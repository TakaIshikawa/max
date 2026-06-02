"""JSON API renderer for buildable unit owner assignment status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_owner_assignment_status.v1"
KIND = "max.api.buildable_unit_owner_assignment_status"


def buildable_unit_owner_assignment_status_to_json(payload: Mapping[str, Any]) -> str:
    units = [_unit(row) for row in _items(payload)]
    units.sort(key=lambda row: (_rank(row["status"]), row["profile"], row["unit_id"]))
    high = sum(1 for row in units if row["status"] == "critical")
    approved = sum(1 for row in units if row["unassigned"] and row["unit_status"] == "approved")
    pending = sum(1 for row in units if row["unassigned"] and row["unit_status"] != "approved")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": "critical" if high else "warning" if approved or pending else "ok", "summary": {"unit_count": len(units), "unassigned_approved_count": approved, "unassigned_pending_count": pending, "high_priority_unassigned_approved_count": high}, "gaps_by_profile": _gaps(units), "units": units, "metadata": source_metadata(payload, unit_count=len(units))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("units")) or list_of_maps(payload.get("items"))


def _unit(row: Mapping[str, Any]) -> dict[str, Any]:
    owner = _text(row.get("owner"))
    unit_status = _bucket(row.get("status"), "unknown")
    priority = _bucket(row.get("priority"), "normal")
    unassigned = not owner
    status = "critical" if unassigned and unit_status == "approved" and priority in {"high", "p0", "p1"} else "warning" if unassigned else "ok"
    return {"unit_id": _text(row.get("unit_id") or row.get("id")) or "unknown_unit", "profile": _bucket(row.get("profile"), "unknown_profile"), "owner": owner or None, "unit_status": unit_status, "generated_at": _text(row.get("generated_at")) or None, "priority": priority, "unassigned": unassigned, "status": status}


def _gaps(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["profile"] for row in units if row["unassigned"])
    return [{"profile": profile, "unassigned_count": count} for profile, count in sorted(counts.items())]


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
