"""JSON API renderer for profile evaluation weight drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, source_metadata

SCHEMA_VERSION = "max.api.profile_evaluation_weight_drift_status.v1"
KIND = "max.api.profile_evaluation_weight_drift_status"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def profile_evaluation_weight_drift_status_to_json(payload: Mapping[str, Any]) -> str:
    profiles = _profiles(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(profiles), "profiles": profiles, "metadata": source_metadata(payload, profile_count=len(profiles))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profiles(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    rows = []
    for index, item in enumerate(source, start=1):
        if not isinstance(item, Mapping):
            continue
        dimensions = _dimensions(item)
        rows.append({"profile": _text(item.get("profile") or item.get("name")) or f"profile-{index}", "severity": min((row["severity"] for row in dimensions), key=lambda value: SEVERITY_RANK[value], default="ok"), "dimensions": dimensions})
    return sorted(rows, key=lambda row: (SEVERITY_RANK[row["severity"]], row["profile"]))


def _dimensions(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    baseline = item.get("baseline_weights") if isinstance(item.get("baseline_weights"), Mapping) else {}
    active = item.get("active_weights") if isinstance(item.get("active_weights"), Mapping) else item.get("weights")
    active = active if isinstance(active, Mapping) else {}
    rows = []
    for dimension in sorted(set(baseline) | set(active), key=str):
        base = float_or_zero(baseline.get(dimension))
        current = float_or_zero(active.get(dimension))
        missing_baseline = dimension not in baseline
        absolute = round(abs(current - base), 4)
        percent = round((absolute / base * 100) if base else (100.0 if current else 0.0), 2)
        severity = "warn" if missing_baseline else ("critical" if absolute >= 0.25 or percent >= 50 else ("warn" if absolute >= 0.1 or percent >= 20 else "ok"))
        rows.append({"dimension": str(dimension), "baseline_weight": round(base, 4) if not missing_baseline else None, "active_weight": round(current, 4), "absolute_drift": absolute, "percentage_drift": percent, "missing_baseline": missing_baseline, "severity": severity})
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"profile_count": len(rows), "severity": min((row["severity"] for row in rows), key=lambda value: SEVERITY_RANK[value], default="ok"), "drifted_profile_count": sum(1 for row in rows if row["severity"] != "ok")}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
