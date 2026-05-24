"""Tact spec generation failure export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.tact_spec_generation_failure_report.v1"
KIND = "max.tact_spec_generation_failure_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class TactSpecGenerationFailureInput(TypedDict, total=False):
    unit_id: str
    template: str
    reason: str
    failed_at: str
    retryable: bool
    owner: str
    status: str


def build_tact_spec_generation_failure_report(records: Iterable[TactSpecGenerationFailureInput | dict[str, Any]], *, title: str = "Tact Spec Generation Failure Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    rows = [_row(raw, index) for index, raw in enumerate(records, start=1)]
    rows.sort(key=lambda row: (row["status"] == "resolved", row["template"].lower(), row["reason"].lower(), row["unit_id"].lower()))
    unresolved = [row for row in rows if row["status"] != "resolved"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Tact Spec Generation Failure Report",
        "summary": {
            "total_failures": len(rows),
            "affected_units": len({row["unit_id"] for row in rows}),
            "affected_templates": len({row["template"] for row in rows}),
            "unresolved_failures": len(unresolved),
        },
        "failure_rows": rows,
        "unresolved_failures": unresolved,
        "failures_by_template": _group(rows, "template"),
        "failures_by_reason": _group(rows, "reason"),
    }


def render_tact_spec_generation_failure_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_tact_spec_generation_failure_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Tact Spec Generation Failure Report'}", "", "## Summary", "", f"- Failures: {summary.get('total_failures', 0)}", f"- Unresolved: {summary.get('unresolved_failures', 0)}"]).rstrip() + "\n"


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "unit_id": _text(raw.get("unit_id") or raw.get("id")) or f"unknown-unit-{index}",
        "template": _text(raw.get("template")) or "unknown-template",
        "reason": _normalize_reason(raw.get("reason") or raw.get("failure_reason")),
        "failed_at": _text(raw.get("failed_at")),
        "retryable": _bool(raw.get("retryable")),
        "owner": _text(raw.get("owner")) or "Unassigned",
        "status": _text(raw.get("status")).lower() or "unresolved",
    }


def _group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return [{key: value, "failure_count": sum(1 for row in rows if row[key] == value), "unresolved_count": sum(1 for row in rows if row[key] == value and row["status"] != "resolved")} for value in sorted({row[key] for row in rows}, key=str.casefold)]


def _normalize_reason(value: Any) -> str:
    text = _text(value).lower()
    if not text:
        return "unknown"
    if "timeout" in text:
        return "timeout"
    if "template" in text:
        return "template_error"
    if "evidence" in text:
        return "missing_evidence"
    return text.replace(" ", "_")


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "retryable"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
