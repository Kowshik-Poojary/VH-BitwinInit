"""Data models for resource lifecycle facts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResourceState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ESCAPED = "ESCAPED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Resource:
    """One resource acquired in a source scope."""

    resource_id: int
    resource_type: str
    variable: str
    filename: str
    opened_line: int
    scope: str
    state: ResourceState = ResourceState.OPEN
    closed_line: int | None = None
    ownership: str = "LOCAL_OWNER"

    @property
    def is_closed(self) -> bool:
        return self.state == ResourceState.CLOSED
