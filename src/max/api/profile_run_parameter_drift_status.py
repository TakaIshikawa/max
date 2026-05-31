"""JSON API renderer for profile run parameter drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.profile_run_parameter_drift_status.v1"
KIND = "max.api.profile_run_parameter_drift_status"
WATCHED = ("source_weights", "evaluation_weights", "budget_caps", "enabled_stages")


def profile_run_parameter_drift_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item) for item in list_of_maps(payload.get("profile_runs") or payload.get("items"))]
    rows.sort(key=lambda row: (_rank(row["severity"]), -len(row["changed_fields"]), row["profile_id"]))
    drifted = [row for row in rows if row["changed_fields"]]
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "drifted" if drifted else "ok", "profile_count": len(rows), "drifted_profile_count": len(drifted), "material_change_count": sum(len(row["changed_fields"]) for row in rows)}, "rows": rows, "drifted_profiles": drifted, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    current = item.get("current") if isinstance(item.get("current"), Mapping) else item.get("parameters") if isinstance(item.get("parameters"), Mapping) else {}
    baseline = item.get("baseline") if isinstance(item.get("baseline"), Mapping) else {}
    changed = [{"field": key, "before": baseline.get(key), "after": current.get(key)} for key in WATCHED if baseline.get(key) != current.get(key)]
    severity = "critical" if any(change["field"] in {"budget_caps", "enabled_stages"} for change in changed) else "warning" if changed else "ok"
    return {"profile_id": str(item.get("profile_id") or item.get("id") or "unknown_profile"), "changed_fields": changed, "severity": severity}


def _rank(value: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(value, 3)
