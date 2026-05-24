"""Profile constraint violation export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.profile_constraint_violation_report.v1"
KIND = "max.profile_constraint_violation_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "low": 2}


class ProfileConstraintViolationInput(TypedDict, total=False):
    profile: str
    constraint: str
    constraint_type: str
    severity: str
    observed_value: str
    expected_value: str
    remediation_hint: str
    passed: bool


def build_profile_constraint_violation_report(
    records: Iterable[ProfileConstraintViolationInput | dict[str, Any]],
    *,
    title: str = "Profile Constraint Violation Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = [_row(raw, index) for index, raw in enumerate(records, start=1)]
    violations = [row for row in rows if row["status"] == "violation"]
    violations.sort(key=lambda row: (_SEVERITY_ORDER.get(row["severity"], 3), row["profile"].lower(), row["constraint"].lower()))
    profiles = {row["profile"] for row in rows}
    profiles_with = {row["profile"] for row in violations}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Profile Constraint Violation Report",
        "summary": {
            "total_profiles": len(profiles),
            "profiles_with_violations": len(profiles_with),
            "critical_violations": sum(1 for row in violations if row["severity"] == "critical"),
            "warning_violations": sum(1 for row in violations if row["severity"] == "warning"),
        },
        "constraint_rows": rows,
        "violations": violations,
        "violations_by_profile": _group(violations, "profile"),
        "violations_by_severity": _group(violations, "severity"),
        "violations_by_constraint_type": _group(violations, "constraint_type"),
    }


def render_profile_constraint_violation_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_profile_constraint_violation_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([
        f"# {report.get('title') or 'Profile Constraint Violation Report'}",
        "",
        "## Summary",
        "",
        f"- Profiles: {summary.get('total_profiles', 0)}",
        f"- Profiles with violations: {summary.get('profiles_with_violations', 0)}",
    ]).rstrip() + "\n"


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    passed = raw.get("passed") is True or _text(raw.get("status")).lower() in {"passed", "ok", "compliant"}
    severity = _text(raw.get("severity")).lower() or "warning"
    severity = severity if severity in _SEVERITY_ORDER else "warning"
    return {
        "profile": _text(raw.get("profile")) or "Unknown profile",
        "constraint": _text(raw.get("constraint") or raw.get("name")) or f"constraint-{index}",
        "constraint_type": _text(raw.get("constraint_type") or raw.get("type")) or "general",
        "severity": severity,
        "observed_value": _text(raw.get("observed_value")),
        "expected_value": _text(raw.get("expected_value")),
        "remediation_hint": _text(raw.get("remediation_hint")) or "Review profile constraint configuration.",
        "status": "passed" if passed else "violation",
    }


def _group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return [{key: value, "violation_count": sum(1 for row in rows if row[key] == value)} for value in sorted({row[key] for row in rows}, key=str.casefold)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
