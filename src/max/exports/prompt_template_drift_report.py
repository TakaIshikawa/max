"""Prompt template drift export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.prompt_template_drift_report.v1"
KIND = "max.prompt_template_drift_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_prompt_template_drift_report(records: Iterable[dict[str, Any]], *, title: str = "Prompt Template Drift Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    rows = []
    compared = 0
    for raw in records:
        compared += 1
        template_id = _text(raw.get("template_id")) or "unknown-template"
        baseline_version = _text(raw.get("baseline_version")) or "baseline"
        current_version = _text(raw.get("current_version")) or "current"
        baseline = _sections(raw.get("baseline_sections") or raw.get("baseline"))
        current = _sections(raw.get("current_sections") or raw.get("current"))
        for section in sorted(set(baseline) - set(current), key=str.lower):
            rows.append(_row(template_id, baseline_version, current_version, section, "removed", "critical" if _required(section, baseline) else "medium"))
        for section in sorted(set(current) - set(baseline), key=str.lower):
            rows.append(_row(template_id, baseline_version, current_version, section, "added", "low"))
        for section in sorted(set(baseline) & set(current), key=str.lower):
            if _body(baseline[section]) != _body(current[section]):
                severity = "high" if _required(section, baseline) else "medium"
                rows.append(_row(template_id, baseline_version, current_version, section, "changed", severity))
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["template_id"].lower(), row["section"].lower(), row["drift_type"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Prompt Template Drift Report", "summary": {"template_count": compared, "drift_count": len(rows), "added_count": sum(1 for row in rows if row["drift_type"] == "added"), "removed_count": sum(1 for row in rows if row["drift_type"] == "removed"), "changed_count": sum(1 for row in rows if row["drift_type"] == "changed")}, "drift_rows": rows}


def render_prompt_template_drift_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_prompt_template_drift_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Prompt Template Drift Report'}", "", "## Summary", "", f"- Templates: {summary.get('template_count', 0)}", f"- Drift rows: {summary.get('drift_count', 0)}"]).rstrip() + "\n"


def _row(template_id: str, baseline_version: str, current_version: str, section: str, drift_type: str, severity: str) -> dict[str, Any]:
    return {"template_id": template_id, "baseline_version": baseline_version, "current_version": current_version, "section": section, "drift_type": drift_type, "severity": severity, "review_recommendation": f"Review {section} {drift_type} drift before promoting this prompt template."}


def _sections(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): section for key, section in value.items()}
    if isinstance(value, list):
        return {str(item.get("name") or item.get("section") or "unknown-section"): item for item in value if isinstance(item, dict)}
    return {}


def _required(section: str, sections: dict[str, Any]) -> bool:
    value = sections.get(section)
    if isinstance(value, dict):
        return bool(value.get("required"))
    return section.lower() in {"safety", "instructions", "system"}


def _body(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("body") or value.get("text") or value.get("content")
    return _text(value)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
