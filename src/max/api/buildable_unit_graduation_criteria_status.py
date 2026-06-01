"""JSON API renderer for buildable unit graduation criteria status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.buildable_unit_graduation_criteria_status.v1"
KIND = "max.api.buildable_unit_graduation_criteria_status"
RANK = {"blocked": 0, "rejected": 1, "review_needed": 2, "ready": 3}


def buildable_unit_graduation_criteria_status_to_json(payload: Mapping[str, Any]) -> str:
    units = [_unit(row, i) for i, row in enumerate(list_of_maps(payload.get("units") or payload.get("rows")), start=1)]
    counts = dict(sorted(Counter(row["status"] for row in units).items()))
    overall = "blocked" if counts.get("blocked") else ("review_needed" if counts.get("review_needed") or counts.get("rejected") else "ready")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": overall, "summary": {"total_units": len(units), "ready_count": counts.get("ready", 0), "blocked_count": counts.get("blocked", 0), "review_needed_count": counts.get("review_needed", 0), "rejected_count": counts.get("rejected", 0)}, "blockers": sorted([row for row in units if row["status"] == "blocked"], key=lambda row: row["unit_id"].casefold()), "units": sorted(units, key=lambda row: (RANK[row["status"]], row["unit_id"].casefold())), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _unit(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    missing = strings(item.get("missing_evidence"))
    gates = strings(item.get("unmet_gates") or item.get("blocked_gates"))
    signoffs = strings(item.get("required_signoffs") or item.get("missing_signoffs"))
    rejected = bool(item.get("rejected")) or _text(item.get("decision")).casefold() == "rejected"
    review = bool(item.get("review_needed")) or bool(signoffs)
    status = "rejected" if rejected else ("blocked" if missing or gates else ("review_needed" if review else "ready"))
    return {"unit_id": _text(item.get("unit_id") or item.get("id")) or f"unit-{index}", "profile": _text(item.get("profile")) or "default", "missing_evidence": missing, "unmet_gates": gates, "required_signoffs": signoffs, "status": status, "remediation_actions": _actions(missing, gates, signoffs, rejected)}


def _actions(missing: list[str], gates: list[str], signoffs: list[str], rejected: bool) -> list[str]:
    actions = []
    if missing:
        actions.append("attach missing graduation evidence")
    if gates:
        actions.append("satisfy unmet graduation gates")
    if signoffs:
        actions.append("collect required signoffs")
    if rejected:
        actions.append("revise rejected unit before resubmission")
    return actions or ["ready for graduation"]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
