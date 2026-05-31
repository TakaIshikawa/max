"""JSON API renderer for tact spec export readiness status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.tact_spec_export_readiness_status.v1"
KIND = "max.api.tact_spec_export_readiness_status"
REQUIRED = ("evaluation", "evidence", "acceptance_criteria")


def tact_spec_export_readiness_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item) for item in list_of_maps(payload.get("candidates") or payload.get("specs") or payload.get("items")) if _status(item) == "approved"]
    rows.sort(key=lambda row: (row["severity"] != "blocked", row["idea_id"]))
    ready = [row for row in rows if row["ready"]]
    blocked = [row for row in rows if not row["ready"]]
    categories = Counter(blocker for row in blocked for blocker in row["blockers"])
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "blocked" if blocked else "ready", "candidate_count": len(rows), "ready_count": len(ready), "blocked_count": len(blocked), "blocker_categories": dict(sorted(categories.items()))}, "rows": rows, "ready_candidates": ready, "blocked_candidates": blocked, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    blockers = [name for name in REQUIRED if not _present(item, name)]
    return {"idea_id": str(item.get("idea_id") or item.get("id") or "unknown_idea"), "spec_id": item.get("spec_id"), "blockers": blockers, "ready": not blockers, "severity": "blocked" if blockers else "ready", "recommended_action": "complete_" + blockers[0] if blockers else "export_tact_spec"}


def _present(item: Mapping[str, Any], key: str) -> bool:
    value = item.get(key) or item.get(f"{key}_complete") or item.get(f"has_{key}")
    return bool(value)


def _status(item: Mapping[str, Any]) -> str:
    return str(item.get("status") or item.get("idea_status") or "").lower()
