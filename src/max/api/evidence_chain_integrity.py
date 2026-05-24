"""JSON API renderer for evidence chain integrity."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.evidence_chain_integrity.v1"
KIND = "max.api.evidence_chain_integrity"
STATUS_RANK = {"broken": 0, "degraded": 1, "complete": 2}


def evidence_chain_integrity_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    chains = _chains(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(chains),
        "chains": chains,
        "broken_chains": [row for row in chains if row["status"] == "broken"],
        "metadata": _metadata(payload, chains, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _chains(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("chains") if isinstance(payload.get("chains"), list) else payload.get("evidence_chains")
    rows = [_chain(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["entity_type"], row["entity_id"]))
    return rows


def _chain(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    missing_signal_ids = _strings(item.get("missing_signal_ids") or item.get("missing_signals"))
    missing_insight_ids = _strings(item.get("missing_insight_ids") or item.get("missing_insights"))
    orphaned = _int(item.get("orphaned_reference_count", item.get("orphaned_references")))
    confidence = _score(item.get("confidence", item.get("confidence_score", 1)))
    status = _status(missing_signal_ids, missing_insight_ids, orphaned, confidence)
    return {
        "entity_id": _text(item.get("entity_id") or item.get("id")) or f"entity-{index}",
        "entity_type": _text(item.get("entity_type") or item.get("type")) or "unknown-entity",
        "missing_signal_ids": missing_signal_ids,
        "missing_insight_ids": missing_insight_ids,
        "orphaned_reference_count": orphaned,
        "confidence": confidence,
        "status": status,
        "missing_reference_count": len(missing_signal_ids) + len(missing_insight_ids) + orphaned,
    }


def _status(missing_signal_ids: list[str], missing_insight_ids: list[str], orphaned: int, confidence: float) -> str:
    if missing_signal_ids or missing_insight_ids:
        return "broken"
    if orphaned or confidence < 0.75:
        return "degraded"
    return "complete"


def _summary(chains: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in chains)
    return {
        "chain_count": len(chains),
        "complete_count": counts["complete"],
        "degraded_count": counts["degraded"],
        "broken_count": counts["broken"],
        "missing_reference_count": sum(row["missing_reference_count"] for row in chains),
    }


def _metadata(payload: Mapping[str, Any], chains: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "chain_count": len(chains)}


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    return sorted(str(item) for item in values if item not in (None, ""))


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _score(value: Any) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
