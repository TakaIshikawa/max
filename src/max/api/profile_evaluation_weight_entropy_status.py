"""JSON API renderer for profile evaluation weight entropy status."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.profile_evaluation_weight_entropy_status.v1"
KIND = "max.api.profile_evaluation_weight_entropy_status"


def profile_evaluation_weight_entropy_status_to_json(payload: Mapping[str, Any]) -> str:
    profiles = [_profile(row) for row in _items(payload)]
    profiles.sort(key=lambda row: (_rank(row["status"]), row["profile"]))
    critical = sum(1 for row in profiles if row["status"] == "critical")
    warning = sum(1 for row in profiles if row["status"] == "warning")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": "critical" if critical else "warning" if warning else "ok", "summary": {"profile_count": len(profiles), "critical_count": critical, "warning_count": warning}, "profiles": profiles, "metadata": source_metadata(payload, profile_count=len(profiles))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("profiles")) or list_of_maps(payload.get("items"))


def _profile(row: Mapping[str, Any]) -> dict[str, Any]:
    weights = row.get("weights") if isinstance(row.get("weights"), Mapping) else {}
    violations: list[str] = []
    positives: dict[str, float] = {}
    for key, value in weights.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            violations.append(f"non_numeric_weight:{key}")
            continue
        if number < 0:
            violations.append(f"negative_weight:{key}")
        elif number > 0:
            positives[str(key)] = number
    if not positives:
        violations.append("empty_positive_weights")
    total = sum(positives.values())
    normalized = {key: round(value / total, 4) for key, value in sorted(positives.items())} if total else {}
    entropy = round(-sum(weight * math.log2(weight) for weight in normalized.values()), 4) if normalized else 0.0
    dominant = max(normalized, key=normalized.get) if normalized else None
    min_entropy = float_or_zero(row.get("min_entropy")) or 0.0
    max_single = float_or_zero(row.get("max_single_weight")) or 1.0
    if entropy < min_entropy and normalized:
        violations.append("entropy_below_minimum")
    if normalized and max(normalized.values()) > max_single:
        violations.append("single_weight_above_maximum")
    status = "critical" if any(v.startswith(("negative", "non_numeric", "empty")) for v in violations) else "warning" if violations else "ok"
    return {"profile": _bucket(row.get("profile"), "unknown_profile"), "normalized_weights": normalized, "entropy": entropy, "dominant_dimension": dominant, "violations": sorted(violations), "status": status}


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
