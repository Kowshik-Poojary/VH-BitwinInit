"""Import resolution utilities for mapping aliases to qualified names."""

from __future__ import annotations

from leakguard.models import FileAnalysis, ImportInfo


class ImportResolver:
    """Resolve imported names to their source modules.

    This is intentionally conservative — perfect resolution requires
    type inference which belongs in the data-flow engine.
    """

    def __init__(self, file_analysis: FileAnalysis) -> None:
        self._imports = file_analysis.imports
        self._alias_map: dict[str, ImportInfo] = {}
        self._from_import_map: dict[str, ImportInfo] = {}
        self._build_maps()

    def _build_maps(self) -> None:
        for imp in self._imports:
            if imp.is_from_import and imp.imported_name:
                key = imp.alias or imp.imported_name
                self._from_import_map[key] = imp
            else:
                key = imp.alias or (imp.imported_name or imp.module).split(".")[0]
                self._alias_map[key] = imp

    def resolve_name(self, name: str) -> str | None:
        """Resolve a bare name to its module prefix if known."""
        if name in self._alias_map:
            return self._alias_map[name].module or self._alias_map[name].imported_name
        return None

    def resolve_attribute_call(self, base: str, attribute: str) -> str | None:
        """Resolve base.attr to a qualified call name if possible.

        Example: db.connect -> sqlite3.connect when db aliases sqlite3.
        """
        if base in self._alias_map:
            module = self._alias_map[base].module or self._alias_map[base].imported_name
            if module:
                return f"{module}.{attribute}"
        if base in self._from_import_map:
            imp = self._from_import_map[base]
            if imp.imported_name == attribute or imp.alias == base:
                module = imp.module or ""
                return f"{module}.{imp.imported_name}" if module else imp.imported_name
        return None

    def resolve_call(self, base: str | None, attribute: str | None, function_name: str | None) -> str | None:
        """Attempt to resolve a call to a registry-compatible qualified name."""
        if base and attribute:
            resolved = self.resolve_attribute_call(base, attribute)
            if resolved:
                return resolved
            return f"{base}.{attribute}"
        return function_name
