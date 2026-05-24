"""JSON API renderer for feedback learning conflicts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.feedback_learning_conflict.v1"
KIND = "max.api.feedback_learning_conflict"


def feedback_learning_conflict_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    signals = _signals(payload)
    groups = _conflicts(signals)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(groups, signals),
        "signals": signals,
        "conflict_groups": groups,
        "dimension_totals": _dimension_totals(groups, signals),
        "metadata": _metadata(payload, signals, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _signals(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("signals") if isinstance(payload.get("signals"), list) else payload.get("feedback")
    rows = [_signal(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (row["idea_id"], row["profile"], row["dimension"], row["outcome"], row["signal_id"]))
    return rows


def _signal(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {"signal_id": _text(item.get("signal_id") or item.get("id")) or f"signal-{index}", "idea_id": _text(item.get("idea_id") or item.get("idea")) or "unknown-idea", "profile": _bucket(item.get("profile"), "unknown-profile"), "dimension": _bucket(item.get("dimension"), "overall"), "outcome": _outcome(item.get("outcome") or item.get("decision")), "resolved": _bool(item.get("resolved"))}


def _conflicts(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in signals:
        grouped[(row["idea_id"], row["profile"], row["dimension"])].append(row)
    rows = []
    for (idea_id, profile, dimension), items in grouped.items():
        outcomes = {row["outcome"] for row in items}
        if {"approve", "reject"} <= outcomes:
            unresolved = [row for row in items if not row["resolved"]]
            rows.append({"idea_id": idea_id, "profile": profile, "dimension": dimension, "signal_ids": [row["signal_id"] for row in items], "outcomes": sorted(outcomes), "resolved": not unresolved, "unresolved_count": len(unresolved), "severity": "severe" if len(unresolved) >= 3 else "conflicted"})
    rows.sort(key=lambda row: (row["resolved"], -row["unresolved_count"], row["idea_id"], row["profile"], row["dimension"]))
    return rows


def _summary(groups: list[dict[str, Any]], signals: list[dict[str, Any]]) -> dict[str, Any]:
    unresolved = sum(1 for row in groups if not row["resolved"])
    severe = sum(1 for row in groups if row["severity"] == "severe" and not row["resolved"])
    status = "severe" if severe else ("conflicted" if unresolved else "clean")
    return {"status": status, "signal_count": len(signals), "conflict_group_count": len(groups), "unresolved_count": unresolved, "resolved_conflict_count": sum(1 for row in groups if row["resolved"])}


def _dimension_totals(groups: list[dict[str, Any]], signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signal_counts = Counter(row["dimension"] for row in signals)
    conflict_counts = Counter(row["dimension"] for row in groups)
    unresolved_counts = Counter(row["dimension"] for row in groups if not row["resolved"])
    rows = [{"dimension": dimension, "signal_count": count, "conflict_count": conflict_counts[dimension], "unresolved_count": unresolved_counts[dimension]} for dimension, count in signal_counts.items()]
    rows.sort(key=lambda row: (-row["unresolved_count"], row["dimension"]))
    return rows


def _metadata(payload: Mapping[str, Any], signals: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "signal_count": len(signals)}


def _outcome(value: Any) -> str:
    text = _bucket(value, "neutral")
    if text in {"approved", "accept", "accepted", "positive"}:
        return "approve"
    if text in {"rejected", "deny", "denied", "negative"}:
        return "reject"
    return text


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
