"""Source adapter reliability export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.source_adapter_reliability.v1"
KIND = "max.source_adapter_reliability"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"

_FAIL_STATUSES = {"failed", "error", "timeout", "cancelled"}
_SUCCESS_STATUSES = {"success", "succeeded", "completed", "ok"}
_OPEN_BREAKERS = {"open", "tripped"}


class SourceAdapterRunInput(TypedDict, total=False):
    source: str
    source_name: str
    name: str
    status: str
    started_at: str
    finished_at: str
    completed_at: str
    item_count: int | float | str
    error: str
    circuit_breaker_state: str


def build_source_adapter_reliability_report(
    records: Iterable[SourceAdapterRunInput | dict[str, Any]],
    *,
    title: str = "Source Adapter Reliability Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    per_source = _per_source(rows)
    failing_sources = [row for row in per_source if row["failure_count"] > 0]
    open_circuit_breakers = [
        {
            "source": row["source"],
            "circuit_breaker_state": row["circuit_breaker_state"],
            "last_error": row["last_error"],
        }
        for row in per_source
        if row["open_circuit_breaker"]
    ]
    recent_errors = _recent_errors(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Source Adapter Reliability Report",
        "summary": _summary(rows, failing_sources, open_circuit_breakers),
        "per_source": per_source,
        "failing_sources": failing_sources,
        "open_circuit_breakers": open_circuit_breakers,
        "recent_errors": recent_errors,
    }


def render_source_adapter_reliability_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Source Adapter Reliability Report'}",
        "",
        "## Summary",
        "",
        f"- Adapter runs: {summary.get('run_count', 0)}",
        f"- Successful runs: {summary.get('success_count', 0)}",
        f"- Failed runs: {summary.get('failure_count', 0)}",
        f"- Success rate: {summary.get('success_rate', 0.0)}",
        f"- Average item count: {summary.get('average_item_count', 0.0)}",
        f"- Failing sources: {summary.get('failing_source_count', 0)}",
        f"- Open circuit breakers: {summary.get('open_circuit_breaker_count', 0)}",
        "",
        "## Failing Sources",
        "",
    ]
    if report.get("failing_sources"):
        for row in report["failing_sources"]:
            lines.append(f"- {row['source']}: {row['failure_count']} failure(s), success rate {row['success_rate']}")
    else:
        lines.append("- No failing sources detected.")
    lines.extend(["", "## Open Circuit Breakers", ""])
    if report.get("open_circuit_breakers"):
        for row in report["open_circuit_breakers"]:
            lines.append(f"- {row['source']}: {row['circuit_breaker_state']}")
    else:
        lines.append("- No open circuit breakers.")
    return "\n".join(lines).rstrip() + "\n"


def render_source_adapter_reliability_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[SourceAdapterRunInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(records):
        status = _status(raw.get("status"))
        error = _text(raw.get("error"))
        rows.append(
            {
                "source": _text(raw.get("source") or raw.get("source_name") or raw.get("name")) or "Unknown source",
                "status": status,
                "started_at": _text(raw.get("started_at")),
                "finished_at": _text(raw.get("finished_at") or raw.get("completed_at")),
                "item_count": _int(raw.get("item_count")),
                "error": error,
                "circuit_breaker_state": _breaker(raw.get("circuit_breaker_state")),
                "failed": status in _FAIL_STATUSES or bool(error),
                "succeeded": status in _SUCCESS_STATUSES,
                "_input_order": index,
            }
        )
    rows.sort(key=lambda row: (row["source"].lower(), row["started_at"] or "9999-12-31", row["_input_order"]))
    for row in rows:
        row.pop("_input_order", None)
    return rows


def _per_source(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["source"]].append(row)
    output = []
    for source, items in grouped.items():
        successes = sum(1 for row in items if row["succeeded"] and not row["failed"])
        failures = sum(1 for row in items if row["failed"])
        last_error = sorted((row for row in items if row["error"]), key=lambda row: (row["started_at"], row["finished_at"]))[-1]["error"] if any(row["error"] for row in items) else ""
        breaker_state = sorted({row["circuit_breaker_state"] for row in items if row["circuit_breaker_state"] != "closed"})[0] if any(row["circuit_breaker_state"] != "closed" for row in items) else "closed"
        output.append(
            {
                "source": source,
                "run_count": len(items),
                "success_count": successes,
                "failure_count": failures,
                "success_rate": _rate(successes, len(items)),
                "average_item_count": _avg(row["item_count"] for row in items),
                "last_started_at": max((row["started_at"] for row in items if row["started_at"]), default=""),
                "last_error": last_error,
                "circuit_breaker_state": breaker_state,
                "open_circuit_breaker": breaker_state in _OPEN_BREAKERS,
            }
        )
    output.sort(key=lambda row: (-row["failure_count"], row["source"].lower()))
    return output


def _summary(rows: list[dict[str, Any]], failing: list[dict[str, Any]], open_breakers: list[dict[str, Any]]) -> dict[str, Any]:
    successes = sum(1 for row in rows if row["succeeded"] and not row["failed"])
    failures = sum(1 for row in rows if row["failed"])
    return {
        "run_count": len(rows),
        "source_count": len({row["source"] for row in rows}),
        "success_count": successes,
        "failure_count": failures,
        "success_rate": _rate(successes, len(rows)),
        "average_item_count": _avg(row["item_count"] for row in rows),
        "failing_source_count": len(failing),
        "open_circuit_breaker_count": len(open_breakers),
    }


def _recent_errors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors = [
        {
            "source": row["source"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "error": row["error"] or "Adapter run failed without an error message",
            "circuit_breaker_state": row["circuit_breaker_state"],
        }
        for row in rows
        if row["failed"]
    ]
    errors.sort(key=lambda row: (row["started_at"] or "", row["source"].lower(), row["error"]), reverse=True)
    return errors


def _status(value: Any) -> str:
    text = _text(value).lower().replace("_", " ")
    return text or "unknown"


def _breaker(value: Any) -> str:
    text = _text(value).lower().replace("_", " ")
    return text if text in {"closed", "half open", "open", "tripped"} else "closed"


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _avg(values: Iterable[int]) -> float:
    items = list(values)
    return round(sum(items) / len(items), 2) if items else 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
