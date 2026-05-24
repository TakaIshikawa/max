"""Adapter circuit breaker recovery export report."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.adapter_circuit_breaker_recovery_report.v1"
KIND = "max.adapter_circuit_breaker_recovery_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"

STATE_SEVERITY = {"open": 0, "tripped": 0, "half_open": 1, "half-open": 1, "recovering": 1, "closed": 3, "healthy": 3}


class AdapterCircuitBreakerInput(TypedDict, total=False):
    adapter: str
    source: str
    state: str
    opened_at: str
    half_opened_at: str
    recovery_latency_seconds: int | float | str
    failed_probe_count: int | float | str
    requires_operator_action: bool
    action_required: bool
    reason: str


def build_adapter_circuit_breaker_recovery_report(
    records: Iterable[AdapterCircuitBreakerInput | dict[str, Any]] | dict[str, Any],
    *,
    title: str = "Adapter Circuit Breaker Recovery Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    failed_probe_action_threshold: int = 3,
) -> dict[str, Any]:
    adapters = _normalize_adapters(records, failed_probe_action_threshold=failed_probe_action_threshold)
    recovery_actions = [row for row in adapters if row["requires_operator_action"]]
    recovery_actions.sort(key=_sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Adapter Circuit Breaker Recovery Report",
        "summary": _summary(adapters, recovery_actions),
        "adapter_states": adapters,
        "recovery_actions": recovery_actions,
        "state_totals": _state_totals(adapters),
    }


def render_adapter_circuit_breaker_recovery_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Adapter Circuit Breaker Recovery Report'}",
        "",
        "## Summary",
        "",
        f"- Adapters: {summary.get('adapter_count', 0)}",
        f"- Open adapters: {summary.get('open_count', 0)}",
        f"- Half-open adapters: {summary.get('half_open_count', 0)}",
        f"- Requiring action: {summary.get('requires_action_count', 0)}",
        f"- Failed probes: {summary.get('failed_probe_count', 0)}",
        "",
        "## Recovery Actions",
        "",
    ]
    actions = report.get("recovery_actions") or []
    if actions:
        for row in actions:
            lines.append(
                f"- ACTION REQUIRED: {row['adapter']} / {row['source']} is {row['state']} "
                f"after {row['failed_probe_count']} failed probes ({row['action']})"
            )
    else:
        lines.append("- No adapters require operator action.")
    return "\n".join(lines).rstrip() + "\n"


def render_adapter_circuit_breaker_recovery_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_adapters(records: Iterable[dict[str, Any]] | dict[str, Any], *, failed_probe_action_threshold: int) -> list[dict[str, Any]]:
    if isinstance(records, dict):
        source = records.get("adapter_states") or records.get("adapters") or records.get("circuit_breakers") or []
    else:
        source = records
    rows = [_adapter_row(item, index, failed_probe_action_threshold) for index, item in enumerate(source if isinstance(source, list) else list(source), start=1) if isinstance(item, dict)]
    if not rows:
        rows.append(_adapter_row({}, 1, failed_probe_action_threshold))
    rows.sort(key=_sort_key)
    return rows


def _adapter_row(raw: dict[str, Any], index: int, failed_probe_action_threshold: int) -> dict[str, Any]:
    state = _state(raw.get("state") or raw.get("circuit_state"))
    failed_probes = _int(raw.get("failed_probe_count", raw.get("failed_probes")))
    explicit_action = raw.get("requires_operator_action", raw.get("action_required"))
    needs_action = _bool(explicit_action) if explicit_action is not None else state in {"open", "tripped"} or failed_probes >= failed_probe_action_threshold
    adapter = _text(raw.get("adapter") or raw.get("adapter_name")) or f"adapter-{index}"
    source = _text(raw.get("source") or raw.get("source_id")) or "unknown-source"
    return {
        "adapter": adapter,
        "source": source,
        "state": state,
        "severity": _severity(state, needs_action),
        "opened_at": _text(raw.get("opened_at") or raw.get("last_opened_at")),
        "half_opened_at": _text(raw.get("half_opened_at") or raw.get("half_open_at")),
        "recent_transition": _text(raw.get("recent_transition") or raw.get("transition")) or _recent_transition(state),
        "recovery_latency_seconds": _float(raw.get("recovery_latency_seconds", raw.get("recovery_latency_ms", 0))) / (1000 if raw.get("recovery_latency_ms") is not None and raw.get("recovery_latency_seconds") is None else 1),
        "failed_probe_count": failed_probes,
        "requires_operator_action": needs_action,
        "action": _text(raw.get("action") or raw.get("next_action")) or _action(state, failed_probes, needs_action),
        "reason": _text(raw.get("reason") or raw.get("error")),
    }


def _summary(rows: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "adapter_count": len(rows),
        "open_count": sum(1 for row in rows if row["state"] in {"open", "tripped"}),
        "half_open_count": sum(1 for row in rows if row["state"] == "half_open"),
        "closed_count": sum(1 for row in rows if row["state"] == "closed"),
        "requires_action_count": len(actions),
        "failed_probe_count": sum(row["failed_probe_count"] for row in rows),
        "average_recovery_latency_seconds": round(sum(row["recovery_latency_seconds"] for row in rows) / len(rows), 4) if rows else 0.0,
    }


def _state_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["state"] for row in rows)
    return [{"state": state, "count": count} for state, count in sorted(counts.items())]


def _sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row["severity"], row["adapter"].lower(), row["source"].lower())


def _state(value: Any) -> str:
    state = _text(value).lower().replace("-", "_").replace(" ", "_")
    if state in {"open", "tripped", "half_open", "recovering", "closed", "healthy"}:
        return "closed" if state == "healthy" else state
    return "closed"


def _severity(state: str, needs_action: bool) -> int:
    if needs_action:
        return -1
    return STATE_SEVERITY.get(state, 2)


def _recent_transition(state: str) -> str:
    return "opened" if state in {"open", "tripped"} else "half_opened" if state == "half_open" else "none"


def _action(state: str, failed_probes: int, needs_action: bool) -> str:
    if not needs_action:
        return "continue monitoring"
    if state == "half_open":
        return "inspect failed recovery probes"
    if failed_probes:
        return "reset adapter after dependency validation"
    return "confirm upstream recovery before closing breaker"


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _float(value: Any) -> float:
    try:
        return round(max(0.0, float(value or 0)), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
