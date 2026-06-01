"""JSON API renderer for synthesis incremental watermark status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.synthesis_incremental_watermark_status.v1"
KIND = "max.api.synthesis_incremental_watermark_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def synthesis_incremental_watermark_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    lag = float_or_zero(payload.get("max_lag_hours") or payload.get("lag_threshold_hours") or 6)
    stuck = float_or_zero(payload.get("stuck_after_hours") or 24)
    sources = [_source(row, i, as_of, lag, stuck) for i, row in enumerate(list_of_maps(payload.get("sources") or payload.get("rows")), start=1)]
    blockers = [row for row in sources if row["status"] == "critical"]
    status = "critical" if blockers else ("warning" if any(row["status"] == "warning" for row in sources) else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": status, "total_sources": len(sources), "missing_watermark_count": sum(1 for row in sources if row["missing_watermark"]), "stuck_watermark_count": sum(1 for row in sources if row["stuck_watermark"]), "max_lag_hours": max([row["lag_hours"] or 0 for row in sources], default=0), "blockers": sorted(blockers, key=lambda row: row["source"].casefold()), "sources": sorted(sources, key=lambda row: (RANK[row["status"]], row["source"].casefold())), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _source(item: Mapping[str, Any], index: int, as_of: datetime, max_lag: float, stuck_after: float) -> dict[str, Any]:
    watermark = parse_datetime(item.get("watermark_at") or item.get("incremental_watermark_at"))
    latest = parse_datetime(item.get("latest_signal_at") or item.get("latest_seen_at")) or as_of
    updated = parse_datetime(item.get("watermark_updated_at") or item.get("updated_at")) or watermark
    lag_hours = round((latest - watermark).total_seconds() / 3600, 2) if watermark else None
    idle_hours = round((as_of - updated).total_seconds() / 3600, 2) if updated else None
    missing = watermark is None
    stuck = bool(item.get("stuck_watermark")) or (idle_hours is not None and idle_hours > stuck_after and (lag_hours or 0) > 0)
    status = "critical" if missing or stuck else ("warning" if lag_hours is not None and lag_hours > max_lag else "healthy")
    return {"source": _text(item.get("source") or item.get("name") or item.get("id")) or f"source-{index}", "watermark_at": item.get("watermark_at") or item.get("incremental_watermark_at"), "latest_signal_at": item.get("latest_signal_at") or item.get("latest_seen_at"), "lag_hours": lag_hours, "max_lag_hours": max_lag, "watermark_idle_hours": idle_hours, "missing_watermark": missing, "stuck_watermark": stuck, "status": status, "recommended_action": "initialize source watermark" if missing else ("unstick incremental synthesis watermark" if stuck else ("advance delayed watermark" if status == "warning" else "continue monitoring"))}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
