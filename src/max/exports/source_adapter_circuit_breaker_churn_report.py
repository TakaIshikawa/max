"""Source adapter circuit breaker churn export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_circuit_breaker_churn_report.v1"
KIND = "max.source_adapter_circuit_breaker_churn_report"


def generate_source_adapter_circuit_breaker_churn_report(records: Iterable[dict[str, Any]], *, churn_threshold: int = 3) -> dict[str, Any]:
    threshold = max(0, _int(churn_threshold))
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        adapter = _text(raw.get("adapter") or raw.get("source_adapter") or raw.get("adapter_id")) or "unknown-adapter"
        source = _text(raw.get("source") or raw.get("signal_source") or raw.get("source_id")) or "unknown-source"
        groups.setdefault((adapter, source), []).append(raw)

    rows = []
    for (adapter, source), events in groups.items():
        states = [_state(event) for event in sorted(events, key=lambda event: _text(event.get("timestamp") or event.get("occurred_at")))]
        opened_count = sum(1 for state in states if state == "open")
        closed_count = sum(1 for state in states if state == "closed")
        reopen_count = _reopen_count(states)
        churn_score = opened_count + closed_count + reopen_count
        rows.append(
            {
                "adapter": adapter,
                "source": source,
                "opened_count": opened_count,
                "closed_count": closed_count,
                "reopen_count": reopen_count,
                "churn_score": churn_score,
                "status": "churn" if churn_score >= threshold and churn_score > 0 else "stable",
            }
        )
    rows.sort(key=lambda row: (-row["churn_score"], -row["reopen_count"], row["adapter"].lower(), row["source"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "adapter_source_count": len(rows),
            "opened_count": sum(row["opened_count"] for row in rows),
            "closed_count": sum(row["closed_count"] for row in rows),
            "reopen_count": sum(row["reopen_count"] for row in rows),
            "churn_count": sum(1 for row in rows if row["status"] == "churn"),
            "churn_threshold": threshold,
        },
        "rows": rows,
    }


def _reopen_count(states: list[str]) -> int:
    reopen_count = 0
    seen_closed = False
    for state in states:
        if state == "closed":
            seen_closed = True
        elif state == "open" and seen_closed:
            reopen_count += 1
            seen_closed = False
    return reopen_count


def _state(raw: dict[str, Any]) -> str:
    state = _text(raw.get("state") or raw.get("to_state") or raw.get("event") or raw.get("status")).lower().replace("-", "_")
    if state in {"open", "opened", "tripped", "circuit_opened", "breaker_opened"}:
        return "open"
    if state in {"closed", "close", "recovered", "reset", "circuit_closed", "breaker_closed"}:
        return "closed"
    return "other"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
