"""Machine-readable output formats for LeakGuard findings."""

from __future__ import annotations

import json
from collections.abc import Iterable

from .detector import Finding


def finding_dict(finding: Finding) -> dict[str, object]:
    return {
        "file": finding.filename,
        "scope": finding.scope,
        "resource": finding.resource_type,
        "variable": finding.variable,
        "opened_line": finding.opened_line,
        "closed_line": finding.closed_line,
        "classification": finding.classification,
        "reason": finding.reason,
        "evidence": list(finding.evidence),
    }


def json_report(findings: Iterable[Finding]) -> str:
    return json.dumps(
        {"version": 1, "findings": [finding_dict(finding) for finding in findings]},
        indent=2,
    )


def sarif_report(findings: Iterable[Finding]) -> str:
    results = []
    rules: dict[str, dict[str, str]] = {}
    for finding in findings:
        rule_id = "LEAKGUARD001"
        rules[rule_id] = {
            "id": rule_id,
            "name": "Resource leak",
            "shortDescription": "A resource may remain open on a reachable path.",
        }
        results.append(
            {
                "ruleId": rule_id,
                "level": "error",
                "message": {
                    "text": (
                        f"{finding.classification}: {finding.resource_type} "
                        f"'{finding.variable}' remains open. {finding.reason}"
                    )
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": finding.filename.replace("\\", "/")
                            },
                            "region": {"startLine": finding.opened_line},
                        }
                    }
                ],
            }
        )
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "LeakGuard",
                        "informationUri": "https://github.com/",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(payload, indent=2)