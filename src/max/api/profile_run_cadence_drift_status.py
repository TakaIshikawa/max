"""JSON API renderer for profile run cadence drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.profile_run_cadence_drift_status.v1"
KIND = "max.api.profile_run_cadence_drift_status"


def profile_run_cadence_drift_status_to_json(payload: Mapping[str, Any]) -> str:
    warning = float_or_zero(payload.get("warning_drift_ratio")) or 1.25
    critical = float_or_zero(payload.get("critical_drift_ratio")) or 1.75
    profiles = [_profile(row, warning, critical) for row in _items(payload)]
    profiles.sort(key=lambda row: (_rank(row["status"]), row["profile"]))
    summary = _summary(profiles)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "profiles": profiles, "metadata": source_metadata(payload, profile_count=len(profiles))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("profiles")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _profile(row: Mapping[str, Any], warning: float, critical: float) -> dict[str, Any]:
    expected = max(0.0, float_or_zero(row.get("expected_interval_hours")))
    actual = max(0.0, float_or_zero(row.get("actual_interval_hours")))
    drift_ratio = round(actual / expected, 4) if expected else (1.0 if actual else 0.0)
    status = "critical" if drift_ratio >= critical else "warning" if drift_ratio >= warning else "ok"
    return {"profile": _bucket(row.get("profile"), "unknown_profile"), "run_cadence": str(row.get("run_cadence") or "unknown"), "expected_interval_hours": expected, "actual_interval_hours": actual, "drift_ratio": drift_ratio, "last_run_at": row.get("last_run_at"), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "profile_count": len(rows), "affected_profile_count": critical + warning, "critical_count": critical, "warning_count": warning}


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
