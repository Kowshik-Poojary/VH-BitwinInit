"""Configurable resource acquisition rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceRule:
    call: str
    resource_type: str
    cleanup: str = "close"
    managed: bool = True


DEFAULT_RULES = (
    ResourceRule("open", "File"),
    ResourceRule("Path.open", "File"),
    ResourceRule("pathlib.Path.open", "File"),
    ResourceRule("sqlite3.connect", "SQLite connection"),
    ResourceRule("socket.socket", "Socket"),
)


def load_rules(path: str | Path | None = None) -> tuple[ResourceRule, ...]:
    """Load JSON rules, or return the built-in rules when no file is given."""
    if path is None:
        return DEFAULT_RULES
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(
        ResourceRule(
            call=item["call"],
            resource_type=item["resource_type"],
            cleanup=item.get("cleanup", "close"),
            managed=item.get("managed", True),
        )
        for item in payload["resources"]
    )


def default_rules_json() -> str:
    return json.dumps(
        {
            "resources": [
                {
                    "call": rule.call,
                    "resource_type": rule.resource_type,
                    "cleanup": rule.cleanup,
                    "managed": rule.managed,
                }
                for rule in DEFAULT_RULES
            ]
        },
        indent=2,
    )