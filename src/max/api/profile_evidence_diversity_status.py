"""JSON API renderer for profile evidence diversity status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.profile_evidence_diversity_status.v1"
KIND = "max.api.profile_evidence_diversity_status"


def profile_evidence_diversity_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    low_threshold = _float(payload.get("low_diversity_threshold", 0.5), 0.5)
    dominance_threshold = _float(payload.get("dominance_threshold", 0.7), 0.7)
    profiles = _profiles(payload, low_threshold, dominance_threshold)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(profiles),
        "profile_diversity": profiles,
        "low_diversity_profiles": [row for row in profiles if row["low_diversity"]],
        "source_mix": _mix(profiles, "source_mix", "source"),
        "category_mix": _mix(profiles, "category_mix", "category"),
        "metadata": _metadata(payload, profiles, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profiles(payload: Mapping[str, Any], low_threshold: float, dominance_threshold: float) -> list[dict[str, Any]]:
    source = payload.get("profiles") if isinstance(payload.get("profiles"), list) else payload.get("profile_diversity")
    rows = [_profile(item, index, low_threshold, dominance_threshold) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (row["diversity_score"], -row["dominant_source_share"], row["profile"]))
    return rows


def _profile(item: Mapping[str, Any], index: int, low_threshold: float, dominance_threshold: float) -> dict[str, Any]:
    evidence = [entry for entry in _as_list(item.get("evidence")) if isinstance(entry, Mapping)]
    source_counts = _counts(item.get("source_counts"), evidence, "source")
    category_counts = _counts(item.get("category_counts"), evidence, "category")
    evidence_count = _int(item.get("evidence_count", sum(source_counts.values()) or len(evidence)))
    source_count = _int(item.get("source_count", len(source_counts)))
    category_count = _int(item.get("category_count", len(category_counts)))
    corroboration_count = _int(item.get("corroboration_count", item.get("corroborations", 0)))
    dominant_share = _share(item.get("dominant_source_share"), source_counts, evidence_count)
    score = _score(source_count, category_count, corroboration_count, dominant_share, evidence_count)
    return {
        "profile": _text(item.get("profile") or item.get("profile_id")) or f"profile-{index}",
        "evidence_count": evidence_count,
        "source_count": source_count,
        "category_count": category_count,
        "corroboration_count": corroboration_count,
        "dominant_source_share": dominant_share,
        "diversity_score": score,
        "low_diversity": score < low_threshold or dominant_share > dominance_threshold,
        "risk_flags": _risk_flags(score, low_threshold, dominant_share, dominance_threshold, evidence_count),
        "source_mix": dict(sorted(source_counts.items())),
        "category_mix": dict(sorted(category_counts.items())),
    }


def _score(source_count: int, category_count: int, corroboration_count: int, dominant_share: float, evidence_count: int) -> float:
    if evidence_count <= 0:
        return 0.0
    raw = (min(source_count / 3, 1) * 0.4) + (min(category_count / 3, 1) * 0.3) + (min(corroboration_count / 2, 1) * 0.2) + ((1 - dominant_share) * 0.1)
    return round(min(max(raw, 0.0), 1.0), 4)


def _summary(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "profile_count": len(profiles),
        "low_diversity_count": sum(1 for row in profiles if row["low_diversity"]),
        "average_diversity_score": round(sum(row["diversity_score"] for row in profiles) / len(profiles), 4) if profiles else 0.0,
    }


def _mix(profiles: list[dict[str, Any]], field: str, output_key: str) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for profile in profiles:
        counts.update(profile[field])
    return [{output_key: key, "count": count} for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _metadata(payload: Mapping[str, Any], profiles: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "profile_count": len(profiles)}


def _counts(explicit: Any, evidence: list[Mapping[str, Any]], field: str) -> dict[str, int]:
    if isinstance(explicit, Mapping):
        return {str(key): _int(value) for key, value in explicit.items()}
    counts: Counter[str] = Counter(_text(item.get(field)) or f"unknown-{field}" for item in evidence)
    return dict(counts)


def _share(explicit: Any, counts: dict[str, int], total: int) -> float:
    if explicit is not None:
        return min(max(_float(explicit, 0.0), 0.0), 1.0)
    return round(max(counts.values()) / total, 4) if counts and total else 0.0


def _risk_flags(score: float, low_threshold: float, dominant_share: float, dominance_threshold: float, evidence_count: int) -> list[str]:
    flags = []
    if evidence_count <= 0:
        flags.append("missing_evidence")
    if score < low_threshold:
        flags.append("low_diversity")
    if dominant_share > dominance_threshold:
        flags.append("dominant_source")
    return flags


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
