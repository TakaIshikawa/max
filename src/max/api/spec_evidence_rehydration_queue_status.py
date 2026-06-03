"""JSON API renderer for spec evidence rehydration queue status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.spec_evidence_rehydration_queue_status.v1"
KIND = "max.api.spec_evidence_rehydration_queue_status"


def spec_evidence_rehydration_queue_status_to_json(payload: Mapping[str, Any]) -> str:
    warning_age = max(0, int_or_zero(payload.get("warning_age_hours"))) or 24
    critical_age = max(0, int_or_zero(payload.get("critical_age_hours"))) or 72
    max_attempts = max(1, int_or_zero(payload.get("max_attempts")) or 3)
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    specs = [_spec(row, warning_age, critical_age, max_attempts, as_of) for row in _items(payload)]
    specs.sort(key=lambda row: (_rank(row["status"]), row["spec_id"]))
    summary = _summary(specs)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "specs": specs, "metadata": source_metadata(payload, queued_count=len(specs))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("specs")) or list_of_maps(payload.get("items")) or list_of_maps(payload.get("rows"))


def _spec(row: Mapping[str, Any], warning_age: int, critical_age: int, max_attempts: int, as_of: datetime) -> dict[str, Any]:
    queued_at = parse_datetime(row.get("queued_at"))
    age = round(max((as_of - queued_at).total_seconds() / 3600, 0), 2) if queued_at else None
    attempts = max(0, int_or_zero(row.get("attempts")))
    retry_exhausted = attempts >= max_attempts
    critical_age_hit = age is not None and age >= critical_age
    warning_age_hit = age is not None and age >= warning_age
    status = "critical" if retry_exhausted or critical_age_hit else "warning" if warning_age_hit or attempts else "ok"
    return {"spec_id": _bucket(row.get("spec_id") or row.get("id"), "unknown_spec"), "profile": _bucket(row.get("profile"), "unknown_profile"), "queued_at": row.get("queued_at"), "queued_age_hours": age, "attempts": attempts, "last_error": row.get("last_error"), "evidence_count": max(0, int_or_zero(row.get("evidence_count"))), "retry_exhausted": retry_exhausted, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = sum(1 for row in rows if row["status"] == "critical")
    warning = sum(1 for row in rows if row["status"] == "warning")
    return {"status": "critical" if critical else "warning" if warning else "ok", "queued_count": len(rows), "stuck_count": critical + warning, "retry_exhausted_count": sum(1 for row in rows if row["retry_exhausted"]), "oldest_age_hours": max((row["queued_age_hours"] for row in rows if row["queued_age_hours"] is not None), default=None)}


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
