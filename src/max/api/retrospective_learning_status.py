"""JSON API renderer for retrospective learning status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.retrospective_learning_status.v1"
KIND = "max.api.retrospective_learning_status"


def retrospective_learning_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    min_confidence = _score(payload.get("min_confidence", 0.7))
    min_sample_size = _int(payload.get("min_sample_size", 10))
    runs = _runs(payload)
    adjustments = _adjustments(payload, min_confidence, min_sample_size)
    applied = [row for row in adjustments if row["status"] == "applied"]
    rejected = [row for row in adjustments if row["status"] == "rejected"]
    pending = _pending(adjustments, min_confidence, min_sample_size)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(runs, applied, rejected, pending),
        "learning_runs": runs,
        "applied_adjustments": applied,
        "rejected_adjustments": rejected,
        "pending_reviews": pending,
        "profile_impact": _profile_impact(adjustments),
        "metadata": _metadata(payload, runs, adjustments, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _runs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("learning_runs") if isinstance(payload.get("learning_runs"), list) else payload.get("runs")
    rows = [
        {
            "run_id": _text(item.get("run_id") or item.get("id")) or f"run-{index}",
            "status": _text(item.get("status")) or "unknown",
            "sample_size": _int(item.get("sample_size")),
            "completed_at": item.get("completed_at"),
        }
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    rows.sort(key=lambda row: (row["run_id"], row["status"]))
    return rows


def _adjustments(payload: Mapping[str, Any], min_confidence: float, min_sample_size: int) -> list[dict[str, Any]]:
    source = payload.get("adjustments") if isinstance(payload.get("adjustments"), list) else payload.get("scoring_weight_adjustments")
    rows = [_adjustment(item, index, min_confidence, min_sample_size) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (-abs(row["weight_delta"]), row["dimension"], row["profile"], row["id"]))
    return rows


def _adjustment(item: Mapping[str, Any], index: int, min_confidence: float, min_sample_size: int) -> dict[str, Any]:
    confidence = _score(item.get("confidence"))
    sample_size = _int(item.get("sample_size"))
    approved = item.get("approved")
    status = _status(item.get("status"), approved, confidence, sample_size, min_confidence, min_sample_size)
    return {
        "id": _text(item.get("id") or item.get("adjustment_id")) or f"A{index}",
        "profile": _text(item.get("profile")) or "unknown-profile",
        "dimension": _text(item.get("dimension") or item.get("weight")) or "unknown-dimension",
        "weight_delta": _float(item.get("weight_delta", item.get("delta"))),
        "confidence": confidence,
        "sample_size": sample_size,
        "approved": _bool_or_none(approved),
        "status": status,
        "reason": _text(item.get("reason")),
    }


def _status(value: Any, approved: Any, confidence: float, sample_size: int, min_confidence: float, min_sample_size: int) -> str:
    explicit = _text(value).lower()
    if explicit in {"applied", "rejected"}:
        return explicit
    if _bool_or_none(approved) is False:
        return "rejected"
    if _bool_or_none(approved) is True and confidence >= min_confidence and sample_size >= min_sample_size:
        return "applied"
    return "pending_review"


def _pending(adjustments: list[dict[str, Any]], min_confidence: float, min_sample_size: int) -> list[dict[str, Any]]:
    rows = []
    for row in adjustments:
        reasons = []
        if row["approved"] is None:
            reasons.append("missing_approval")
        if row["confidence"] < min_confidence:
            reasons.append("low_confidence")
        if row["sample_size"] < min_sample_size:
            reasons.append("insufficient_sample_size")
        if row["status"] == "pending_review" or reasons:
            rows.append({"id": row["id"], "profile": row["profile"], "dimension": row["dimension"], "reasons": reasons})
    rows.sort(key=lambda row: (row["profile"], row["dimension"], row["id"]))
    return rows


def _summary(runs: list[dict[str, Any]], applied: list[dict[str, Any]], rejected: list[dict[str, Any]], pending: list[dict[str, Any]]) -> dict[str, Any]:
    return {"run_count": len(runs), "applied_adjustment_count": len(applied), "rejected_adjustment_count": len(rejected), "pending_review_count": len(pending)}


def _profile_impact(adjustments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in adjustments:
        grouped[row["profile"]].append(row)
    rows = [{"profile": profile, "adjustment_count": len(items), "net_weight_delta": round(sum(item["weight_delta"] for item in items), 4)} for profile, items in grouped.items()]
    rows.sort(key=lambda row: (-abs(row["net_weight_delta"]), row["profile"]))
    return rows


def _metadata(payload: Mapping[str, Any], runs: list[dict[str, Any]], adjustments: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "run_count": len(runs), "adjustment_count": len(adjustments)}


def _score(value: Any) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _float(value: Any) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "approved"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
