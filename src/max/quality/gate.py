"""Domain quality enforcement gate."""

from __future__ import annotations

from max.quality.scorer import DomainQualityScore
from max.types.buildable_unit import BuildableUnit


def enforce_domain_quality_gate(
    units: list[BuildableUnit],
    scores: list[DomainQualityScore],
) -> tuple[list[BuildableUnit], list[BuildableUnit]]:
    """Split units into pass/reject lists and annotate unit quality fields."""
    score_by_id = {score.buildable_unit_id: score for score in scores}
    kept: list[BuildableUnit] = []
    rejected: list[BuildableUnit] = []
    for unit in units:
        score = score_by_id.get(unit.id)
        if not score:
            kept.append(unit)
            continue
        unit.quality_score = round(score.overall_score / 10.0, 2)
        unit.rejection_tags = sorted(set([*unit.rejection_tags, *score.rejection_tags]))
        if score.passed_gate:
            kept.append(unit)
        else:
            rejected.append(unit)
    return kept, rejected
