"""Detect resource acquisitions and cleanup from normalized AST facts."""

from __future__ import annotations

from ..parser import ScopeFacts
from .models import Resource, ResourceState


class ResourceDetector:
    """Build resource lifecycle records from parsed Python scopes."""

    def detect(
        self,
        scopes: tuple[ScopeFacts, ...],
        filename: str,
    ) -> tuple[Resource, ...]:
        resources: list[Resource] = []
        next_id = 1

        for scope in scopes:
            active: dict[str, int] = {}
            for operation in scope.operations:
                if operation.kind == "acquire":
                    resource = Resource(
                        resource_id=next_id,
                        resource_type=operation.resource_type,
                        variable=operation.variable,
                        filename=filename,
                        opened_line=operation.line,
                        scope=scope.name,
                    )
                    resources.append(resource)
                    active[operation.variable] = len(resources) - 1
                    next_id += 1
                elif operation.kind == "managed":
                    resource = Resource(
                        resource_id=next_id,
                        resource_type=operation.resource_type,
                        variable=operation.variable,
                        filename=filename,
                        opened_line=operation.line,
                        scope=scope.name,
                        state=ResourceState.CLOSED,
                    )
                    resources.append(resource)
                    next_id += 1
                elif operation.kind == "close":
                    resource_index = active.pop(operation.variable, None)
                    if resource_index is not None:
                        resource = resources[resource_index]
                        resources[resource_index] = Resource(
                            resource_id=resource.resource_id,
                            resource_type=resource.resource_type,
                            variable=resource.variable,
                            filename=resource.filename,
                            opened_line=resource.opened_line,
                            scope=resource.scope,
                            state=ResourceState.CLOSED,
                            closed_line=operation.line,
                        )

        return tuple(resources)
