"""JSON API renderer for evidence reference URL health status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.evidence_reference_url_health_status.v1"
KIND = "max.api.evidence_reference_url_health_status"
RANK = {"critical": 0, "warning": 1, "unknown": 2, "healthy": 3}


def evidence_reference_url_health_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) or parse_datetime(payload.get("as_of"))
    rows = [_row(item, index, now) for index, item in enumerate(list_of_maps(payload.get("references") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (RANK[row["status"]], row["source"], row["reference_id"]))
    affected = [row for row in rows if row["status"] != "healthy"]
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "affected_references": affected, "source_rollups": _source_rollups(rows), "status_code_families": _families(rows), "references": rows, "actions": _actions(affected), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    status_code = item.get("status_code")
    code = int_or_zero(status_code)
    checked_at = parse_datetime(item.get("checked_at"))
    stale = bool(checked_at and as_of and (as_of - checked_at).days > int_or_zero(item.get("stale_after_days") or 7))
    error = item.get("error")
    if status_code in (None, "") and not checked_at and not error:
        status = "unknown"
    elif code in {404, 410} or (error and not item.get("last_success_at")):
        status = "critical"
    elif 300 <= code < 400 or item.get("redirect_target") or stale:
        status = "warning"
    elif 200 <= code < 300:
        status = "healthy"
    else:
        status = "warning" if code else "unknown"
    return {"reference_id": str(item.get("reference_id") or item.get("id") or f"reference-{index}"), "url": item.get("url"), "source": str(item.get("source") or "unknown"), "status_code": code if status_code not in (None, "") else None, "checked_at": item.get("checked_at"), "last_success_at": item.get("last_success_at"), "redirect_target": item.get("redirect_target"), "error": error, "status": status, "action": _action(status)}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if any(row["status"] == "warning" for row in rows) else ("unknown" if any(row["status"] == "unknown" for row in rows) else "healthy")), "reference_count": len(rows), "affected_reference_count": sum(1 for row in rows if row["status"] != "healthy")}


def _source_rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source": source, "reference_count": sum(1 for row in rows if row["source"] == source), "affected_reference_count": sum(1 for row in rows if row["source"] == source and row["status"] != "healthy")} for source in sorted({row["source"] for row in rows})]


def _families(rows: list[dict[str, Any]]) -> dict[str, int]:
    families = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "unknown": 0}
    for row in rows:
        code = row["status_code"]
        key = "unknown" if code is None else f"{code // 100}xx"
        families[key if key in families else "unknown"] += 1
    return families


def _action(status: str) -> str:
    return {"critical": "replace or remove dead evidence references", "warning": "refresh redirected or stale evidence reference checks", "unknown": "run URL health checks for references missing status data"}.get(status, "none")


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({_action(row["status"]) for row in rows if row["status"] != "healthy"})
