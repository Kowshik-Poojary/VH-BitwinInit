"""Centralized resource registry for LeakGuard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResourceDefinition:
    resource_type: str
    cleanup_methods: tuple[str, ...]
    context_manager_aware: bool = True
    acquisition_pattern: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "cleanup_methods": list(self.cleanup_methods),
            "context_manager_aware": self.context_manager_aware,
            "acquisition_pattern": self.acquisition_pattern,
        }


RESOURCE_REGISTRY: dict[str, ResourceDefinition] = {
    "open": ResourceDefinition(
        resource_type="file",
        cleanup_methods=("close",),
        context_manager_aware=True,
    ),
    "sqlite3.connect": ResourceDefinition(
        resource_type="database",
        cleanup_methods=("close",),
        context_manager_aware=True,
    ),
    "socket.socket": ResourceDefinition(
        resource_type="socket",
        cleanup_methods=("close", "shutdown"),
        context_manager_aware=False,
    ),
    "socket.create_connection": ResourceDefinition(
        resource_type="socket",
        cleanup_methods=("close", "shutdown"),
        context_manager_aware=False,
    ),
    "tempfile.NamedTemporaryFile": ResourceDefinition(
        resource_type="file",
        cleanup_methods=("close",),
        context_manager_aware=True,
    ),
    "tempfile.TemporaryFile": ResourceDefinition(
        resource_type="file",
        cleanup_methods=("close",),
        context_manager_aware=True,
    ),
}


def lookup_resource(qualified_name: str | None) -> ResourceDefinition | None:
    """Look up a resource definition by qualified call name."""
    if qualified_name is None:
        return None
    return RESOURCE_REGISTRY.get(qualified_name)


def lookup_cleanup_method(
    base: str | None, attribute: str | None
) -> tuple[str, ResourceDefinition] | None:
    """Check if an attribute call is a known cleanup method on any resource type."""
    if attribute is None:
        return None
    for definition in RESOURCE_REGISTRY.values():
        if attribute in definition.cleanup_methods:
            return attribute, definition
    return None


def register_resource(key: str, definition: ResourceDefinition) -> None:
    """Register a new resource type (for extensibility)."""
    RESOURCE_REGISTRY[key] = definition
