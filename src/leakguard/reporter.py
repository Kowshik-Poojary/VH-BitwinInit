"""Output renderers for LeakGuard findings."""

from __future__ import annotations

import json
from typing import Any

from leakguard.models import Finding


def render_json(findings: list[Finding]) -> str:
	return json.dumps(
		{"summary": {"findings": len(findings)}, "findings": [f.to_dict() for f in findings]},
		indent=2,
	)


def render_text(findings: list[Finding]) -> str:
	lines = ["LeakGuard", "========", ""]
	if not findings:
		lines.append("No findings.")
		return "\n".join(lines)

	for finding in findings:
		confidence = finding.details.get("confidence", "LOW")
		lines.extend(
			[
				f"{finding.severity.value} {finding.rule_id} {finding.status.value} {confidence}",
				f"{finding.location.file}:{finding.location.line}:{finding.location.column}",
				f"{finding.message} ({finding.resource_type})",
				"",
			]
		)
	return "\n".join(lines).rstrip()


def render_sarif(findings: list[Finding]) -> str:
	results: list[dict[str, Any]] = []
	for finding in findings:
		results.append(
			{
				"ruleId": finding.rule_id,
				"level": finding.severity.value.lower(),
				"message": {"text": finding.message},
				"locations": [
					{
						"physicalLocation": {
							"artifactLocation": {"uri": finding.location.file},
							"region": {"startLine": finding.location.line, "startColumn": finding.location.column + 1},
						}
					}
				],
			}
		)
	return json.dumps(
		{
			"$schema": "https://json.schemastore.org/sarif-2.1.0.json",
			"version": "2.1.0",
			"runs": [{"tool": {"driver": {"name": "LeakGuard"}}, "results": results}],
		},
		indent=2,
	)
