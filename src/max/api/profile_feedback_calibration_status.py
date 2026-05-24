"""JSON API renderer for profile feedback calibration status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.profile_feedback_calibration_status.v1"
KIND = "max.api.profile_feedback_calibration_status"
CONFIDENCE_RANK = {"insufficient": 0, "low": 1, "medium": 2, "high": 3}


def profile_feedback_calibration_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    min_samples = _int(payload.get("min_samples", payload.get("minimum_samples", 20)))
    profiles = _profiles(payload, min_samples)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(profiles),
        "profiles": profiles,
        "warnings": [warning for row in profiles for warning in row["warnings"]],
        "recommendations": _recommendations(profiles),
        "metadata": _metadata(payload, profiles, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profiles(payload: Mapping[str, Any], min_samples: int) -> list[dict[str, Any]]:
    source = payload.get("profiles") if isinstance(payload.get("profiles"), list) else payload.get("calibrations")
    rows = [_profile(item, index, min_samples) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (CONFIDENCE_RANK[row["confidence"]], row["profile"]))
    return rows


def _profile(item: Mapping[str, Any], index: int, min_samples: int) -> dict[str, Any]:
    positive = _int(item.get("positive_count", item.get("approved", item.get("approvals"))))
    negative = _int(item.get("negative_count", item.get("rejected", item.get("rejections"))))
    samples = _int(item.get("sample_count", item.get("samples"))) or positive + negative
    mix = round(positive / samples, 4) if samples else 0.0
    deltas = _deltas(item.get("weight_deltas", item.get("deltas")))
    warnings = _warnings(_text(item.get("profile")) or f"profile-{index}", samples, positive, negative, min_samples)
    confidence = _confidence(samples, min_samples, mix)
    return {
        "profile": _text(item.get("profile") or item.get("name")) or f"profile-{index}",
        "sample_count": samples,
        "positive_count": positive,
        "negative_count": negative,
        "positive_rate": mix,
        "negative_rate": round(negative / samples, 4) if samples else 0.0,
        "confidence": confidence,
        "weight_deltas": deltas,
        "warnings": warnings,
    }


def _deltas(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        iterable = value.items()
    else:
        iterable = []
    for dimension, delta in iterable:
        rows.append({"dimension": _text(dimension), "delta": _float(delta)})
    rows.sort(key=lambda row: (-abs(row["delta"]), row["dimension"]))
    return rows


def _warnings(profile: str, samples: int, positive: int, negative: int, min_samples: int) -> list[dict[str, Any]]:
    rows = []
    if samples < min_samples:
        rows.append({"profile": profile, "type": "insufficient_data", "message": "Profile has fewer feedback samples than required"})
    if samples and (positive == 0 or negative == 0 or max(positive, negative) / samples >= 0.9):
        rows.append({"profile": profile, "type": "skewed_outcomes", "message": "Profile feedback outcomes are heavily skewed"})
    return rows


def _confidence(samples: int, min_samples: int, positive_rate: float) -> str:
    if samples <= 0 or samples < min_samples:
        return "insufficient"
    if positive_rate <= 0.1 or positive_rate >= 0.9:
        return "low"
    if samples >= min_samples * 3:
        return "high"
    return "medium"


def _recommendations(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in profiles:
        if row["confidence"] == "insufficient":
            rows.append({"profile": row["profile"], "action": "Collect more approval and rejection feedback before changing weights"})
        elif row["warnings"]:
            rows.append({"profile": row["profile"], "action": "Balance feedback collection across positive and negative outcomes"})
        elif row["weight_deltas"]:
            rows.append({"profile": row["profile"], "action": "Apply calibrated weight deltas", "top_delta": row["weight_deltas"][0]})
    return rows


def _summary(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "profile_count": len(profiles),
        "sample_count": sum(row["sample_count"] for row in profiles),
        "positive_count": sum(row["positive_count"] for row in profiles),
        "negative_count": sum(row["negative_count"] for row in profiles),
        "warning_count": sum(len(row["warnings"]) for row in profiles),
    }


def _metadata(payload: Mapping[str, Any], profiles: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "profile_count": len(profiles)}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
