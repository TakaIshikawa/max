"""JSON API renderer for signal source noise status."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from max.api._renderer_utils import bool_or_default, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.signal_source_noise_status.v1"
KIND = "max.api.signal_source_noise_status"
STATUS_RANK = {"unusable": 0, "noisy": 1, "clean": 2}


def signal_source_noise_status_to_json(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]], *, noisy_threshold: float = 20.0, unusable_threshold: float = 50.0) -> str:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _items(payload):
        key = (_text(item.get("source")) or "unknown", _text(item.get("profile")) or "default")
        group = groups.setdefault(key, {"source": key[0], "profile": key[1], "total_signals": 0, "noisy_signals": 0, "duplicate_signals": 0})
        count = max(1, int_or_zero(item.get("signal_count", item.get("count"))) or 1)
        group["total_signals"] += count
        if bool_or_default(item.get("noisy", item.get("is_noisy")), default=False):
            group["noisy_signals"] += count
        if bool_or_default(item.get("duplicate", item.get("is_duplicate")), default=False):
            group["duplicate_signals"] += count
    rows = [_finish_group(group, noisy_threshold, unusable_threshold) for group in groups.values()]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["source"], row["profile"]))
    metadata = source_metadata(payload if isinstance(payload, Mapping) else {}, group_count=len(rows))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "sources": rows, "metadata": metadata}, indent=2, sort_keys=True)


def _finish_group(group: dict[str, Any], noisy_threshold: float, unusable_threshold: float) -> dict[str, Any]:
    noise_rate = round((group["noisy_signals"] / group["total_signals"]) * 100, 2) if group["total_signals"] else 0.0
    duplicate_rate = round((group["duplicate_signals"] / group["total_signals"]) * 100, 2) if group["total_signals"] else 0.0
    worst_rate = max(noise_rate, duplicate_rate)
    status = "unusable" if worst_rate >= unusable_threshold else "noisy" if worst_rate >= noisy_threshold else "clean"
    return {**group, "noise_rate": noise_rate, "duplicate_rate": duplicate_rate, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(row["total_signals"] for row in rows)
    noisy = sum(row["noisy_signals"] for row in rows)
    duplicate = sum(row["duplicate_signals"] for row in rows)
    return {"status": "unusable" if any(row["status"] == "unusable" for row in rows) else "noisy" if any(row["status"] == "noisy" for row in rows) else "clean", "group_count": len(rows), "total_signals": total, "noisy_signals": noisy, "duplicate_signals": duplicate, "noise_rate": round((noisy / total) * 100, 2) if total else 0.0, "duplicate_rate": round((duplicate / total) * 100, 2) if total else 0.0}


def _items(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        return list_of_maps(payload.get("samples") or payload.get("signals") or payload.get("rows") or payload.get("items"))
    return [item for item in payload if isinstance(item, Mapping)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
