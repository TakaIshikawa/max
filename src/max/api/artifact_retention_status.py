"""JSON API renderer for run artifact retention status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.artifact_retention_status.v1"
KIND = "max.api.artifact_retention_status"
STATUS_RANK = {"expired": 0, "nearing_expiry": 1, "retained": 2, "legal_hold": 3}


def artifact_retention_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    artifacts = _artifacts(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(artifacts),
        "artifacts": artifacts,
        "type_totals": _type_totals(artifacts),
        "expired_artifacts": [row for row in artifacts if row["status"] == "expired"],
        "metadata": _metadata(payload, artifacts, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _artifacts(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else payload.get("run_artifacts")
    rows = [_artifact(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["run_id"], row["artifact_id"]))
    return rows


def _artifact(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    age_days = _int(item.get("age_days", item.get("age")))
    retention_days = _int(item.get("retention_days", item.get("retention")))
    hold = _bool(item.get("hold", item.get("legal_hold")))
    delete_after_days = max(retention_days - age_days, 0)
    status = _status(age_days, retention_days, hold)
    return {
        "artifact_id": _text(item.get("artifact_id") or item.get("id")) or f"artifact-{index}",
        "run_id": _text(item.get("run_id") or item.get("run")) or "unknown-run",
        "type": _text(item.get("type") or item.get("artifact_type")) or "unknown-type",
        "age_days": age_days,
        "retention_days": retention_days,
        "hold": hold,
        "delete_after_days": delete_after_days,
        "status": status,
    }


def _status(age_days: int, retention_days: int, hold: bool) -> str:
    if hold:
        return "legal_hold"
    if retention_days and age_days >= retention_days:
        return "expired"
    if retention_days and retention_days - age_days <= max(1, int(retention_days * 0.1)):
        return "nearing_expiry"
    return "retained"


def _summary(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in artifacts)
    return {
        "artifact_count": len(artifacts),
        "expired_count": counts["expired"],
        "nearing_expiry_count": counts["nearing_expiry"],
        "retained_count": counts["retained"],
        "legal_hold_count": counts["legal_hold"],
    }


def _type_totals(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in artifacts:
        grouped[row["type"]].append(row)
    return [
        {
            "type": key,
            "artifact_count": len(items),
            "expired_count": sum(1 for item in items if item["status"] == "expired"),
            "legal_hold_count": sum(1 for item in items if item["status"] == "legal_hold"),
        }
        for key, items in sorted(grouped.items())
    ]


def _metadata(payload: Mapping[str, Any], artifacts: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "artifact_count": len(artifacts)}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
