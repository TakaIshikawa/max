"""Cross-source triangulation — cluster signals by topic, score source diversity."""

from __future__ import annotations

from dataclasses import dataclass, field

from max.embeddings.engine import _cosine_similarity, embed_text
from max.types.signal import Signal


@dataclass
class SignalCluster:
    """A group of semantically related signals across sources."""

    topic: str
    signals: list[Signal] = field(default_factory=list)
    source_diversity: float = 0.0
    avg_credibility: float = 0.0
    roles: dict[str, int] = field(default_factory=dict)
    centroid: list[float] = field(default_factory=list)

    @property
    def signal_ids(self) -> list[str]:
        return [s.id for s in self.signals]

    @property
    def distinct_sources(self) -> set[str]:
        return {s.source_adapter for s in self.signals}

    def triangulation_score(self) -> float:
        """Combined score: source_diversity * avg_credibility * size_factor."""
        size_factor = min(len(self.signals) / 3.0, 1.0)
        return self.source_diversity * self.avg_credibility * size_factor


def triangulate(
    signals: list[Signal],
    *,
    similarity_threshold: float = 0.65,
    max_clusters: int = 20,
) -> list[SignalCluster]:
    """Cluster signals by semantic similarity and compute triangulation scores.

    Returns clusters sorted by triangulation_score descending.
    """
    if not signals:
        return []

    clusters: list[SignalCluster] = []

    for signal in signals:
        text = f"{signal.title} {signal.content[:200]}"
        embedding = embed_text(text)

        best_cluster: SignalCluster | None = None
        best_sim = 0.0
        for cluster in clusters:
            sim = _cosine_similarity(embedding, cluster.centroid)
            if sim > best_sim and sim >= similarity_threshold:
                best_sim = sim
                best_cluster = cluster

        if best_cluster is not None:
            best_cluster.signals.append(signal)
            n = len(best_cluster.signals)
            best_cluster.centroid = [
                (c * (n - 1) + e) / n
                for c, e in zip(best_cluster.centroid, embedding)
            ]
        elif len(clusters) < max_clusters:
            clusters.append(SignalCluster(
                topic=signal.title,
                signals=[signal],
                centroid=embedding,
            ))

    total_adapters = len({s.source_adapter for s in signals})
    for cluster in clusters:
        _compute_cluster_stats(cluster, total_adapters)

    clusters.sort(key=lambda c: c.triangulation_score(), reverse=True)
    return clusters


def _compute_cluster_stats(cluster: SignalCluster, total_adapters: int) -> None:
    """Compute diversity, credibility, and role stats for a cluster."""
    distinct = len(cluster.distinct_sources)
    cluster.source_diversity = distinct / max(total_adapters, 1)
    cluster.avg_credibility = (
        sum(s.credibility for s in cluster.signals) / len(cluster.signals)
        if cluster.signals else 0.0
    )
    if cluster.signals:
        best = max(cluster.signals, key=lambda s: s.credibility)
        cluster.topic = best.title
    cluster.roles = {}
    for s in cluster.signals:
        role = s.signal_role or "unknown"
        cluster.roles[role] = cluster.roles.get(role, 0) + 1


def format_cluster_context(
    clusters: list[SignalCluster],
    *,
    max_clusters: int = 5,
) -> str | None:
    """Format top clusters as text for the synthesis prompt."""
    multi_source = [c for c in clusters if len(c.distinct_sources) > 1]
    if not multi_source:
        return None

    lines: list[str] = []
    for i, cluster in enumerate(multi_source[:max_clusters], 1):
        sources = ", ".join(sorted(cluster.distinct_sources))
        role_str = ", ".join(f"{r}={n}" for r, n in sorted(cluster.roles.items()))
        lines.append(
            f"{i}. [{cluster.topic}] — {len(cluster.signals)} signals from {sources} "
            f"(roles: {role_str}, credibility: {cluster.avg_credibility:.2f})"
        )

    return "\n".join(lines) if lines else None
