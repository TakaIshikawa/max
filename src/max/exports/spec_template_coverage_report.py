"""Spec template coverage export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_template_coverage_report.v1"
KIND = "max.spec_template_coverage_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
REQUIRED_SECTIONS = ("objective", "scope", "acceptance_criteria", "evidence", "risks", "rollout")
CRITICAL_SECTIONS = {"objective", "acceptance_criteria", "evidence"}


def generate_spec_template_coverage_report(records: Iterable[dict[str, Any]], *, required_sections: Iterable[str] = REQUIRED_SECTIONS, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    required = tuple(_norm(section) for section in required_sections)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, item in enumerate(records, start=1):
        grouped.setdefault(_text(item.get("template") or item.get("template_name") or item.get("spec_type")) or "default", []).append(_spec(item, index))
    rows = []
    for template, specs in grouped.items():
        missing: dict[str, list[str]] = {section: [] for section in required}
        for spec in specs:
            present = {_norm(section) for section in spec["sections"]}
            for section in required:
                if section not in present:
                    missing[section].append(spec["spec_id"])
        missing_sections = {section: ids for section, ids in missing.items() if ids}
        total = len(required) * len(specs)
        covered = total - sum(len(ids) for ids in missing_sections.values())
        critical = sorted(section for section in missing_sections if section in CRITICAL_SECTIONS)
        coverage = round((covered / total) * 100, 2) if total else 100.0
        severity = "critical" if critical else ("warn" if missing_sections else "ok")
        rows.append({"template": template, "spec_count": len(specs), "coverage_percent": coverage, "missing_sections": missing_sections, "missing_critical_sections": critical, "severity": severity})
    rows.sort(key=lambda row: (row["coverage_percent"], row["template"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"template_count": len(rows), "spec_count": sum(row["spec_count"] for row in rows), "template_with_missing_count": sum(1 for row in rows if row["missing_sections"])}, "rows": rows}


def render_spec_template_coverage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_spec_template_coverage_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Spec Template Coverage Report", "", f"Templates: {report.get('summary', {}).get('template_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['template']}: {row['coverage_percent']}% coverage ({row['severity']})")
        for section, ids in row["missing_sections"].items():
            lines.append(f"  - missing {section}: {', '.join(ids)}")
    return "\n".join(lines).rstrip() + "\n"


def _spec(item: dict[str, Any], index: int) -> dict[str, Any]:
    sections = item.get("sections") if isinstance(item.get("sections"), dict) else item
    return {"spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}", "sections": [key for key, value in sections.items() if _present(value)]}


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _norm(value: Any) -> str:
    return _text(value).lower().replace(" ", "_").replace("-", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
