"""Buildable unit dependency freshness export report."""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_dependency_freshness_report.v1"
KIND = "max.buildable_unit_dependency_freshness_report"


def generate_buildable_unit_dependency_freshness_report(records: Iterable[dict[str, Any]], *, as_of: str, stale_after_days: int = 30) -> dict[str, Any]:
    today = date.fromisoformat(as_of)
    findings = []
    checked = 0
    for unit in records:
        unit_id = _text(unit.get("unit_id") or unit.get("id")) or "unknown-unit"
        for dep in unit.get("dependencies", []):
            checked += 1
            checked_at = _text(dep.get("checked_at") or dep.get("observed_at"))
            issue = None
            age = None
            if not checked_at:
                issue = "missing_freshness_metadata"
            else:
                age = (today - date.fromisoformat(checked_at[:10])).days
                if age > stale_after_days:
                    issue = "stale_dependency_metadata"
            if issue:
                findings.append({"unit_id": unit_id, "dependency": _text(dep.get("name")) or "unknown-dependency", "version": _text(dep.get("version")) or "unknown-version", "ecosystem": _text(dep.get("ecosystem")) or "unknown-ecosystem", "age_days": age, "severity": "critical" if issue.startswith("missing") else "high" if age and age >= stale_after_days * 2 else "medium", "issue_type": issue, "recommended_action": "Refresh dependency verification metadata."})
    findings.sort(key=lambda row: (_severity_rank(row["severity"]), row["unit_id"].lower(), row["dependency"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"dependency_count": checked, "finding_count": len(findings), "missing_metadata_count": sum(1 for row in findings if row["issue_type"] == "missing_freshness_metadata"), "stale_metadata_count": sum(1 for row in findings if row["issue_type"] == "stale_dependency_metadata"), "as_of": as_of, "stale_after_days": stale_after_days}, "findings": findings}


def _severity_rank(value: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(value, 4)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

