"""States propagated through a function CFG."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResourceState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    ESCAPED = "escaped"
    UNKNOWN = "unknown"


@dataclass
class AnalysisState:
    resources: dict[str, ResourceState] = field(default_factory=dict)

    def copy(self) -> "AnalysisState":
        return AnalysisState(resources=self.resources.copy())

    def merge(self, other: "AnalysisState") -> "AnalysisState":
        """Join states, preserving an open state from any incoming path."""
        merged = self.copy()
        variables = set(self.resources) | set(other.resources)
        for variable in variables:
            left = self.resources.get(variable)
            right = other.resources.get(variable)
            if left == right:
                if left is not None:
                    merged.resources[variable] = left
            elif ResourceState.OPEN in (left, right):
                merged.resources[variable] = ResourceState.OPEN
            elif ResourceState.UNKNOWN in (left, right):
                merged.resources[variable] = ResourceState.UNKNOWN
            elif ResourceState.ESCAPED in (left, right):
                merged.resources[variable] = ResourceState.ESCAPED
            elif left is not None:
                merged.resources[variable] = left
            elif right is not None:
                merged.resources[variable] = right
        return merged
