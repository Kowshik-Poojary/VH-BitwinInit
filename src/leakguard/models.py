"""Data models for LeakGuard project analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AnalysisErrorType(str, Enum):
    READ_ERROR = "READ_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    SIZE_LIMIT = "SIZE_LIMIT"
    ANALYSIS_ERROR = "ANALYSIS_ERROR"


class OperationKind(str, Enum):
    ACQUIRE = "ACQUIRE"
    CLOSE = "CLOSE"


class ControlFlowKind(str, Enum):
    IF = "IF"
    ELIF = "ELIF"
    ELSE = "ELSE"
    FOR = "FOR"
    ASYNC_FOR = "ASYNC_FOR"
    WHILE = "WHILE"
    TRY = "TRY"
    EXCEPT = "EXCEPT"
    FINALLY = "FINALLY"
    WITH = "WITH"
    ASYNC_WITH = "ASYNC_WITH"
    RETURN = "RETURN"
    RAISE = "RAISE"
    BREAK = "BREAK"
    CONTINUE = "CONTINUE"


class FindingSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class FindingCategory(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    RESOURCE_LEAK = "RESOURCE_LEAK"
    ANALYSIS = "ANALYSIS"


class FindingStatus(str, Enum):
    SAFE = "SAFE"
    DEFINITE_LEAK = "DEFINITE_LEAK"
    ESCAPED = "ESCAPED"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SourceLocation:
    file: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


@dataclass(frozen=True)
class FunctionContext:
    module: str
    function: str
    class_name: str | None = None
    is_async: bool = False
    is_method: bool = False

    def qualified_name(self) -> str:
        if self.class_name:
            return f"{self.module}.{self.class_name}.{self.function}"
        return f"{self.module}.{self.function}"


@dataclass
class ImportInfo:
    module: str
    imported_name: str | None
    alias: str | None
    is_from_import: bool
    location: SourceLocation
    level: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "imported_name": self.imported_name,
            "alias": self.alias,
            "is_from_import": self.is_from_import,
            "level": self.level,
            "location": self.location.to_dict(),
        }


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    location: SourceLocation
    is_async: bool
    is_method: bool
    class_name: str | None = None
    decorators: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    nested_functions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "location": self.location.to_dict(),
            "is_async": self.is_async,
            "is_method": self.is_method,
            "class_name": self.class_name,
            "decorators": self.decorators,
            "parameters": self.parameters,
            "nested_functions": self.nested_functions,
        }


@dataclass
class ClassInfo:
    name: str
    qualified_name: str
    location: SourceLocation
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "location": self.location.to_dict(),
            "bases": self.bases,
            "methods": self.methods,
        }


@dataclass
class ArgumentInfo:
    expression: str
    location: SourceLocation

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "location": self.location.to_dict(),
        }


@dataclass
class CallInfo:
    qualified_name: str | None
    base: str | None
    attribute: str | None
    function_name: str | None
    arguments: list[ArgumentInfo]
    location: SourceLocation
    context: FunctionContext | None = None
    is_method_call: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualified_name": self.qualified_name,
            "base": self.base,
            "attribute": self.attribute,
            "function_name": self.function_name,
            "arguments": [a.to_dict() for a in self.arguments],
            "location": self.location.to_dict(),
            "context": self.context.qualified_name() if self.context else None,
            "is_method_call": self.is_method_call,
        }


@dataclass
class AssignmentInfo:
    targets: list[str]
    value_expression: str
    location: SourceLocation
    context: FunctionContext | None = None
    is_annotated: bool = False
    is_augmented: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "targets": self.targets,
            "value_expression": self.value_expression,
            "location": self.location.to_dict(),
            "context": self.context.qualified_name() if self.context else None,
            "is_annotated": self.is_annotated,
            "is_augmented": self.is_augmented,
        }


@dataclass
class ReturnInfo:
    value_expression: str | None
    location: SourceLocation
    context: FunctionContext | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_expression": self.value_expression,
            "location": self.location.to_dict(),
            "context": self.context.qualified_name() if self.context else None,
        }


@dataclass
class RaiseInfo:
    exception_expression: str | None
    location: SourceLocation
    context: FunctionContext | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "exception_expression": self.exception_expression,
            "location": self.location.to_dict(),
            "context": self.context.qualified_name() if self.context else None,
        }


@dataclass
class ResourceOperation:
    kind: OperationKind
    resource_type: str | None
    registry_key: str | None
    expression: str
    target: str | None
    method: str | None
    location: SourceLocation
    context: FunctionContext | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "resource_type": self.resource_type,
            "registry_key": self.registry_key,
            "expression": self.expression,
            "target": self.target,
            "method": self.method,
            "location": self.location.to_dict(),
            "context": self.context.qualified_name() if self.context else None,
        }


@dataclass
class ContextManagerInfo:
    expression: str
    target: str | None
    location: SourceLocation
    is_async: bool
    context: FunctionContext | None = None
    registry_key: str | None = None
    resource_type: str | None = None
    body_start_line: int | None = None
    body_end_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "target": self.target,
            "location": self.location.to_dict(),
            "is_async": self.is_async,
            "context": self.context.qualified_name() if self.context else None,
            "registry_key": self.registry_key,
            "resource_type": self.resource_type,
            "body_start_line": self.body_start_line,
            "body_end_line": self.body_end_line,
        }


@dataclass
class ControlFlowInfo:
    kind: ControlFlowKind
    location: SourceLocation
    context: FunctionContext | None = None
    condition: str | None = None
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "location": self.location.to_dict(),
            "context": self.context.qualified_name() if self.context else None,
            "condition": self.condition,
            "target": self.target,
        }


@dataclass
class AttributeAccessInfo:
    base: str
    attribute: str
    full_expression: str
    location: SourceLocation
    context: FunctionContext | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "attribute": self.attribute,
            "full_expression": self.full_expression,
            "location": self.location.to_dict(),
            "context": self.context.qualified_name() if self.context else None,
        }


@dataclass
class NameReferenceInfo:
    name: str
    location: SourceLocation
    context: FunctionContext | None = None
    ctx_type: str = "Load"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location.to_dict(),
            "context": self.context.qualified_name() if self.context else None,
            "ctx_type": self.ctx_type,
        }


@dataclass
class FunctionCallPassInfo:
    caller: FunctionContext | None
    callee_expression: str
    callee_name: str | None
    argument_expressions: list[str]
    location: SourceLocation

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller": self.caller.qualified_name() if self.caller else None,
            "callee_expression": self.callee_expression,
            "callee_name": self.callee_name,
            "argument_expressions": self.argument_expressions,
            "location": self.location.to_dict(),
        }


@dataclass
class AnalysisError:
    error_type: AnalysisErrorType
    file: str
    message: str
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type.value,
            "file": self.file,
            "message": self.message,
            "line": self.line,
            "column": self.column,
        }


@dataclass
class Finding:
    rule_id: str
    severity: FindingSeverity
    category: FindingCategory
    message: str
    location: SourceLocation
    status: FindingStatus = FindingStatus.UNKNOWN
    resource_type: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "status": self.status.value,
            "resource_type": self.resource_type,
            "location": self.location.to_dict(),
            "details": self.details,
        }


@dataclass
class FileAnalysis:
    """Structured analysis for a single Python file.

    Designed to be cacheable independently using path, mtime, size, and hash.
    """

    path: str
    module_name: str
    imports: list[ImportInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    assignments: list[AssignmentInfo] = field(default_factory=list)
    returns: list[ReturnInfo] = field(default_factory=list)
    raises: list[RaiseInfo] = field(default_factory=list)
    resource_operations: list[ResourceOperation] = field(default_factory=list)
    context_managers: list[ContextManagerInfo] = field(default_factory=list)
    control_flow: list[ControlFlowInfo] = field(default_factory=list)
    attribute_accesses: list[AttributeAccessInfo] = field(default_factory=list)
    name_references: list[NameReferenceInfo] = field(default_factory=list)
    function_call_passes: list[FunctionCallPassInfo] = field(default_factory=list)
    parse_time_ms: float = 0.0
    extract_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "module_name": self.module_name,
            "imports": [i.to_dict() for i in self.imports],
            "functions": [f.to_dict() for f in self.functions],
            "classes": [c.to_dict() for c in self.classes],
            "calls": [c.to_dict() for c in self.calls],
            "assignments": [a.to_dict() for a in self.assignments],
            "returns": [r.to_dict() for r in self.returns],
            "raises": [r.to_dict() for r in self.raises],
            "resource_operations": [r.to_dict() for r in self.resource_operations],
            "context_managers": [c.to_dict() for c in self.context_managers],
            "control_flow": [c.to_dict() for c in self.control_flow],
            "attribute_accesses": [a.to_dict() for a in self.attribute_accesses],
            "name_references": [n.to_dict() for n in self.name_references],
            "function_call_passes": [f.to_dict() for f in self.function_call_passes],
            "parse_time_ms": self.parse_time_ms,
            "extract_time_ms": self.extract_time_ms,
        }


@dataclass
class AnalysisStatistics:
    files_discovered: int = 0
    files_analyzed: int = 0
    files_skipped: int = 0
    parse_errors: int = 0
    read_errors: int = 0
    size_limit_errors: int = 0
    total_functions: int = 0
    total_classes: int = 0
    total_calls: int = 0
    resource_acquisitions: dict[str, int] = field(default_factory=dict)
    resource_closes: int = 0
    context_managers: int = 0
    scan_time_ms: float = 0.0
    parse_time_ms: float = 0.0
    extract_time_ms: float = 0.0
    total_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_discovered": self.files_discovered,
            "files_analyzed": self.files_analyzed,
            "files_skipped": self.files_skipped,
            "parse_errors": self.parse_errors,
            "read_errors": self.read_errors,
            "size_limit_errors": self.size_limit_errors,
            "total_functions": self.total_functions,
            "total_classes": self.total_classes,
            "total_calls": self.total_calls,
            "resource_acquisitions": dict(self.resource_acquisitions),
            "resource_closes": self.resource_closes,
            "context_managers": self.context_managers,
            "scan_time_ms": self.scan_time_ms,
            "parse_time_ms": self.parse_time_ms,
            "extract_time_ms": self.extract_time_ms,
            "total_time_ms": self.total_time_ms,
        }


@dataclass
class ProjectAnalysis:
    project_path: str
    file_analyses: list[FileAnalysis] = field(default_factory=list)
    errors: list[AnalysisError] = field(default_factory=list)
    statistics: AnalysisStatistics = field(default_factory=AnalysisStatistics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "file_analyses": [f.to_dict() for f in self.file_analyses],
            "errors": [e.to_dict() for e in self.errors],
            "statistics": self.statistics.to_dict(),
        }
