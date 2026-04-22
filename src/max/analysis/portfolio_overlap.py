"""Portfolio overlap and cannibalization analysis for generated ideas."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from max.embeddings.engine import _cosine_similarity
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit

BUILDABLE_UNIT_ENTITY_TYPE = "buildable_unit"


@dataclass(frozen=True)
class PortfolioOverlapReason:
    type: str
    description: str
    score: float
    shared_terms: list[str] = field(default_factory=list)
    shared_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PortfolioOverlapCluster:
    cluster_id: str
    idea_ids: list[str]
    representative_idea_ids: list[str]
    overlap_score: float
    overlap_reasons: list[PortfolioOverlapReason]
    suggested_action: str


def find_portfolio_overlap_clusters(
    store: Store,
    *,
    limit: int = 20,
    min_overlap_score: float = 0.35,
    include_archived: bool = False,
) -> list[PortfolioOverlapCluster]:
    """Find idea clusters with portfolio overlap or cannibalization risk.

    The analysis is deterministic and only uses stored embeddings when they
    already exist; it does not create embeddings as a side effect.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not 0.0 <= min_overlap_score <= 1.0:
        raise ValueError("min_overlap_score must be between 0 and 1")

    units = store.get_buildable_units(limit=10000)
    if not include_archived:
        units = [unit for unit in units if unit.status != "archived"]
    if len(units) < 2:
        return []

    embeddings = _stored_embeddings(store)
    features = {unit.id: _idea_features(unit) for unit in units}
    by_id = {unit.id: unit for unit in units}

    pair_scores: dict[tuple[str, str], tuple[float, list[PortfolioOverlapReason]]] = {}
    adjacency: dict[str, set[str]] = {unit.id: set() for unit in units}
    for left, right in combinations(units, 2):
        score, reasons = _pair_overlap(
            left,
            right,
            left_features=features[left.id],
            right_features=features[right.id],
            left_embedding=embeddings.get(left.id),
            right_embedding=embeddings.get(right.id),
        )
        if score < min_overlap_score:
            continue
        key = tuple(sorted((left.id, right.id)))
        pair_scores[key] = (score, reasons)
        adjacency[left.id].add(right.id)
        adjacency[right.id].add(left.id)

    clusters: list[PortfolioOverlapCluster] = []
    visited: set[str] = set()
    for idea_id in sorted(adjacency):
        if idea_id in visited or not adjacency[idea_id]:
            continue
        component = _component(idea_id, adjacency, visited)
        if len(component) < 2:
            continue
        clusters.append(_build_cluster(component, by_id=by_id, pair_scores=pair_scores))

    clusters.sort(key=lambda cluster: (-cluster.overlap_score, cluster.cluster_id))
    return clusters[:limit]


def _component(start: str, adjacency: dict[str, set[str]], visited: set[str]) -> list[str]:
    stack = [start]
    component: list[str] = []
    visited.add(start)
    while stack:
        idea_id = stack.pop()
        component.append(idea_id)
        for neighbor in sorted(adjacency[idea_id], reverse=True):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return sorted(component)


def _build_cluster(
    idea_ids: list[str],
    *,
    by_id: dict[str, BuildableUnit],
    pair_scores: dict[tuple[str, str], tuple[float, list[PortfolioOverlapReason]]],
) -> PortfolioOverlapCluster:
    relevant_pairs = [
        pair_scores[tuple(sorted((left, right)))]
        for left, right in combinations(idea_ids, 2)
        if tuple(sorted((left, right))) in pair_scores
    ]
    overlap_score = sum(score for score, _ in relevant_pairs) / len(relevant_pairs)
    reasons = _merge_reasons([reason for _, pair_reasons in relevant_pairs for reason in pair_reasons])
    representative_ids = sorted(
        idea_ids,
        key=lambda item: (
            -float(by_id[item].quality_score or 0.0),
            -float(by_id[item].usefulness_score or 0.0),
            by_id[item].id,
        ),
    )[:3]
    return PortfolioOverlapCluster(
        cluster_id="overlap-" + "-".join(idea_ids[:3]),
        idea_ids=idea_ids,
        representative_idea_ids=representative_ids,
        overlap_score=round(overlap_score, 3),
        overlap_reasons=reasons,
        suggested_action=_suggest_action(overlap_score, reasons),
    )


def _pair_overlap(
    left: BuildableUnit,
    right: BuildableUnit,
    *,
    left_features: dict[str, Any],
    right_features: dict[str, Any],
    left_embedding: list[float] | None,
    right_embedding: list[float] | None,
) -> tuple[float, list[PortfolioOverlapReason]]:
    reasons: list[PortfolioOverlapReason] = []

    user_terms = sorted(left_features["users"] & right_features["users"])
    user_score = _jaccard(left_features["users"], right_features["users"])
    if user_score > 0:
        reasons.append(
            PortfolioOverlapReason(
                type="target_users",
                description="Shared target user or buyer language",
                score=round(user_score, 3),
                shared_terms=user_terms[:12],
            )
        )

    problem_score = _cosine_counts(left_features["problem"], right_features["problem"])
    problem_terms = sorted(set(left_features["problem"]) & set(right_features["problem"]))
    if problem_score >= 0.18:
        reasons.append(
            PortfolioOverlapReason(
                type="problem_statement",
                description="Similar problem statement language",
                score=round(problem_score, 3),
                shared_terms=problem_terms[:12],
            )
        )

    stack_terms = sorted(left_features["stack"] & right_features["stack"])
    stack_score = _jaccard(left_features["stack"], right_features["stack"])
    if stack_score > 0:
        reasons.append(
            PortfolioOverlapReason(
                type="stack_keywords",
                description="Shared technical stack or implementation keywords",
                score=round(stack_score, 3),
                shared_terms=stack_terms[:12],
            )
        )

    evidence_ids = _ordered_overlap(left.evidence_signals, right.evidence_signals)
    evidence_score = len(evidence_ids) / max(len(set(left.evidence_signals) | set(right.evidence_signals)), 1)
    if evidence_ids:
        reasons.append(
            PortfolioOverlapReason(
                type="evidence_signal_ids",
                description="Shared source evidence signals",
                score=round(evidence_score, 3),
                shared_ids=evidence_ids,
            )
        )

    embedding_score = 0.0
    if left_embedding is not None and right_embedding is not None:
        embedding_score = max(0.0, _cosine_similarity(left_embedding, right_embedding))
        if embedding_score >= 0.75:
            reasons.append(
                PortfolioOverlapReason(
                    type="embedding_similarity",
                    description="Stored embeddings indicate semantic similarity",
                    score=round(embedding_score, 3),
                )
            )

    score = (
        user_score * 0.18
        + problem_score * 0.30
        + stack_score * 0.14
        + evidence_score * 0.28
        + embedding_score * 0.10
    )
    return min(round(score, 6), 1.0), reasons


def _merge_reasons(reasons: list[PortfolioOverlapReason]) -> list[PortfolioOverlapReason]:
    merged: dict[str, PortfolioOverlapReason] = {}
    for reason in reasons:
        existing = merged.get(reason.type)
        if existing is None:
            merged[reason.type] = reason
            continue
        merged[reason.type] = PortfolioOverlapReason(
            type=reason.type,
            description=reason.description,
            score=round(max(existing.score, reason.score), 3),
            shared_terms=sorted(set(existing.shared_terms) | set(reason.shared_terms))[:12],
            shared_ids=sorted(set(existing.shared_ids) | set(reason.shared_ids))[:12],
        )
    return sorted(merged.values(), key=lambda reason: (-reason.score, reason.type))


def _suggest_action(score: float, reasons: list[PortfolioOverlapReason]) -> str:
    reason_types = {reason.type for reason in reasons}
    if score >= 0.65 or {"problem_statement", "evidence_signal_ids", "target_users"} <= reason_types:
        return "merge"
    if score >= 0.4 or {"problem_statement", "target_users"} <= reason_types:
        return "differentiate"
    return "keep separate"


def _idea_features(unit: BuildableUnit) -> dict[str, Any]:
    return {
        "users": set(
            _tokens(
                " ".join(
                    [
                        unit.target_users,
                        unit.specific_user,
                        unit.buyer,
                        unit.workflow_context,
                    ]
                )
            )
        ),
        "problem": _token_counts(
            " ".join(
                [
                    unit.title,
                    unit.one_liner,
                    unit.problem,
                    unit.current_workaround,
                    unit.value_proposition,
                ]
            )
        ),
        "stack": set(_stack_keywords(unit)),
    }


def _stack_keywords(unit: BuildableUnit) -> list[str]:
    values = [unit.tech_approach, unit.composability_notes]
    values.extend(_flatten_stack(unit.suggested_stack))
    return _tokens(" ".join(str(value) for value in values if value))


def _flatten_stack(value: Any) -> list[str]:
    if isinstance(value, dict):
        flattened: list[str] = []
        for key, item in value.items():
            flattened.append(str(key))
            flattened.extend(_flatten_stack(item))
        return flattened
    if isinstance(value, list | tuple | set):
        flattened = []
        for item in value:
            flattened.extend(_flatten_stack(item))
        return flattened
    if value in (None, ""):
        return []
    return [str(value)]


def _stored_embeddings(store: Store) -> dict[str, list[float]]:
    rows = store.conn.execute(
        "SELECT id, embedding FROM embeddings WHERE entity_type = ?",
        (BUILDABLE_UNIT_ENTITY_TYPE,),
    ).fetchall()
    return {row["id"]: json.loads(row["embedding"]) for row in rows}


def _ordered_overlap(left: list[str], right: list[str]) -> list[str]:
    right_set = set(right)
    return [item for item in left if item in right_set]


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in _STOPWORDS
    ]


def _token_counts(text: str) -> Counter[str]:
    return Counter(_tokens(text))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cosine_counts(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    dot = sum(left[token] * right[token] for token in shared)
    left_mag = math.sqrt(sum(count * count for count in left.values()))
    right_mag = math.sqrt(sum(count * count for count in right.values()))
    if left_mag == 0.0 or right_mag == 0.0:
        return 0.0
    return dot / (left_mag * right_mag)


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "both",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "need",
    "needs",
    "no",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}
