"""JSON API renderer for source adapter stale credential status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_stale_credential_status.v1"
KIND = "max.api.source_adapter_stale_credential_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def source_adapter_stale_credential_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    max_age_days = float_or_zero(payload.get("credential_max_age_days") or payload.get("max_age_days") or 90)
    adapters = [_adapter(row, i, as_of, max_age_days) for i, row in enumerate(list_of_maps(payload.get("adapters") or payload.get("rows")), start=1)]
    stale = [row for row in adapters if row["credential_stale"]]
    missing = [row for row in adapters if row["missing_validation_evidence"]]
    blockers = sorted([row for row in adapters if row["status"] == "critical"], key=lambda row: row["adapter"].casefold())
    status = "critical" if blockers else ("warning" if stale or missing else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": status, "total_adapters": len(adapters), "stale_credential_count": len(stale), "missing_validation_count": len(missing), "stale_adapters": sorted(stale, key=lambda row: row["adapter"].casefold()), "missing_validation_blockers": blockers, "recommended_actions": _actions(stale, missing), "adapters": sorted(adapters, key=lambda row: (RANK[row["status"]], row["adapter"].casefold())), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _adapter(item: Mapping[str, Any], index: int, as_of: datetime, max_age_days: float) -> dict[str, Any]:
    validated_at = parse_datetime(item.get("last_validated_at") or item.get("validated_at") or item.get("last_validation_at"))
    rotated_at = parse_datetime(item.get("credential_rotated_at") or item.get("rotated_at") or item.get("issued_at"))
    age_days = round((as_of - rotated_at).total_seconds() / 86400, 2) if rotated_at else None
    validation_age_days = round((as_of - validated_at).total_seconds() / 86400, 2) if validated_at else None
    stale = age_days is None or age_days > max_age_days
    validation_status = _text(item.get("validation_status")).casefold()
    missing_validation = validated_at is None or validation_status in {"missing", "unknown", "failed"}
    status = "critical" if stale or missing_validation else "healthy"
    return {"adapter": _text(item.get("adapter") or item.get("source") or item.get("name") or item.get("id")) or f"adapter-{index}", "credential_id": _text(item.get("credential_id") or item.get("credential_name")) or "default", "credential_rotated_at": item.get("credential_rotated_at") or item.get("rotated_at") or item.get("issued_at"), "credential_age_days": age_days, "max_age_days": max_age_days, "last_validated_at": item.get("last_validated_at") or item.get("validated_at") or item.get("last_validation_at"), "validation_age_days": validation_age_days, "validation_status": _text(item.get("validation_status")) or ("validated" if validated_at else "missing"), "credential_stale": stale, "missing_validation_evidence": missing_validation, "status": status, "recommended_action": "rotate credential and record validation evidence" if stale and missing_validation else ("rotate credential" if stale else ("record validation evidence" if missing_validation else "continue monitoring"))}


def _actions(stale: list[Mapping[str, Any]], missing: list[Mapping[str, Any]]) -> list[str]:
    actions: list[str] = []
    if stale:
        actions.append("rotate stale adapter credentials")
    if missing:
        actions.append("capture credential validation evidence")
    return actions or ["continue monitoring"]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
