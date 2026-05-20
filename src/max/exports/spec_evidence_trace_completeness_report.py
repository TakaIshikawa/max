"""Spec evidence trace completeness export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.spec_evidence_trace_completeness_report.v1"
KIND = "max.spec_evidence_trace_completeness_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class SpecEvidenceTraceInput(TypedDict, total=False):
    spec_id: str
    title: str
    unit_ids: list[str] | tuple[str, ...] | str
    insight_ids: list[str] | tuple[str, ...] | str
    signal_ids: list[str] | tuple[str, ...] | str
    missing_links: list[str] | tuple[str, ...] | str
    generated_at: str
    owner: str


def build_spec_evidence_trace_completeness_report(
    records: Iterable[SpecEvidenceTraceInput | dict[str, Any]],
    *,
    title: str = "Spec Evidence Trace Completeness Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    missing = [row for row in rows if row["missing_links"]]
    remediation = [row for row in rows if row["completeness_score"] < 1.0 or row["missing_links"]]
    owner_summary = _owner_summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Spec Evidence Trace Completeness Report",
        "summary": {
            "spec_count": len(rows),
            "complete_spec_count": sum(1 for row in rows if row["completeness_score"] == 1.0 and not row["missing_links"]),
            "remediation_count": len(remediation),
            "average_completeness_score": round(sum(row["completeness_score"] for row in rows) / len(rows), 4) if rows else 0.0,
        },
        "spec_completeness": rows,
        "missing_evidence_chains": missing,
        "remediation_queue": sorted(remediation, key=lambda row: (row["completeness_score"], row["owner"].lower(), row["spec_id"].lower())),
        "owner_summary": owner_summary,
    }


def render_spec_evidence_trace_completeness_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join(
        [
            f"# {report.get('title') or 'Spec Evidence Trace Completeness Report'}",
            "",
            "## Summary",
            "",
            f"- Specs: {summary.get('spec_count', 0)}",
            f"- Complete specs: {summary.get('complete_spec_count', 0)}",
            f"- Remediation queue: {summary.get('remediation_count', 0)}",
        ]
    ).rstrip() + "\n"


def render_spec_evidence_trace_completeness_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[SpecEvidenceTraceInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(records):
        units = _items(raw.get("unit_ids"))
        insights = _items(raw.get("insight_ids"))
        signals = _items(raw.get("signal_ids"))
        score = round((bool(units) + bool(insights) + bool(signals)) / 3, 4)
        rows.append(
            {
                "spec_id": _text(raw.get("spec_id")) or f"unknown-spec-{index + 1}",
                "title": _text(raw.get("title")) or "Untitled spec",
                "unit_ids": units,
                "insight_ids": insights,
                "signal_ids": signals,
                "missing_links": _items(raw.get("missing_links")),
                "generated_at": _text(raw.get("generated_at")),
                "owner": _text(raw.get("owner")) or "Unassigned",
                "completeness_score": score,
            }
        )
    rows.sort(key=lambda row: (row["completeness_score"], row["owner"].lower(), row["spec_id"].lower()))
    return rows


def _owner_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owners = sorted({row["owner"] for row in rows}, key=str.lower)
    return [
        {
            "owner": owner,
            "spec_count": sum(1 for row in rows if row["owner"] == owner),
            "remediation_count": sum(1 for row in rows if row["owner"] == owner and (row["completeness_score"] < 1.0 or row["missing_links"])),
            "average_completeness_score": round(sum(row["completeness_score"] for row in rows if row["owner"] == owner) / sum(1 for row in rows if row["owner"] == owner), 4),
        }
        for owner in owners
    ]


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, Iterable):
        parts = [_text(item) for item in value]
    else:
        parts = []
    return sorted({part for part in parts if part})


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
