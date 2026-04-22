"""Similarity search for stored buildable unit ideas."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass

from max.embeddings.engine import _cosine_similarity, embed_text
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit

BUILDABLE_UNIT_ENTITY_TYPE = "buildable_unit"


@dataclass(frozen=True)
class IdeaSimilarityResult:
    """A similar idea and its trace overlap with the query idea."""

    idea_id: str
    title: str
    problem_summary: str
    similarity_score: float
    overlapping_evidence_ids: list[str]
    overlapping_insight_ids: list[str]


def find_similar_ideas(
    store: Store,
    *,
    idea_id: str | None = None,
    query: str | None = None,
    threshold: float = 0.1,
    limit: int = 5,
) -> list[IdeaSimilarityResult]:
    """Find BuildableUnit records similar to an idea id or free-text query.

    Stored embeddings are used whenever present. Missing candidate embeddings
    are not created as a side effect; those candidates use deterministic token
    similarity so sparse test databases and older stores remain queryable.
    """
    if bool(idea_id) == bool(query and query.strip()):
        raise ValueError("Provide exactly one of idea_id or query")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")

    query_unit: BuildableUnit | None = None
    query_text = (query or "").strip()
    query_embedding: list[float] | None = None

    if idea_id:
        query_unit = store.get_buildable_unit(idea_id)
        if query_unit is None:
            raise LookupError(f"Idea not found: {idea_id}")
        query_text = _idea_similarity_text(query_unit)
        query_embedding = _stored_embedding(store, idea_id)

    embeddings_by_id = _stored_embeddings(store)
    if query_embedding is None and embeddings_by_id:
        query_embedding = embed_text(query_text)

    query_tokens = _token_counts(query_text)
    units = store.get_buildable_units(limit=max(limit * 10, 10000))

    scored: list[IdeaSimilarityResult] = []
    for unit in units:
        if query_unit and unit.id == query_unit.id:
            continue

        candidate_embedding = embeddings_by_id.get(unit.id)
        if query_embedding is not None and candidate_embedding is not None:
            score = _cosine_similarity(query_embedding, candidate_embedding)
        else:
            score = _deterministic_text_similarity(query_tokens, _token_counts(_idea_similarity_text(unit)))

        if score < threshold:
            continue

        scored.append(
            IdeaSimilarityResult(
                idea_id=unit.id,
                title=unit.title,
                problem_summary=_short_problem_summary(unit.problem),
                similarity_score=score,
                overlapping_evidence_ids=_overlap(
                    query_unit.evidence_signals if query_unit else [],
                    unit.evidence_signals,
                ),
                overlapping_insight_ids=_overlap(
                    query_unit.inspiring_insights if query_unit else [],
                    unit.inspiring_insights,
                ),
            )
        )

    scored.sort(key=lambda result: (-result.similarity_score, result.idea_id))
    return scored[:limit]


def _stored_embedding(store: Store, entity_id: str) -> list[float] | None:
    row = store.conn.execute(
        "SELECT embedding FROM embeddings WHERE id = ? AND entity_type = ?",
        (entity_id, BUILDABLE_UNIT_ENTITY_TYPE),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["embedding"])


def _stored_embeddings(store: Store) -> dict[str, list[float]]:
    rows = store.conn.execute(
        "SELECT id, embedding FROM embeddings WHERE entity_type = ?",
        (BUILDABLE_UNIT_ENTITY_TYPE,),
    ).fetchall()
    return {row["id"]: json.loads(row["embedding"]) for row in rows}


def _idea_similarity_text(unit: BuildableUnit) -> str:
    return " ".join(
        part
        for part in (
            unit.title,
            unit.one_liner,
            unit.problem,
            unit.solution,
            unit.value_proposition,
            unit.evidence_rationale,
        )
        if part
    )


def _short_problem_summary(problem: str, *, max_chars: int = 180) -> str:
    summary = " ".join(problem.split())
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 3].rstrip() + "..."


def _overlap(left: list[str], right: list[str]) -> list[str]:
    right_set = set(right)
    return [item for item in left if item in right_set]


def _token_counts(text: str) -> Counter[str]:
    return Counter(re.findall(r"[a-z0-9]+", text.lower()))


def _deterministic_text_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    dot = sum(left[token] * right[token] for token in shared)
    left_mag = math.sqrt(sum(count * count for count in left.values()))
    right_mag = math.sqrt(sum(count * count for count in right.values()))
    if left_mag == 0.0 or right_mag == 0.0:
        return 0.0
    return dot / (left_mag * right_mag)
