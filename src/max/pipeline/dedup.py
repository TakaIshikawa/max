"""Semantic deduplication for pipeline outputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from max.embeddings.engine import SemanticIndex
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight

logger = logging.getLogger(__name__)


@dataclass
class DedupResult:
    """Result of a dedup pass."""

    kept: list
    duplicates: int


def dedup_insights(
    insights: list[Insight],
    semantic_index: SemanticIndex,
    *,
    threshold: float = 0.9,
) -> DedupResult:
    """Filter duplicate insights against existing index + earlier batch items.

    Each kept insight is indexed so later items in the same batch are checked
    against it.
    """
    kept: list[Insight] = []
    duplicates = 0

    for insight in insights:
        text = f"{insight.title} {insight.summary}"
        is_dup, dup_id = semantic_index.is_duplicate(text, "insight", threshold=threshold)
        if is_dup:
            logger.debug("Duplicate insight '%s' (matches %s)", insight.title, dup_id)
            duplicates += 1
        else:
            semantic_index.index_entity(insight.id, "insight", text)
            kept.append(insight)

    return DedupResult(kept=kept, duplicates=duplicates)


def dedup_buildable_units(
    units: list[BuildableUnit],
    semantic_index: SemanticIndex,
    *,
    threshold: float = 0.85,
) -> DedupResult:
    """Filter duplicate buildable units against existing index + earlier batch items."""
    kept: list[BuildableUnit] = []
    duplicates = 0

    for unit in units:
        text = f"{unit.title} {unit.one_liner} {unit.problem}"
        is_dup, dup_id = semantic_index.is_duplicate(text, "buildable_unit", threshold=threshold)
        if is_dup:
            logger.debug("Duplicate idea '%s' (matches %s)", unit.title, dup_id)
            duplicates += 1
        else:
            semantic_index.index_entity(unit.id, "buildable_unit", text)
            kept.append(unit)

    return DedupResult(kept=kept, duplicates=duplicates)
