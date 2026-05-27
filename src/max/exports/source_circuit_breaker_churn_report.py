"""Source circuit breaker churn export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_circuit_breaker_churn_report.v1"
KIND = "max.source_circuit_breaker_churn_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_circuit_breaker_churn_report(records: Iterable[dict[str, Any]], *, repeated_open_threshold: int = 2, title: str = "Source Circuit Breaker Churn Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in records:
        if isinstance(raw, dict):
            groups[(_text(raw.get("source")) or "unknown-source", _text(raw.get("adapter")) or "unknown-adapter")].append(raw)
    rows = []
    for (source, adapter), items in groups.items():
        events = sorted(items, key=lambda e: _text(e.get("timestamp")))
        opens = [e for e in events if _state(e) == "open"]
        recoveries = _recoveries(events)
        mean = round(sum(recoveries) / len(recoveries), 2) if recoveries else 0.0
        repeated = len(opens) >= repeated_open_threshold
        rows.append({"source": source, "adapter": adapter, "state_transitions": [_state(e) for e in events], "opens_per_window": len(opens), "mean_recovery_time_minutes": mean, "repeated_open": repeated, "stability_recommendation": "investigate unstable upstream or adapter retries" if repeated else "continue monitoring"})
    rows.sort(key=lambda r: (-r["opens_per_window"], r["source"].lower(), r["adapter"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Source Circuit Breaker Churn Report", "summary": {"adapter_count": len(rows), "open_count": sum(r["opens_per_window"] for r in rows), "repeated_open_count": sum(1 for r in rows if r["repeated_open"])}, "churn_rows": rows}


def render_source_circuit_breaker_churn_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_circuit_breaker_churn_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Circuit Breaker Churn Report'}", "", "## Circuit Breaker Churn", ""]
    lines.extend([f"- {r['source']} / {r['adapter']}: {r['opens_per_window']} opens, repeated={r['repeated_open']}" for r in report.get("churn_rows") or []] or ["- No circuit breaker churn detected."])
    return "\n".join(lines).rstrip() + "\n"


def _recoveries(events: list[dict[str, Any]]) -> list[float]:
    durations = []
    opened_at: datetime | None = None
    for event in events:
        state = _state(event)
        if state == "open":
            opened_at = _parse(_text(event.get("timestamp")))
        elif state == "closed" and opened_at is not None:
            durations.append(round((_parse(_text(event.get("timestamp"))) - opened_at).total_seconds() / 60, 2))
            opened_at = None
    return durations


def _state(raw: dict[str, Any]) -> str:
    state = _text(raw.get("state") or raw.get("to_state")).lower().replace("-", "_")
    return "open" if state in {"open", "tripped"} else "half_open" if state in {"half_open", "recovering"} else "closed"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
