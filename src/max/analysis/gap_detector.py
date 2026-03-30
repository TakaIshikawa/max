"""Gap detection — find validated unmet needs (problems without solutions)."""

from __future__ import annotations

from dataclasses import dataclass, field

from max.analysis.triangulation import triangulate
from max.embeddings.engine import _cosine_similarity, embed_text
from max.store.db import Store
from max.types.signal import Signal


@dataclass
class Gap:
    """A problem-solution gap: strong problem evidence, weak/no solution evidence."""

    topic: str
    problem_signals: list[Signal] = field(default_factory=list)
    solution_signals: list[Signal] = field(default_factory=list)
    gap_score: float = 0.0
    source_diversity: float = 0.0

    @property
    def problem_strength(self) -> float:
        """How well-evidenced is the problem."""
        if not self.problem_signals:
            return 0.0
        n = len(self.problem_signals)
        avg_cred = sum(s.credibility for s in self.problem_signals) / n
        distinct_sources = len({s.source_adapter for s in self.problem_signals})
        return min(1.0, avg_cred * (distinct_sources / 3.0) * min(n / 2.0, 1.0))

    @property
    def solution_coverage(self) -> float:
        """How well-covered by existing solutions (0 = total gap, 1 = fully covered)."""
        if not self.solution_signals:
            return 0.0
        avg_cred = sum(s.credibility for s in self.solution_signals) / len(self.solution_signals)
        return min(1.0, avg_cred * len(self.solution_signals) / 3.0)


def detect_gaps(
    store: Store,
    *,
    signal_limit: int = 200,
    similarity_threshold: float = 0.55,
    min_gap_score: float = 0.2,
    max_gaps: int = 10,
) -> list[Gap]:
    """Detect problem-solution gaps from stored signals.

    1. Load recent signals with roles
    2. Separate into problem and solution pools
    3. Cluster problem signals
    4. For each problem cluster, search for corresponding solution signals
    5. Score the gap (strong problem + weak solution = high gap score)
    """
    signals = store.get_signals(limit=signal_limit)
    if not signals:
        return []

    problems = [s for s in signals if s.signal_role == "problem"]
    solutions = [s for s in signals if s.signal_role == "solution"]

    if not problems:
        return []

    problem_clusters = triangulate(problems, similarity_threshold=0.60)

    # Pre-embed all solution signals
    solution_embeddings: list[tuple[Signal, list[float]]] = []
    for sol in solutions:
        text = f"{sol.title} {sol.content[:200]}"
        emb = embed_text(text)
        solution_embeddings.append((sol, emb))

    gaps: list[Gap] = []
    for cluster in problem_clusters:
        if not cluster.signals:
            continue

        matching_solutions: list[Signal] = []
        for sol, sol_emb in solution_embeddings:
            sim = _cosine_similarity(cluster.centroid, sol_emb)
            if sim >= similarity_threshold:
                matching_solutions.append(sol)

        gap = Gap(
            topic=cluster.topic,
            problem_signals=cluster.signals,
            solution_signals=matching_solutions,
            source_diversity=cluster.source_diversity,
        )
        gap.gap_score = gap.problem_strength * (1.0 - gap.solution_coverage)

        if gap.gap_score >= min_gap_score:
            gaps.append(gap)

    gaps.sort(key=lambda g: g.gap_score, reverse=True)
    return gaps[:max_gaps]


def format_gaps_for_ideation(gaps: list[Gap], *, max_gaps: int = 5) -> str | None:
    """Format top gaps as structured text for the ideation prompt."""
    if not gaps:
        return None

    lines = [
        "VALIDATED UNMET NEEDS — problems with strong evidence but no adequate existing solutions:\n"
    ]
    for i, gap in enumerate(gaps[:max_gaps], 1):
        sources = ", ".join(sorted({s.source_adapter for s in gap.problem_signals}))
        lines.append(f"{i}. {gap.topic}")
        lines.append(
            f"   Gap score: {gap.gap_score:.2f} | Sources: {sources} "
            f"| Problem signals: {len(gap.problem_signals)} "
            f"| Solution signals: {len(gap.solution_signals)}"
        )
        for sig in gap.problem_signals[:3]:
            lines.append(f"   - [{sig.source_adapter}] {sig.title}")
        lines.append("")

    lines.append(
        "Prioritize ideas that address these validated gaps — "
        "they represent the highest-value opportunities."
    )
    return "\n".join(lines)
