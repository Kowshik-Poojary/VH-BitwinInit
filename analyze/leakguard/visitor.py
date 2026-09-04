"""Single-pass AST visitor for structural extraction."""

from __future__ import annotations

import ast

from leakguard.ast_utils import (
    expr_to_str,
    get_base_names,
    get_call_info,
    get_decorator_name,
    target_to_str,
    targets_to_strs,
)
from leakguard.models import (
    ArgumentInfo,
    AssignmentInfo,
    AttributeAccessInfo,
    CallInfo,
    ClassInfo,
    ContextManagerInfo,
    ControlFlowInfo,
    ControlFlowKind,
    FileAnalysis,
    FunctionCallPassInfo,
    FunctionContext,
    FunctionInfo,
    ImportInfo,
    NameReferenceInfo,
    OperationKind,
    RaiseInfo,
    ResourceOperation,
    ReturnInfo,
    SourceLocation,
)
from leakguard.registry import lookup_cleanup_method, lookup_resource


class ProjectASTVisitor(ast.NodeVisitor):
    """Extract structural information from a Python AST in a single traversal."""

    def __init__(self, filename: str, module_name: str) -> None:
        self.filename = filename
        self.module_name = module_name
        self.analysis = FileAnalysis(path=filename, module_name=module_name)

        self._function_stack: list[FunctionContext] = []
        self._class_stack: list[str] = []
        self._current_function_info: FunctionInfo | None = None
        self._processed_acquire_calls: set[int] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            imported_name = alias.name
            alias_name = alias.asname or alias.name.split(".")[0]
            self.analysis.imports.append(
                ImportInfo(
                    module=imported_name,
                    imported_name=imported_name,
                    alias=alias_name if alias.asname else None,
                    is_from_import=False,
                    location=self._loc(node),
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                continue
            imported_name = alias.name
            alias_name = alias.asname or alias.name
            self.analysis.imports.append(
                ImportInfo(
                    module=module,
                    imported_name=imported_name,
                    alias=alias.asname,
                    is_from_import=True,
                    location=self._loc(node),
                    level=node.level,
                )
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_qname = self._qualified_name(node.name)
        class_info = ClassInfo(
            name=node.name,
            qualified_name=class_qname,
            location=self._loc(node),
            bases=get_base_names(node.bases),
        )
        self.analysis.classes.append(class_info)
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_function(node, is_async=True)

    def _enter_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
    ) -> None:
        class_name = self._class_stack[-1] if self._class_stack else None
        is_method = class_name is not None
        qname = self._qualified_name(node.name)

        ctx = FunctionContext(
            module=self.module_name,
            function=node.name,
            class_name=class_name,
            is_async=is_async,
            is_method=is_method,
        )
        self._function_stack.append(ctx)

        func_info = FunctionInfo(
            name=node.name,
            qualified_name=qname,
            location=self._loc(node),
            is_async=is_async,
            is_method=is_method,
            class_name=class_name,
            decorators=[get_decorator_name(d) for d in node.decorator_list],
            parameters=[arg.arg for arg in node.args.args],
        )

        if self._current_function_info is not None:
            self._current_function_info.nested_functions.append(node.name)

        parent_func_info = self._current_function_info
        self._current_function_info = func_info
        self.analysis.functions.append(func_info)

        self.generic_visit(node)

        self._current_function_info = parent_func_info
        self._function_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        targets = targets_to_strs(node.targets)
        value_expr = expr_to_str(node.value)
        location = self._loc(node)

        self.analysis.assignments.append(
            AssignmentInfo(
                targets=targets,
                value_expression=value_expr,
                location=location,
                context=self._current_context(),
            )
        )

        if isinstance(node.value, ast.Call):
            self._handle_call_assignment(node.value, targets, location)

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.target is None:
            self.generic_visit(node)
            return

        targets = [target_to_str(node.target)]
        value_expr = expr_to_str(node.value) if node.value else ""
        location = self._loc(node)

        self.analysis.assignments.append(
            AssignmentInfo(
                targets=targets,
                value_expression=value_expr,
                location=location,
                context=self._current_context(),
                is_annotated=True,
            )
        )

        if node.value is not None and isinstance(node.value, ast.Call):
            self._handle_call_assignment(node.value, targets, location)

        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        targets = [target_to_str(node.target)]
        value_expr = expr_to_str(node.value)
        self.analysis.assignments.append(
            AssignmentInfo(
                targets=targets,
                value_expression=f"{targets[0]} {self._aug_op(node.op)}= {value_expr}",
                location=self._loc(node),
                context=self._current_context(),
                is_augmented=True,
            )
        )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        info = get_call_info(node)
        args = [
            ArgumentInfo(expression=expr_to_str(arg), location=self._loc(arg))
            for arg in node.args
        ]

        call_info = CallInfo(
            qualified_name=info["qualified_name"],
            base=info["base"],
            attribute=info["attribute"],
            function_name=info["function_name"],
            arguments=args,
            location=self._loc(node),
            context=self._current_context(),
            is_method_call=info["is_method_call"],
        )
        self.analysis.calls.append(call_info)

        self._detect_resource_acquire(node, call_info)
        self._detect_resource_close(node, call_info)
        self._record_function_call_pass(node, call_info)

        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        value_expr = expr_to_str(node.value) if node.value else None
        self.analysis.returns.append(
            ReturnInfo(
                value_expression=value_expr,
                location=self._loc(node),
                context=self._current_context(),
            )
        )
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.RETURN,
                location=self._loc(node),
                context=self._current_context(),
            )
        )
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        exc_expr = expr_to_str(node.exc) if node.exc else None
        self.analysis.raises.append(
            RaiseInfo(
                exception_expression=exc_expr,
                location=self._loc(node),
                context=self._current_context(),
            )
        )
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.RAISE,
                location=self._loc(node),
                context=self._current_context(),
            )
        )
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.IF,
                location=self._loc(node),
                context=self._current_context(),
                condition=expr_to_str(node.test),
            )
        )
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.FOR,
                location=self._loc(node),
                context=self._current_context(),
                target=expr_to_str(node.target),
            )
        )
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.ASYNC_FOR,
                location=self._loc(node),
                context=self._current_context(),
                target=expr_to_str(node.target),
            )
        )
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.WHILE,
                location=self._loc(node),
                context=self._current_context(),
                condition=expr_to_str(node.test),
            )
        )
        self.generic_visit(node)

    def visit_Break(self, node: ast.Break) -> None:
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.BREAK,
                location=self._loc(node),
                context=self._current_context(),
            )
        )
        self.generic_visit(node)

    def visit_Continue(self, node: ast.Continue) -> None:
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.CONTINUE,
                location=self._loc(node),
                context=self._current_context(),
            )
        )
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=ControlFlowKind.TRY,
                location=self._loc(node),
                context=self._current_context(),
            )
        )
        for handler in node.handlers:
            self.analysis.control_flow.append(
                ControlFlowInfo(
                    kind=ControlFlowKind.EXCEPT,
                    location=self._loc(handler),
                    context=self._current_context(),
                    condition=expr_to_str(handler.type) if handler.type else None,
                )
            )
        if node.finalbody:
            self.analysis.control_flow.append(
                ControlFlowInfo(
                    kind=ControlFlowKind.FINALLY,
                    location=self._loc(node.finalbody[0]),
                    context=self._current_context(),
                )
            )
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._process_with(node, is_async=False)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._process_with(node, is_async=True)

    def _process_with(self, node: ast.With | ast.AsyncWith, is_async: bool) -> None:
        kind = ControlFlowKind.ASYNC_WITH if is_async else ControlFlowKind.WITH
        self.analysis.control_flow.append(
            ControlFlowInfo(
                kind=kind,
                location=self._loc(node),
                context=self._current_context(),
            )
        )

        body_start = node.body[0].lineno if node.body else None
        body_end = node.body[-1].end_lineno if node.body else None

        for item in node.items:
            expr = expr_to_str(item.context_expr)
            target = target_to_str(item.optional_vars) if item.optional_vars else None
            registry_key = None
            resource_type = None

            if isinstance(item.context_expr, ast.Call):
                call_info_dict = get_call_info(item.context_expr)
                qname = call_info_dict["qualified_name"]
                definition = lookup_resource(qname)
                if definition:
                    registry_key = qname
                    resource_type = definition.resource_type

            self.analysis.context_managers.append(
                ContextManagerInfo(
                    expression=expr,
                    target=target,
                    location=self._loc(item.context_expr),
                    is_async=is_async,
                    context=self._current_context(),
                    registry_key=registry_key,
                    resource_type=resource_type,
                    body_start_line=body_start,
                    body_end_line=body_end,
                )
            )

            if isinstance(item.context_expr, ast.Call):
                self._detect_resource_acquire_in_context(
                    item.context_expr, target, self._loc(item.context_expr)
                )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load):
            base = expr_to_str(node.value)
            self.analysis.attribute_accesses.append(
                AttributeAccessInfo(
                    base=base,
                    attribute=node.attr,
                    full_expression=f"{base}.{node.attr}",
                    location=self._loc(node),
                    context=self._current_context(),
                )
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        ctx_type = type(node.ctx).__name__
        if ctx_type in ("Load", "Store", "Del"):
            self.analysis.name_references.append(
                NameReferenceInfo(
                    name=node.id,
                    location=self._loc(node),
                    context=self._current_context(),
                    ctx_type=ctx_type,
                )
            )
        self.generic_visit(node)

    def _handle_call_assignment(
        self,
        call_node: ast.Call,
        targets: list[str],
        location: SourceLocation,
    ) -> None:
        call_info_dict = get_call_info(call_node)
        qname = call_info_dict["qualified_name"]
        definition = lookup_resource(qname)
        if definition is None:
            return

        self._processed_acquire_calls.add(id(call_node))
        primary_target = targets[0] if targets else None
        self.analysis.resource_operations.append(
            ResourceOperation(
                kind=OperationKind.ACQUIRE,
                resource_type=definition.resource_type,
                registry_key=qname,
                expression=expr_to_str(call_node),
                target=primary_target,
                method=None,
                location=location,
                context=self._current_context(),
            )
        )

    def _detect_resource_acquire(
        self, node: ast.Call, call_info: CallInfo
    ) -> None:
        if id(node) in self._processed_acquire_calls:
            return

        definition = lookup_resource(call_info.qualified_name)
        if definition is None:
            return

        self._processed_acquire_calls.add(id(node))
        self.analysis.resource_operations.append(
            ResourceOperation(
                kind=OperationKind.ACQUIRE,
                resource_type=definition.resource_type,
                registry_key=call_info.qualified_name,
                expression=expr_to_str(node),
                target=None,
                method=None,
                location=call_info.location,
                context=self._current_context(),
            )
        )

    def _detect_resource_acquire_in_context(
        self,
        call_node: ast.Call,
        target: str | None,
        location: SourceLocation,
    ) -> None:
        call_info_dict = get_call_info(call_node)
        qname = call_info_dict["qualified_name"]
        definition = lookup_resource(qname)
        if definition is None:
            return

        self._processed_acquire_calls.add(id(call_node))
        self.analysis.resource_operations.append(
            ResourceOperation(
                kind=OperationKind.ACQUIRE,
                resource_type=definition.resource_type,
                registry_key=qname,
                expression=expr_to_str(call_node),
                target=target,
                method=None,
                location=location,
                context=self._current_context(),
            )
        )

    def _detect_resource_close(
        self, node: ast.Call, call_info: CallInfo
    ) -> None:
        cleanup = lookup_cleanup_method(call_info.base, call_info.attribute)
        if cleanup is None:
            return

        method_name, definition = cleanup
        self.analysis.resource_operations.append(
            ResourceOperation(
                kind=OperationKind.CLOSE,
                resource_type=definition.resource_type,
                registry_key=None,
                expression=expr_to_str(node),
                target=call_info.base,
                method=method_name,
                location=call_info.location,
                context=self._current_context(),
            )
        )

    def _record_function_call_pass(
        self, node: ast.Call, call_info: CallInfo
    ) -> None:
        if call_info.is_method_call and call_info.attribute in (
            "close",
            "shutdown",
        ):
            return

        arg_exprs = [arg.expression for arg in call_info.arguments]
        self.analysis.function_call_passes.append(
            FunctionCallPassInfo(
                caller=self._current_context(),
                callee_expression=call_info.qualified_name or expr_to_str(node.func),
                callee_name=call_info.function_name or call_info.attribute,
                argument_expressions=arg_exprs,
                location=call_info.location,
            )
        )

    def _current_context(self) -> FunctionContext | None:
        return self._function_stack[-1] if self._function_stack else None

    def _qualified_name(self, name: str) -> str:
        parts = [self.module_name]
        if self._class_stack:
            parts.append(".".join(self._class_stack))
        parts.append(name)
        return ".".join(parts)

    def _loc(self, node: ast.AST) -> SourceLocation:
        return SourceLocation(
            file=self.filename,
            line=getattr(node, "lineno", 0) or 0,
            column=getattr(node, "col_offset", 0) or 0,
            end_line=getattr(node, "end_lineno", None),
            end_column=getattr(node, "end_col_offset", None),
        )

    @staticmethod
    def _aug_op(op: ast.operator) -> str:
        mapping = {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
            ast.Mod: "%",
            ast.Pow: "**",
            ast.FloorDiv: "//",
            ast.BitOr: "|",
            ast.BitAnd: "&",
            ast.BitXor: "^",
            ast.LShift: "<<",
            ast.RShift: ">>",
        }
        return mapping.get(type(op), "?")
