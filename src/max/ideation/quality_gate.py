"""Rule-based quality gate for revised ideas."""

from __future__ import annotations

from max.types.buildable_unit import BuildableUnit

GENERIC_PATTERNS = (
    "ai assistant",
    "dashboard",
    "marketplace",
)


def _has_specificity(unit: BuildableUnit) -> bool:
    return bool(unit.specific_user and unit.buyer and unit.workflow_context)


def quality_gate(
    units: list[BuildableUnit],
    *,
    min_quality_score: float = 6.0,
) -> tuple[list[BuildableUnit], list[BuildableUnit]]:
    """Keep ideas that pass minimum specificity and quality thresholds."""
    kept: list[BuildableUnit] = []
    rejected: list[BuildableUnit] = []

    for unit in units:
        tags = set(unit.rejection_tags)
        text = f"{unit.title} {unit.one_liner} {unit.solution}".lower()

        if not _has_specificity(unit):
            tags.add("insufficient_specificity")
        if not unit.evidence_rationale and not unit.inspiring_insights:
            tags.add("weak_evidence")
        if any(pattern in text for pattern in GENERIC_PATTERNS) and not unit.workflow_context:
            tags.add("generic_pattern")
        if unit.quality_score and unit.quality_score < min_quality_score:
            tags.add("low_quality_score")

        unit.rejection_tags = sorted(tags)
        if tags & {
            "no_clear_buyer",
            "generic_ai_assistant",
            "weak_evidence",
            "impossible_data_access",
            "too_broad",
            "unclear_workflow",
            "high_domain_risk",
            "insufficient_specificity",
            "generic_pattern",
            "low_quality_score",
        }:
            rejected.append(unit)
        else:
            kept.append(unit)

    return kept, rejected
