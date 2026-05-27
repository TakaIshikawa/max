"""Safety mitigation escape export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.safety_mitigation_escape_report.v1"
KIND = "max.safety_mitigation_escape_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}


def build_safety_mitigation_escape_report(records: Iterable[dict[str, Any]], *, title: str = "Safety Mitigation Escape Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    rows = []
    total = 0
    covered = 0
    for raw in records:
        total += 1
        is_covered = _bool(raw.get("covered")) or _text(raw.get("status")).lower() == "covered"
        if is_covered:
            covered += 1
            continue
        rows.append({"mitigation_category": _text(raw.get("mitigation_category") or raw.get("category")) or "unknown-category", "idea_id": _text(raw.get("idea_id")) or "unknown-idea", "spec_id": _text(raw.get("spec_id")) or "unknown-spec", "missing_control": _text(raw.get("missing_control") or raw.get("control")) or "unspecified control", "severity": _severity(raw.get("severity")), "remediation_owner": _text(raw.get("remediation_owner") or raw.get("owner")) or "unassigned", "remediation_action": _text(raw.get("remediation_action") or raw.get("action")) or "Add the missing mitigation to the generated tact spec."})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["idea_id"].lower(), row["spec_id"].lower(), row["mitigation_category"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Safety Mitigation Escape Report", "summary": {"mitigation_requirement_count": total, "covered_mitigation_count": covered, "missing_mitigation_count": len(rows)}, "missing_mitigations": rows}


def render_safety_mitigation_escape_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_safety_mitigation_escape_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Safety Mitigation Escape Report'}", "", "## Summary", "", f"- Requirements: {summary.get('mitigation_requirement_count', 0)}", f"- Missing: {summary.get('missing_mitigation_count', 0)}"]).rstrip() + "\n"


def _severity(value: Any) -> str:
    severity = (_text(value) or "unknown").lower()
    return severity if severity in SEVERITY_RANK else "unknown"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "covered"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
