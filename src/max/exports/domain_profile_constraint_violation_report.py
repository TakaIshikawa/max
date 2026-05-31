"""Domain profile constraint violation export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.domain_profile_constraint_violation_report.v1"
KIND = "max.domain_profile_constraint_violation_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_domain_profile_constraint_violation_report(records: Iterable[dict[str, Any]], *, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(records, start=1):
        rows.extend(_violations(item, index))
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["profile"], row["item_id"], row["violation_type"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
        "summary": {"item_count": len({row["item_id"] for row in rows}), "violation_count": len(rows), "critical_count": sum(1 for row in rows if row["severity"] == "critical")},
        "rows": rows,
    }


def render_domain_profile_constraint_violation_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_domain_profile_constraint_violation_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Domain Profile Constraint Violation Report", "", f"Violations: {report.get('summary', {}).get('violation_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['profile']} / {row['item_id']} / {row['violation_type']}: {row['remediation']}")
    return "\n".join(lines).rstrip() + "\n"


def _violations(item: dict[str, Any], index: int) -> list[dict[str, Any]]:
    profile = _text(item.get("profile")) or "default"
    item_id = _text(item.get("item_id") or item.get("id")) or f"item-{index}"
    status = _text(item.get("status")).lower()
    severity = "critical" if status in {"approved", "published"} else "warn"
    constraints = item.get("constraints") if isinstance(item.get("constraints"), dict) else item
    rows = []
    stacks = {value.lower() for value in _list(item.get("stacks") or item.get("stack"))}
    excluded = {value.lower() for value in _list(constraints.get("excluded_stacks"))}
    for stack in sorted(stacks & excluded):
        rows.append(_row(profile, item_id, "excluded_stack", stack, severity, "Replace excluded stack component."))
    required_segment = _text(constraints.get("required_user_segment")).lower()
    segment = _text(item.get("user_segment") or item.get("segment")).lower()
    if required_segment and segment != required_segment:
        rows.append(_row(profile, item_id, "missing_required_segment", segment or "missing", severity, f"Align item to required user segment {required_segment}."))
    regulated_allowed = bool(constraints.get("allow_regulated_data", False))
    if bool(item.get("regulated_data")) and not regulated_allowed:
        rows.append(_row(profile, item_id, "regulated_data", "true", severity, "Remove regulated data handling or update profile approval."))
    return rows


def _row(profile: str, item_id: str, violation_type: str, observed: str, severity: str, remediation: str) -> dict[str, Any]:
    return {"profile": profile, "item_id": item_id, "violation_type": violation_type, "observed_value": observed, "severity": severity, "remediation": remediation}


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
