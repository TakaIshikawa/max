"""Static evaluation weights and dimension definitions."""

from __future__ import annotations

# Static baseline weights (sum to 1.0)
DEFAULT_WEIGHTS: dict[str, float] = {
    "pain_severity": 0.20,
    "addressable_scale": 0.15,
    "build_effort": 0.15,
    "composability": 0.15,
    "competitive_density": 0.10,
    "timing_fit": 0.10,
    "compounding_value": 0.15,
}

# Dimensions where LOWER raw values are BETTER (inverted for scoring)
INVERTED_DIMENSIONS = {"build_effort", "competitive_density"}

DIMENSION_DESCRIPTIONS: dict[str, str] = {
    "pain_severity": "How painful is the problem? (0=trivial, 10=critical daily blocker)",
    "addressable_scale": "How many developers/agents face this? (0=niche, 10=universal)",
    "build_effort": "How hard to build an MVP? (0=months of work, 10=weekend project). INVERTED: lower effort = higher score.",
    "composability": "How well does it integrate with existing tools/ecosystems? (0=standalone island, 10=universal connector)",
    "competitive_density": "How crowded is the space? (0=red ocean, 10=blue ocean). INVERTED: fewer competitors = higher score.",
    "timing_fit": "How good is the timing? (0=too early/late, 10=perfect window)",
    "compounding_value": "Does value grow with usage/network effects? (0=linear, 10=exponential)",
}


def compute_overall_score(
    dimension_values: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute weighted overall score (0-100) from dimension values (0-10 each)."""
    w = weights or DEFAULT_WEIGHTS
    score = sum(dimension_values.get(dim, 0) * weight for dim, weight in w.items())
    return round(score * 10, 2)  # Scale 0-10 weighted average to 0-100
