"""Insight deduplication collision export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.insight_deduplication_collision.v1"
KIND = "max.insight_deduplication_collision"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"
DEFAULT_SIMILARITY_THRESHOLD = 0.9


class InsightDeduplicationCollisionInput(TypedDict, total=False):
    insight_id: str
    duplicate_of: str
    similarity_score: int | float | str
    source_ids: list[str] | tuple[str, ...] | str
    profile: str
    title: str
    resolution: str


def build_insight_deduplication_collision_report(
    records: Iterable[InsightDeduplicationCollisionInput | dict[str, Any]],
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    title: str = "Insight Deduplication Collision Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    threshold = round(_float(similarity_threshold, default=DEFAULT_SIMILARITY_THRESHOLD), 4)
    rows = _normalize_records(records, threshold)
    high = [row for row in rows if row["high_similarity"]]
    unresolved = [row for row in rows if row["unresolved"]]
    profiles = _affected_profiles(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Insight Deduplication Collision Report",
        "similarity_threshold": threshold,
        "summary": {
            "collision_count": len(rows),
            "high_similarity_count": len(high),
            "unresolved_count": len(unresolved),
            "affected_profile_count": len(profiles),
        },
        "collisions": rows,
        "high_similarity_collisions": high,
        "unresolved_collisions": unresolved,
        "affected_profiles": profiles,
        "review_queue": sorted(unresolved, key=lambda row: (not row["high_similarity"], -row["similarity_score"], row["profile"].lower(), row["insight_id"].lower())),
    }


def render_insight_deduplication_collision_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join(
        [
            f"# {report.get('title') or 'Insight Deduplication Collision Report'}",
            "",
            "## Summary",
            "",
            f"- Collisions: {summary.get('collision_count', 0)}",
            f"- High similarity: {summary.get('high_similarity_count', 0)}",
            f"- Unresolved: {summary.get('unresolved_count', 0)}",
        ]
    ).rstrip() + "\n"


def render_insight_deduplication_collision_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[InsightDeduplicationCollisionInput | dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(records):
        score = round(min(1.0, _float(raw.get("similarity_score"))), 4)
        resolution = _text(raw.get("resolution")) or "unresolved"
        rows.append(
            {
                "insight_id": _text(raw.get("insight_id")) or f"unknown-insight-{index + 1}",
                "duplicate_of": _text(raw.get("duplicate_of")) or "unknown-kept-insight",
                "similarity_score": score,
                "source_ids": _source_ids(raw.get("source_ids")),
                "profile": _text(raw.get("profile")) or "Unassigned profile",
                "title": _text(raw.get("title")) or "Untitled insight",
                "resolution": resolution,
                "high_similarity": score >= threshold,
                "unresolved": resolution.lower() in {"", "unresolved", "open", "needs review"},
            }
        )
    rows.sort(key=lambda row: (-row["similarity_score"], row["profile"].lower(), row["insight_id"].lower()))
    return rows


def _affected_profiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = sorted({row["profile"] for row in rows}, key=str.lower)
    return [
        {
            "profile": profile,
            "collision_count": sum(1 for row in rows if row["profile"] == profile),
            "unresolved_count": sum(1 for row in rows if row["profile"] == profile and row["unresolved"]),
        }
        for profile in profiles
    ]


def _source_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, Iterable):
        items = list(value)
    else:
        items = []
    output = sorted({_text(item) for item in items if _text(item)})
    return output or ["unknown-source"]


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
