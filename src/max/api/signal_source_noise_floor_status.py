"""JSON API renderer for signal source noise floor status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.signal_source_noise_floor_status.v1"
KIND = "max.api.signal_source_noise_floor_status"


def signal_source_noise_floor_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_noise_rate"), 0.2)
    critical = _float(payload.get("critical_noise_rate"), 0.5)
    sources = [_source(row, warning, critical) for row in _items(payload)]
    sources.sort(key=lambda row: (_rank(row["status"]), row["source"]))
    summary = _summary(sources)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "sources": sources, "profile_hot_spots": _profiles(sources), "metadata": source_metadata(payload, source_count=len(sources))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("sources")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _source(row: Mapping[str, Any], warning: float, critical: float) -> dict[str, Any]:
    noisy = max(0, int_or_zero(row.get("noisy_signals")))
    accepted = max(0, int_or_zero(row.get("accepted_signals")))
    rejected = max(0, int_or_zero(row.get("rejected_signals")))
    numerator = noisy or rejected
    total = accepted + rejected + (noisy if noisy and not rejected else 0)
    rate = round(numerator / total, 4) if total else 0.0
    status = "critical" if rate >= critical else "warning" if rate >= warning else "ok"
    return {"source": _bucket(row.get("source"), "unknown_source"), "profiles": sorted(_bucket(value, "unknown_profile") for value in as_list(row.get("profiles") or row.get("profile"))), "noisy_signals": noisy, "accepted_signals": accepted, "rejected_signals": rejected, "window_hours": max(0, int_or_zero(row.get("window_hours"))), "noise_rate": rate, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "source_count": len(rows), "noisy_source_count": critical + warning, "rejected_signal_total": sum(row["rejected_signals"] for row in rows), "noisy_signal_total": sum(row["noisy_signals"] for row in rows)}


def _profiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        if row["status"] != "ok":
            for profile in row["profiles"]:
                counts[profile] += 1
    return [{"profile": profile, "noisy_source_count": count} for profile, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
