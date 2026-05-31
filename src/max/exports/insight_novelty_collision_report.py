"""Insight novelty collision export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.insight_novelty_collision_report.v1"
KIND = "max.insight_novelty_collision_report"
SEVERITY_RANK = {"critical": 0, "warn": 1}


def generate_insight_novelty_collision_report(candidates: Iterable[dict[str, Any]], *, similarity_threshold: float = 0.9, critical_threshold: float = 0.97) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(candidates, start=1):
        similarity = _float(item.get("similarity") or item.get("similarity_score"))
        if similarity < similarity_threshold:
            continue
        group = _text(item.get("canonical_insight_id") or item.get("cluster_id")) or f"collision-{index}"
        row = {"group_id": group, "insight_id": _text(item.get("insight_id") or item.get("candidate_insight_id")) or f"insight-{index}", "duplicate_of": _text(item.get("duplicate_of") or item.get("canonical_insight_id")), "similarity_score": round(similarity, 4), "profile": _text(item.get("profile")) or "default", "source_overlap": _items(item.get("source_overlap") or item.get("sources")), "severity": "critical" if similarity >= critical_threshold else "warn"}
        groups[group].append(row)
    rows = [{"group_id": group, "candidate_count": len(items), "max_similarity_score": max(item["similarity_score"] for item in items), "profile": ", ".join(sorted({item["profile"] for item in items})), "source_overlap": sorted({source for item in items for source in item["source_overlap"]}), "severity": min((item["severity"] for item in items), key=SEVERITY_RANK.get), "candidates": sorted(items, key=lambda item: (-item["similarity_score"], item["insight_id"]))} for group, items in groups.items()]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], -row["max_similarity_score"], row["group_id"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"collision_group_count": len(rows), "candidate_count": sum(row["candidate_count"] for row in rows)}, "rows": rows}


def render_insight_novelty_collision_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_insight_novelty_collision_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Insight Novelty Collision Report", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['group_id']}: {row['candidate_count']} candidates, max similarity {row['max_similarity_score']} ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _items(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = []
    return sorted({_text(part) for part in parts if _text(part)})


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
