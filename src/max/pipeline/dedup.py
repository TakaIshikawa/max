"""Semantic deduplication for pipeline outputs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from max.embeddings.engine import SemanticIndex
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight

logger = logging.getLogger(__name__)


def _extract_product_name(title: str) -> str:
    """Extract the product name (before the em dash) and normalize."""
    name = re.split(r"\s*[—–\-]\s*", title, maxsplit=1)[0]
    return name.strip().lower()


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
    existing_names: set[str] | None = None,
) -> DedupResult:
    """Filter duplicate buildable units against existing index + earlier batch items.

    Uses two-phase dedup:
    1. Title-prefix check — rejects ideas with a product name already in the store
    2. Embedding similarity — catches semantic duplicates with different names

    Args:
        existing_names: Product names already in the store (from prior runs).
    """
    kept: list[BuildableUnit] = []
    duplicates = 0
    seen_names: set[str] = set(existing_names or set())

    for unit in units:
        name = _extract_product_name(unit.title)
        text = f"{unit.title} {unit.one_liner} {unit.problem}"

        # Phase 1: exact name match against store or earlier batch items
        if name and name in seen_names:
            logger.debug("Duplicate idea '%s' (same product name)", unit.title)
            duplicates += 1
            continue

        # Phase 2: embedding similarity
        is_dup, dup_id = semantic_index.is_duplicate(text, "buildable_unit", threshold=threshold)
        if is_dup:
            logger.debug("Duplicate idea '%s' (matches %s)", unit.title, dup_id)
            duplicates += 1
            continue

        semantic_index.index_entity(unit.id, "buildable_unit", text)
        if name:
            seen_names.add(name)
        kept.append(unit)

    return DedupResult(kept=kept, duplicates=duplicates)
