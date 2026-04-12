"""Cross-domain idea deduplication — cluster similar ideas, keep best."""

from __future__ import annotations

from dataclasses import dataclass, field

from max.embeddings.engine import _cosine_similarity, embed_text
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


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
        """All members except the representative (highest-scored)."""
        return [(u, ev) for u, ev in self.members if u.id != self.representative.id]


def _idea_text(unit: BuildableUnit) -> str:
    """Build text representation for embedding."""
    return f"{unit.title} {unit.one_liner} {unit.problem[:200]}"


def cluster_ideas(
    ideas: list[tuple[BuildableUnit, UtilityEvaluation | None]],
    *,
    similarity_threshold: float = 0.85,
    max_clusters: int = 200,
) -> list[IdeaCluster]:
    """Cluster ideas by semantic similarity.

    Returns clusters sorted by size descending (largest clusters first).
    Within each cluster, the representative is the highest-scored idea.
    """
    if not ideas:
        return []

    clusters: list[IdeaCluster] = []

    for unit, ev in ideas:
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

    # Set representative to highest-scored in each cluster
    for cluster in clusters:
        best_unit, best_ev = max(
            cluster.members,
            key=lambda x: x[1].overall_score if x[1] else 0.0,
        )
        cluster.representative = best_unit
        cluster.representative_eval = best_ev

    # Sort by cluster size descending (show multi-idea clusters first)
    clusters.sort(key=lambda c: c.size, reverse=True)
    return clusters
