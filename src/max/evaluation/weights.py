"""Evaluation weights — static defaults + dynamic weight profiles."""

from __future__ import annotations

import json
from pathlib import Path

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

# Named weight profiles for different evaluation strategies
WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "default": DEFAULT_WEIGHTS,
    "quick_wins": {
        "pain_severity": 0.15,
        "addressable_scale": 0.10,
        "build_effort": 0.30,  # Heavily favor easy-to-build ideas
        "composability": 0.10,
        "competitive_density": 0.10,
        "timing_fit": 0.15,
        "compounding_value": 0.10,
    },
    "moonshots": {
        "pain_severity": 0.25,
        "addressable_scale": 0.20,
        "build_effort": 0.05,  # Don't penalize effort
        "composability": 0.10,
        "competitive_density": 0.15,
        "timing_fit": 0.05,
        "compounding_value": 0.20,  # Favor compounding value
    },
    "ecosystem": {
        "pain_severity": 0.10,
        "addressable_scale": 0.15,
        "build_effort": 0.10,
        "composability": 0.30,  # Heavily favor composability
        "competitive_density": 0.10,
        "timing_fit": 0.10,
        "compounding_value": 0.15,
    },
    "agent_first": {
        "pain_severity": 0.15,
        "addressable_scale": 0.20,
        "build_effort": 0.10,
        "composability": 0.20,
        "competitive_density": 0.05,
        "timing_fit": 0.15,
        "compounding_value": 0.15,
    },
}


def get_weights(profile: str = "default") -> dict[str, float]:
    """Get weights by profile name. Falls back to default if unknown."""
    return WEIGHT_PROFILES.get(profile, DEFAULT_WEIGHTS)


def compute_overall_score(
    dimension_values: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute weighted overall score (0-100) from dimension values (0-10 each)."""
    w = weights or DEFAULT_WEIGHTS
    score = sum(dimension_values.get(dim, 0) * weight for dim, weight in w.items())
    return round(score * 10, 2)  # Scale 0-10 weighted average to 0-100


def adapt_weights(
    outcomes: list[dict],
    base_weights: dict[str, float] | None = None,
    learning_rate: float = 0.05,
) -> dict[str, float]:
    """Adapt weights based on historical outcomes.

    Each outcome dict should contain:
        - dimension_values: dict[str, float] — scores per dimension
        - success: bool — whether the idea was ultimately approved/published
        - approval_score: int | None — 1-10 conviction score (optional)

    Dimensions that correlate with success get higher weights.
    When approval_score is present, strongly-approved ideas (score=10)
    contribute more to dimension averages than weakly-approved ones (score=5).
    """
    base = dict(base_weights or DEFAULT_WEIGHTS)

    if not outcomes:
        return base

    # Compute per-dimension success correlation
    adjustments: dict[str, float] = {dim: 0.0 for dim in base}

    successes = [o for o in outcomes if o.get("success")]
    failures = [o for o in outcomes if not o.get("success")]

    if not successes or not failures:
        return base

    for dim in base:
        # Score-weighted average for successes:
        # approval_score defaults to 5 for legacy rows without a score
        weights = [o.get("approval_score") or 5 for o in successes]
        weight_total = sum(weights)
        success_avg = sum(
            o["dimension_values"].get(dim, 0) * w
            for o, w in zip(successes, weights)
        ) / weight_total

        failure_count = len(failures)
        failure_avg = sum(
            o["dimension_values"].get(dim, 0)
            for o in failures
        ) / failure_count

        # Positive delta = dimension predicts success
        adjustments[dim] = (success_avg - failure_avg) * learning_rate

    # Apply adjustments and renormalize
    for dim in base:
        base[dim] = max(0.01, base[dim] + adjustments[dim])

    total = sum(base.values())
    return {dim: round(w / total, 4) for dim, w in base.items()}


def get_adapted_weights(
    profile: str,
    feedback_outcomes: list[dict],
    *,
    learning_rate: float = 0.05,
) -> tuple[dict[str, float], bool]:
    """Try feedback-adapted weights, fall back to static profile.

    Returns (weights, was_adapted). Falls back when there's no feedback,
    or feedback lacks diversity (all success or all failure).
    """
    base = get_weights(profile)

    if not feedback_outcomes:
        return base, False

    # Filter to outcomes that have dimension values
    valid = [o for o in feedback_outcomes if o.get("dimension_values")]
    if not valid:
        return base, False

    success_count = sum(1 for o in valid if o.get("success"))
    failure_count = len(valid) - success_count

    if success_count == 0 or failure_count == 0:
        return base, False

    adapted = adapt_weights(valid, base, learning_rate=learning_rate)
    return adapted, True


def save_weights(weights: dict[str, float], path: Path) -> None:
    """Persist a weight profile to a JSON file."""
    with open(path, "w") as f:
        json.dump(weights, f, indent=2)


def load_weights(path: Path) -> dict[str, float]:
    """Load a weight profile from a JSON file."""
    with open(path) as f:
        return json.load(f)
