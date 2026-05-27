"""Idea duplicate cluster export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.idea_duplicate_cluster_report.v1"
KIND = "max.idea_duplicate_cluster_report"


def generate_idea_duplicate_cluster_report(pairs: Iterable[dict[str, Any]], *, threshold: float = 0.9) -> dict[str, Any]:
    parent: dict[str, str] = {}
    similarities: dict[frozenset[str], float] = {}
    for raw in pairs:
        left = _text(raw.get("left_id") or raw.get("idea_id") or raw.get("a"))
        right = _text(raw.get("right_id") or raw.get("duplicate_id") or raw.get("b"))
        score = _float(raw.get("similarity"))
        if not left or not right or left == right or score < threshold:
            continue
        _union(parent, left, right)
        similarities[frozenset({left, right})] = max(score, similarities.get(frozenset({left, right}), 0.0))
    clusters: dict[str, list[str]] = {}
    for item in list(parent):
        clusters.setdefault(_find(parent, item), []).append(item)
    rows = []
    for members in clusters.values():
        members = sorted(set(members))
        if len(members) < 2:
            continue
        canonical = members[0]
        rows.append(
            {
                "canonical_idea_id": canonical,
                "duplicate_ids": members[1:],
                "duplicate_count": len(members) - 1,
                "max_similarity": max(similarities.get(frozenset({a, b}), 0.0) for a in members for b in members if a < b),
                "recommendation": f"Merge or suppress duplicates into canonical idea {canonical}.",
            }
        )
    rows.sort(key=lambda row: (-row["duplicate_count"], row["canonical_idea_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"cluster_count": len(rows), "total_duplicate_idea_count": sum(row["duplicate_count"] for row in rows), "threshold": threshold}, "clusters": rows}


def _find(parent: dict[str, str], item: str) -> str:
    parent.setdefault(item, item)
    if parent[item] != item:
        parent[item] = _find(parent, parent[item])
    return parent[item]


def _union(parent: dict[str, str], left: str, right: str) -> None:
    root_left, root_right = _find(parent, left), _find(parent, right)
    if root_left != root_right:
        parent[max(root_left, root_right)] = min(root_left, root_right)


def _float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

