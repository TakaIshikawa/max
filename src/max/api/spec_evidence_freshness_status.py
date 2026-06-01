"""JSON API renderer for spec evidence freshness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.spec_evidence_freshness_status.v1"
KIND = "max.api.spec_evidence_freshness_status"


def spec_evidence_freshness_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    max_age = _float(payload.get("max_age_hours"), 168.0)
    specs = [_spec(row, index, now, max_age) for index, row in enumerate(list_of_maps(payload.get("specs") or payload.get("rows")), start=1)]
    specs.sort(key=lambda row: (-row["stale_evidence_count"], -row["oldest_evidence_age_hours"], row["spec_id"]))
    refresh = [row for row in specs if row["refresh_required"]]
    stalest = specs[0] if specs and specs[0]["oldest_evidence_age_hours"] > 0 else None
    all_evidence_stale = bool(specs) and all(row["evidence_count"] and row["stale_evidence_count"] == row["evidence_count"] for row in specs)
    status = "critical" if all_evidence_stale else ("warning" if refresh else "healthy")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"status": status, "spec_count": len(specs), "refresh_required_count": len(refresh), "stale_evidence_count": sum(row["stale_evidence_count"] for row in specs), "stalest_spec": stalest["spec_id"] if stalest else None},
        "specs": specs,
        "refresh_required_specs": refresh,
        "stalest_spec": stalest,
        "metadata": source_metadata(payload, as_of=now.isoformat().replace("+00:00", "Z")),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _spec(item: Mapping[str, Any], index: int, now: datetime, max_age: float) -> dict[str, Any]:
    evidence = [_evidence(row, now, max_age) for row in list_of_maps(item.get("evidence") or item.get("evidence_items"))]
    ages = [row["age_hours"] for row in evidence]
    stale = [row for row in evidence if row["status"] == "stale"]
    missing = [row for row in evidence if row["status"] == "missing"]
    return {"spec_id": _text(item.get("spec_id") or item.get("id") or f"spec-{index}"), "evidence_count": len(evidence), "newest_evidence_age_hours": min(ages) if ages else 0.0, "oldest_evidence_age_hours": max(ages) if ages else 0.0, "stale_evidence_count": len(stale) + len(missing), "refresh_required": bool(stale or missing), "evidence": evidence}


def _evidence(item: Mapping[str, Any], now: datetime, max_age: float) -> dict[str, Any]:
    ts = parse_datetime(item.get("timestamp") or item.get("observed_at") or item.get("created_at"))
    age = round(max((now - ts).total_seconds() / 3600, 0.0), 2) if ts else 0.0
    status = "missing" if ts is None else ("stale" if age > max_age else "fresh")
    return {"evidence_id": _text(item.get("evidence_id") or item.get("id") or "evidence"), "timestamp": ts.isoformat().replace("+00:00", "Z") if ts else None, "age_hours": age, "status": status}


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
