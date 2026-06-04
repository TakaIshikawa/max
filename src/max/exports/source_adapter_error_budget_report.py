"""Source adapter error budget export report."""

from __future__ import annotations

import json
from typing import Any, Mapping

SCHEMA_VERSION = "max.source_adapter_error_budget_report.v1"
KIND = "max.source_adapter_error_budget_report"


def build_source_adapter_error_budget_report_export(
    records: list[Mapping[str, Any]],
    *,
    generated_at: str = "2026-06-01T00:00:00+00:00",
    source: str = "source_adapter_error_budget",
) -> dict[str, Any]:
    rows = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            continue
        allowed = _int(record.get("allowed_errors") or record.get("error_budget"))
        actual = _int(record.get("actual_errors") or record.get("consumed_errors") or record.get("error_count") or record.get("errors"))
        remaining = allowed - actual
        breached = actual > allowed
        adapter = _text(record.get("adapter") or record.get("source_adapter") or record.get("source")) or f"adapter-{index}"
        rows.append(
            {
                "adapter": adapter,
                "source": _text(record.get("source")) or adapter,
                "allowed_errors": allowed,
                "actual_errors": actual,
                "budget_remaining": remaining,
                "breached": breached,
                "owner": _text(record.get("owner")) or "unassigned",
                "recommended_action": _text(record.get("recommended_action")) or _action(breached, remaining),
            }
        )
    rows.sort(key=lambda row: (0 if row["breached"] else 1, row["budget_remaining"], row["adapter"].lower(), row["source"].lower()))
    breached_rows = [row for row in rows if row["breached"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
        "source": source,
        "summary": {
            "adapter_count": len(rows),
            "breached_count": len(breached_rows),
            "total_allowed_errors": sum(row["allowed_errors"] for row in rows),
            "total_actual_errors": sum(row["actual_errors"] for row in rows),
        },
        "adapter_rows": rows,
        "breached_adapters": breached_rows,
    }


def render_source_adapter_error_budget_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_adapter_error_budget_report_markdown(report: dict[str, Any]) -> str:
    rows = report.get("adapter_rows") or []
    lines = ["# Source Adapter Error Budget Report", ""]
    if not rows:
        lines.append("No source adapter error budget records supplied. No adapter error budget records supplied.")
        return "\n".join(lines).rstrip() + "\n"
    lines.extend(["| Adapter | Source | Allowed | Actual | Remaining | Status | Owner | Action |", "| --- | --- | ---: | ---: | ---: | --- | --- | --- |"])
    for row in rows:
        status = "breached" if row["breached"] else "within_budget"
        lines.append(
            f"| {row['adapter']} | {row['source']} | {row['allowed_errors']} | {row['actual_errors']} | "
            f"{row['budget_remaining']} | {status} | {row['owner']} | {row['recommended_action']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _action(breached: bool, remaining: int) -> str:
    if breached:
        return "pause ingestion and repair adapter failures"
    if remaining <= 1:
        return "monitor closely and reduce retry pressure"
    return "monitor error budget"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
