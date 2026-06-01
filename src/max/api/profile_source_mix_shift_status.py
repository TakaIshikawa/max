"""JSON API renderer for profile source mix shift status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.profile_source_mix_shift_status.v1"
KIND = "max.api.profile_source_mix_shift_status"


def profile_source_mix_shift_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = _float(payload.get("warning_max_shift"), 0.15)
    critical = _float(payload.get("critical_max_shift"), 0.3)
    profiles = _profiles(payload)
    rows = [_profile(name, data, warning, critical) for name, data in profiles.items()]
    rows.sort(key=lambda row: (-row["max_shift"], row["profile"]))
    max_shift = rows[0]["max_shift"] if rows else 0.0
    status = "critical" if max_shift >= critical else ("warning" if max_shift >= warning else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "profile_count": len(rows), "max_observed_shift": max_shift, "most_shifted_profile": rows[0]["profile"] if rows else None}, "profiles": rows, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profiles(payload: Mapping[str, Any]) -> dict[str, dict[str, dict[str, int]]]:
    grouped: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: {"current": {}, "baseline": {}})
    for row in list_of_maps(payload.get("profiles")):
        profile = _text(row.get("profile") or row.get("name") or "default")
        grouped[profile]["current"].update(_counts(row.get("current") or row.get("current_sources")))
        grouped[profile]["baseline"].update(_counts(row.get("baseline") or row.get("baseline_sources")))
    for row in list_of_maps(payload.get("current") or payload.get("current_sources")):
        grouped[_text(row.get("profile") or "default")]["current"][_text(row.get("source") or "unknown")] = max(0, int_or_zero(row.get("count") or row.get("signals")))
    for row in list_of_maps(payload.get("baseline") or payload.get("baseline_sources")):
        grouped[_text(row.get("profile") or "default")]["baseline"][_text(row.get("source") or "unknown")] = max(0, int_or_zero(row.get("count") or row.get("signals")))
    return dict(grouped)


def _counts(value: Any) -> dict[str, int]:
    if isinstance(value, Mapping):
        return {_text(key): max(0, int_or_zero(count)) for key, count in value.items()}
    return {_text(row.get("source") or "unknown"): max(0, int_or_zero(row.get("count") or row.get("signals"))) for row in list_of_maps(value)}


def _profile(profile: str, data: dict[str, dict[str, int]], warning: float, critical: float) -> dict[str, Any]:
    current = data["current"]
    baseline = data["baseline"]
    current_total = sum(current.values())
    baseline_total = sum(baseline.values())
    rows = []
    for source in sorted(set(current) | set(baseline)):
        current_share = round(current.get(source, 0) / current_total, 4) if current_total else 0.0
        baseline_share = round(baseline.get(source, 0) / baseline_total, 4) if baseline_total else 0.0
        shift = round(abs(current_share - baseline_share), 4)
        direction = "overrepresented" if current_share > baseline_share else ("underrepresented" if baseline_share > current_share else "balanced")
        if source not in baseline:
            direction = "missing_baseline"
        elif source not in current:
            direction = "missing_current"
        rows.append({"source": source, "current_count": current.get(source, 0), "baseline_count": baseline.get(source, 0), "current_share": current_share, "baseline_share": baseline_share, "shift": shift, "direction": direction})
    rows.sort(key=lambda row: (-row["shift"], row["source"]))
    max_shift = rows[0]["shift"] if rows else 0.0
    status = "critical" if max_shift >= critical else ("warning" if max_shift >= warning else "healthy")
    return {"profile": profile, "status": status, "current_total": current_total, "baseline_total": baseline_total, "max_shift": max_shift, "sources": rows, "overrepresented_sources": [row for row in rows if row["direction"] in {"overrepresented", "missing_baseline"}], "underrepresented_sources": [row for row in rows if row["direction"] in {"underrepresented", "missing_current"}]}


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

