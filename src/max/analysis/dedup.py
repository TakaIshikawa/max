"""Cross-domain idea deduplication — cluster similar ideas, keep best."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from max.embeddings.engine import _cosine_similarity, embed_text
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


# Status priority for choosing cluster representative.
# Approved/rejected reflect explicit user decisions and outrank score-based picks.
_STATUS_PRIORITY: dict[str, int] = {"approved": 2, "rejected": 1}


def _representative_key(
    unit: BuildableUnit, ev: UtilityEvaluation | None,
) -> tuple[int, float]:
    """Sort key for picking a cluster representative.

    Approved members win over rejected, which win over evaluated/other; ties
    broken by overall score. This preserves prior user decisions across runs.
    """
    priority = _STATUS_PRIORITY.get(unit.status or "", 0)
    score = ev.overall_score if ev else 0.0
    return (priority, score)


@dataclass
class IdeaCluster:
    """A group of semantically similar ideas across domains."""

    representative: BuildableUnit
    representative_eval: UtilityEvaluation | None
    members: list[tuple[BuildableUnit, UtilityEvaluation | None]] = field(default_factory=list)
    centroid: list[float] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def best_score(self) -> float:
        scores = [ev.overall_score for _, ev in self.members if ev]
        return max(scores) if scores else 0.0

    @property
    def domains(self) -> set[str]:
        return {u.domain for u, _ in self.members if u.domain}

    @property
    def duplicates(self) -> list[tuple[BuildableUnit, UtilityEvaluation | None]]:
        """All members except the representative."""
        return [(u, ev) for u, ev in self.members if u.id != self.representative.id]


def _idea_text(unit: BuildableUnit) -> str:
    """Build text representation for embedding."""
    return f"{unit.title} {unit.one_liner} {unit.problem[:200]}"


def _extract_product_name(title: str) -> str:
    """Extract the product name (before the em dash) and normalize."""
    name = re.split(r"\s*[—–\-]\s*", title, maxsplit=1)[0]
    return name.strip().lower()


def _pre_cluster_by_name(
    ideas: list[tuple[BuildableUnit, UtilityEvaluation | None]],
) -> list[list[tuple[BuildableUnit, UtilityEvaluation | None]]]:
    """Group ideas that share the same product name.

    Returns groups where each group contains ideas with identical
    (normalized) product names. Groups of size 1 are included as singletons.
    """
    name_groups: dict[str, list[tuple[BuildableUnit, UtilityEvaluation | None]]] = defaultdict(list)
    for unit, ev in ideas:
        name = _extract_product_name(unit.title)
        name_groups[name].append((unit, ev))
    return list(name_groups.values())


def cluster_ideas(
    ideas: list[tuple[BuildableUnit, UtilityEvaluation | None]],
    *,
    similarity_threshold: float = 0.85,
    max_clusters: int = 200,
) -> list[IdeaCluster]:
    """Cluster ideas by semantic similarity.

    Uses a two-phase approach:
    1. Pre-cluster ideas with identical product names (exact match, fast)
    2. Cluster remaining groups by embedding similarity (semantic match)

    Returns clusters sorted by size descending (largest clusters first).
    Within each cluster, the representative is the highest-priority idea —
    approved > rejected > others, with ties broken by score. This preserves
    prior user decisions across runs.
    """
    if not ideas:
        return []

    # Phase 1: pre-cluster by product name
    name_groups = _pre_cluster_by_name(ideas)

    clusters: list[IdeaCluster] = []

    for group in name_groups:
        # For multi-member name groups, create a cluster directly
        if len(group) > 1:
            best_unit, best_ev = max(
                group,
                key=lambda x: _representative_key(x[0], x[1]),
            )
            text = _idea_text(best_unit)
            embedding = embed_text(text)
            clusters.append(IdeaCluster(
                representative=best_unit,
                representative_eval=best_ev,
                members=list(group),
                centroid=embedding,
            ))
            continue

        # Phase 2: for singletons, try embedding-based clustering
        unit, ev = group[0]
        text = _idea_text(unit)
        embedding = embed_text(text)

        best_cluster: IdeaCluster | None = None
        best_sim = 0.0
        for cluster in clusters:
            sim = _cosine_similarity(embedding, cluster.centroid)
            if sim > best_sim and sim >= similarity_threshold:
                best_sim = sim
                best_cluster = cluster

        if best_cluster is not None:
            best_cluster.members.append((unit, ev))
            # Update centroid (running average)
            n = len(best_cluster.members)
            best_cluster.centroid = [
                (c * (n - 1) + e) / n
                for c, e in zip(best_cluster.centroid, embedding)
            ]
        elif len(clusters) < max_clusters:
            clusters.append(IdeaCluster(
                representative=unit,
                representative_eval=ev,
                members=[(unit, ev)],
                centroid=embedding,
            ))

    # Set representative: prefer approved/rejected (preserves user decisions),
    # then by score
    for cluster in clusters:
        best_unit, best_ev = max(
            cluster.members,
            key=lambda x: _representative_key(x[0], x[1]),
        )
        cluster.representative = best_unit
        cluster.representative_eval = best_ev

    # Sort by cluster size descending (show multi-idea clusters first)
    clusters.sort(key=lambda c: c.size, reverse=True)
    return clusters
