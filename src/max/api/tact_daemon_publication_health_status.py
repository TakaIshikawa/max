"""JSON API renderer for tact daemon publication health status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.tact_daemon_publication_health_status.v1"
KIND = "max.api.tact_daemon_publication_health_status"


def tact_daemon_publication_health_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    stale_hours = int_or_zero(payload.get("publish_stale_hours") or payload.get("stale_hours") or 24)
    daemons = [_daemon(row, i, as_of, stale_hours) for i, row in enumerate(list_of_maps(payload.get("daemons") or payload.get("rows")), start=1)]
    status = "critical" if any(row["status"] == "critical" for row in daemons) else ("warning" if any(row["status"] == "warning" for row in daemons) else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": status, "total_daemons": len(daemons), "unreachable_count": sum(1 for row in daemons if not row["reachable"]), "pending_payload_count": sum(row["pending_payload_count"] for row in daemons), "failed_handoff_count": sum(row["failed_handoff_count"] for row in daemons), "daemons": sorted(daemons, key=lambda row: (row["status"] != "critical", row["daemon"].casefold())), "next_action": _next_action(daemons), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _daemon(item: Mapping[str, Any], index: int, as_of: datetime, stale_hours: int) -> dict[str, Any]:
    reachable = bool(item.get("reachable", item.get("is_reachable", True)))
    last_success = parse_datetime(item.get("last_successful_publish_at") or item.get("last_publish_at"))
    age_hours = round((as_of - last_success).total_seconds() / 3600, 2) if last_success else None
    pending = int_or_zero(item.get("pending_payload_count") or item.get("pending_count"))
    failed = int_or_zero(item.get("failed_handoff_count") or item.get("failed_count"))
    never = last_success is None
    status = "critical" if not reachable or never else ("warning" if pending or failed or (age_hours is not None and age_hours > stale_hours) else "healthy")
    return {"daemon": _text(item.get("daemon") or item.get("name") or item.get("id")) or f"daemon-{index}", "reachable": reachable, "last_successful_publish_at": item.get("last_successful_publish_at") or item.get("last_publish_at"), "last_success_age_hours": age_hours, "pending_payload_count": pending, "failed_handoff_count": failed, "never_published": never, "status": status, "next_action": "restore daemon reachability" if not reachable else ("perform first successful publish" if never else ("drain pending payloads and retry failed handoffs" if pending or failed else ("verify daemon publish loop" if age_hours is not None and age_hours > stale_hours else "continue monitoring")))}


def _next_action(rows: list[Mapping[str, Any]]) -> str:
    if any(not row["reachable"] for row in rows):
        return "restore daemon reachability"
    if any(row["never_published"] for row in rows):
        return "perform first successful publish"
    if any(row["pending_payload_count"] or row["failed_handoff_count"] for row in rows):
        return "drain pending payloads and retry failed handoffs"
    return "continue monitoring"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
