"""JSON API renderer for spec publication readiness status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import bool_or_default, list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.spec_publication_readiness_status.v1"
KIND = "max.api.spec_publication_readiness_status"


def spec_publication_readiness_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_spec(row, i) for i, row in enumerate(list_of_maps(payload.get("specs") or payload.get("rows")), start=1)]
    blocked = [row for row in rows if row["status"] == "blocked"]
    ready = len(rows) - len(blocked)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "ready_count": ready, "blocked_count": len(blocked), "readiness_rate": round(ready / len(rows), 4) if rows else 0.0, "blockers_by_reason": dict(sorted(Counter(reason for row in blocked for reason in row["blockers"]).items())), "blocked_specs": sorted(blocked, key=lambda row: (-len(row["blockers"]), row["created_at"] or "", row["spec_id"])), "top_blockers": _top(blocked), "overall_status": "blocked" if blocked else "ready", "specs": rows, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _spec(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    blockers = strings(item.get("blockers") or item.get("unresolved_blockers"))
    if not bool_or_default(item.get("has_evidence"), default=bool(item.get("evidence"))):
        blockers.append("missing_evidence")
    if bool_or_default(item.get("stale_evaluation"), default=False):
        blockers.append("stale_evaluation")
    if not bool_or_default(item.get("destination_eligible"), default=True):
        blockers.append("destination_ineligible")
    blockers = sorted(set(blockers))
    return {"spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}", "destination": _text(item.get("destination")) or "default", "created_at": item.get("created_at"), "evaluation_at": item.get("evaluation_at"), "evaluation_timestamp": parse_datetime(item.get("evaluation_at")).isoformat() if parse_datetime(item.get("evaluation_at")) else None, "blockers": blockers, "status": "blocked" if blockers else "ready"}


def _top(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(reason for row in rows for reason in row["blockers"])
    return [{"reason": reason, "count": count} for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
