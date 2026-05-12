"""Vendor evaluation export for build-vs-buy decisions."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1
KIND = "vendor-evaluation"


class EvaluationCriterion(StrEnum):
    """Criteria used to compare build and vendor options."""

    FUNCTIONALITY_FIT = "functionality_fit"
    INTEGRATION_EASE = "integration_ease"
    TOTAL_COST = "total_cost"
    VENDOR_STABILITY = "vendor_stability"
    CUSTOMIZABILITY = "customizability"
    SUPPORT_QUALITY = "support_quality"
    SECURITY_COMPLIANCE = "security_compliance"
    SCALABILITY = "scalability"


CRITERIA: tuple[EvaluationCriterion, ...] = tuple(EvaluationCriterion)

DEFAULT_WEIGHTS: dict[str, float] = {
    EvaluationCriterion.FUNCTIONALITY_FIT.value: 0.22,
    EvaluationCriterion.INTEGRATION_EASE.value: 0.14,
    EvaluationCriterion.TOTAL_COST.value: 0.14,
    EvaluationCriterion.VENDOR_STABILITY.value: 0.10,
    EvaluationCriterion.CUSTOMIZABILITY.value: 0.14,
    EvaluationCriterion.SUPPORT_QUALITY.value: 0.08,
    EvaluationCriterion.SECURITY_COMPLIANCE.value: 0.10,
    EvaluationCriterion.SCALABILITY.value: 0.08,
}

_CRITERION_LABELS = {
    EvaluationCriterion.FUNCTIONALITY_FIT.value: "Functionality Fit",
    EvaluationCriterion.INTEGRATION_EASE.value: "Integration Ease",
    EvaluationCriterion.TOTAL_COST.value: "Total Cost",
    EvaluationCriterion.VENDOR_STABILITY.value: "Vendor Stability",
    EvaluationCriterion.CUSTOMIZABILITY.value: "Customizability",
    EvaluationCriterion.SUPPORT_QUALITY.value: "Support Quality",
    EvaluationCriterion.SECURITY_COMPLIANCE.value: "Security Compliance",
    EvaluationCriterion.SCALABILITY.value: "Scalability",
}


def build_vendor_evaluation(unit: dict[str, Any], alternatives: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a weighted build-vs-buy vendor evaluation matrix."""
    build_option = _build_option(unit)
    vendor_options = [_vendor_option(alternative) for alternative in alternatives]
    options = [build_option, *vendor_options]
    weighted_scores = _weighted_scores(options)
    comparison_matrix = _comparison_matrix(options)
    recommendation = _recommendation(build_option, vendor_options, weighted_scores)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "vendor_evaluation",
            "idea_id": _text(unit.get("id"), unit.get("idea_id"), unit.get("source_id")),
            "title": _text(unit.get("title"), unit.get("name"), "Untitled build option"),
        },
        "criteria": [
            {
                "key": criterion.value,
                "label": _CRITERION_LABELS[criterion.value],
                "weight": DEFAULT_WEIGHTS[criterion.value],
            }
            for criterion in CRITERIA
        ],
        "build_option": build_option,
        "vendor_options": vendor_options,
        "comparison_matrix": comparison_matrix,
        "weighted_scores": weighted_scores,
        "recommendation": recommendation,
        "decision_factors": _decision_factors(options, weighted_scores),
    }


def render_vendor_evaluation_markdown(evaluation: dict[str, Any]) -> str:
    """Render a vendor evaluation as Markdown with a comparison table."""
    source = evaluation.get("source", {})
    recommendation = evaluation.get("recommendation", {})
    options = [evaluation.get("build_option", {}), *evaluation.get("vendor_options", [])]
    option_names = [_option_name(option) for option in options]
    lines = [
        f"# Vendor Evaluation: {_md(source.get('title') or source.get('idea_id') or 'Untitled')}",
        "",
        f"Schema: `{evaluation['schema_version']}`",
        f"Generated: {evaluation['generated_at']}",
        "",
        "## Recommendation",
        "",
        f"- Decision: **{_md(recommendation.get('decision', 'build'))}**",
        f"- Winner: {_md(recommendation.get('winning_option', 'Build'))}",
        f"- Justification: {_md(recommendation.get('justification', 'No justification available.'))}",
        "",
        "## Comparison Matrix",
        "",
        "| Criterion | Weight | " + " | ".join(_md(name) for name in option_names) + " |",
        "| --- | ---: | " + " | ".join("---:" for _ in option_names) + " |",
    ]

    for row in evaluation.get("comparison_matrix", []):
        scores = " | ".join(f"{float(row['scores'].get(name, 0.0)):.1f}" for name in option_names)
        lines.append(f"| {_md(row['criterion_label'])} | {float(row['weight']):.2f} | {scores} |")

    totals = evaluation.get("weighted_scores", {})
    lines.append(
        "| **Weighted Total** | 1.00 | "
        + " | ".join(f"**{float(totals.get(name, 0.0)):.1f}**" for name in option_names)
        + " |"
    )

    lines.extend(["", "## Decision Factors", ""])
    factors = evaluation.get("decision_factors", [])
    if factors:
        for factor in factors:
            lines.append(f"- {_md(factor)}")
    else:
        lines.append("- No differentiating factors identified.")
    return "\n".join(lines).rstrip() + "\n"


def render_vendor_evaluation_json(evaluation: dict[str, Any]) -> str:
    """Render a vendor evaluation as stable JSON."""
    return json.dumps(evaluation, indent=2, sort_keys=True, default=str)


def render_vendor_evaluation_csv(evaluation: dict[str, Any]) -> str:
    """Render a flat comparison matrix as CSV."""
    output = io.StringIO()
    options = [evaluation.get("build_option", {}), *evaluation.get("vendor_options", [])]
    option_names = [_option_name(option) for option in options]
    writer = csv.DictWriter(
        output,
        fieldnames=["criterion", "criterion_label", "weight", *option_names],
    )
    writer.writeheader()
    for row in evaluation.get("comparison_matrix", []):
        writer.writerow(
            {
                "criterion": row["criterion"],
                "criterion_label": row["criterion_label"],
                "weight": row["weight"],
                **{name: row["scores"].get(name, 0.0) for name in option_names},
            }
        )
    writer.writerow(
        {
            "criterion": "weighted_total",
            "criterion_label": "Weighted Total",
            "weight": 1.0,
            **evaluation.get("weighted_scores", {}),
        }
    )
    return output.getvalue()


def _build_option(unit: dict[str, Any]) -> dict[str, Any]:
    explicit = _scores(unit)
    score = _number_from_paths(unit, ("evaluation", "overall_score"), ("quality", "quality_score"), ("score",), default=72.0)
    effort = _number_from_paths(unit, ("implementation_effort",), ("effort_score",), ("complexity_score",), default=45.0)
    cost = _number_from_paths(unit, ("estimated_cost",), ("build_cost",), ("cost",), default=None)
    scores = {
        EvaluationCriterion.FUNCTIONALITY_FIT.value: _score(explicit, EvaluationCriterion.FUNCTIONALITY_FIT, score),
        EvaluationCriterion.INTEGRATION_EASE.value: _score(explicit, EvaluationCriterion.INTEGRATION_EASE, 72.0 - min(effort * 0.25, 20.0)),
        EvaluationCriterion.TOTAL_COST.value: _score(explicit, EvaluationCriterion.TOTAL_COST, _cost_score(cost, default=62.0)),
        EvaluationCriterion.VENDOR_STABILITY.value: _score(explicit, EvaluationCriterion.VENDOR_STABILITY, 68.0),
        EvaluationCriterion.CUSTOMIZABILITY.value: _score(explicit, EvaluationCriterion.CUSTOMIZABILITY, 88.0),
        EvaluationCriterion.SUPPORT_QUALITY.value: _score(explicit, EvaluationCriterion.SUPPORT_QUALITY, 58.0),
        EvaluationCriterion.SECURITY_COMPLIANCE.value: _score(explicit, EvaluationCriterion.SECURITY_COMPLIANCE, _security_score(unit, default=70.0)),
        EvaluationCriterion.SCALABILITY.value: _score(explicit, EvaluationCriterion.SCALABILITY, _scale_score(unit, default=70.0)),
    }
    return {
        "id": _text(unit.get("id"), unit.get("idea_id"), "build"),
        "name": _text(unit.get("title"), unit.get("name"), "Build in-house"),
        "type": "build",
        "description": _text(unit.get("summary"), unit.get("description"), unit.get("solution"), ""),
        "scores": scores,
    }


def _vendor_option(alternative: dict[str, Any]) -> dict[str, Any]:
    explicit = _scores(alternative)
    cost = _number_from_paths(alternative, ("annual_cost",), ("total_cost",), ("price",), ("cost",), default=None)
    scores = {
        EvaluationCriterion.FUNCTIONALITY_FIT.value: _score(explicit, EvaluationCriterion.FUNCTIONALITY_FIT, _number_from_paths(alternative, ("fit_score",), ("feature_match",), default=72.0)),
        EvaluationCriterion.INTEGRATION_EASE.value: _score(explicit, EvaluationCriterion.INTEGRATION_EASE, _number_from_paths(alternative, ("integration_score",), default=70.0)),
        EvaluationCriterion.TOTAL_COST.value: _score(explicit, EvaluationCriterion.TOTAL_COST, _cost_score(cost, default=68.0)),
        EvaluationCriterion.VENDOR_STABILITY.value: _score(explicit, EvaluationCriterion.VENDOR_STABILITY, _number_from_paths(alternative, ("stability_score",), ("market_presence",), default=70.0)),
        EvaluationCriterion.CUSTOMIZABILITY.value: _score(explicit, EvaluationCriterion.CUSTOMIZABILITY, _number_from_paths(alternative, ("customizability_score",), default=58.0)),
        EvaluationCriterion.SUPPORT_QUALITY.value: _score(explicit, EvaluationCriterion.SUPPORT_QUALITY, _number_from_paths(alternative, ("support_score",), default=70.0)),
        EvaluationCriterion.SECURITY_COMPLIANCE.value: _score(explicit, EvaluationCriterion.SECURITY_COMPLIANCE, _security_score(alternative, default=72.0)),
        EvaluationCriterion.SCALABILITY.value: _score(explicit, EvaluationCriterion.SCALABILITY, _scale_score(alternative, default=72.0)),
    }
    return {
        "id": _text(alternative.get("id"), alternative.get("vendor_id"), alternative.get("name"), "vendor"),
        "name": _text(alternative.get("name"), alternative.get("vendor"), "Unnamed vendor"),
        "type": "buy",
        "description": _text(alternative.get("summary"), alternative.get("description"), ""),
        "scores": scores,
    }


def _comparison_matrix(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for criterion in CRITERIA:
        rows.append(
            {
                "criterion": criterion.value,
                "criterion_label": _CRITERION_LABELS[criterion.value],
                "weight": DEFAULT_WEIGHTS[criterion.value],
                "scores": {
                    _option_name(option): round(float(option["scores"].get(criterion.value, 0.0)), 1)
                    for option in options
                },
            }
        )
    return rows


def _weighted_scores(options: list[dict[str, Any]]) -> dict[str, float]:
    totals = {}
    for option in options:
        total = sum(
            float(option["scores"].get(criterion.value, 0.0)) * DEFAULT_WEIGHTS[criterion.value]
            for criterion in CRITERIA
        )
        totals[_option_name(option)] = round(total, 1)
    return totals


def _recommendation(
    build_option: dict[str, Any],
    vendor_options: list[dict[str, Any]],
    weighted_scores: dict[str, float],
) -> dict[str, Any]:
    build_name = _option_name(build_option)
    build_score = weighted_scores.get(build_name, 0.0)
    if not vendor_options:
        return {
            "decision": "build",
            "winning_option": build_name,
            "score": build_score,
            "justification": "No vendor alternatives were provided, so the in-house build is the only viable option.",
        }

    vendor_names = [_option_name(option) for option in vendor_options]
    best_vendor = max(vendor_names, key=lambda name: weighted_scores.get(name, 0.0))
    vendor_score = weighted_scores[best_vendor]
    delta = round(vendor_score - build_score, 1)
    if delta >= 8.0:
        decision = "buy"
        winner = best_vendor
        justification = f"{best_vendor} leads the build option by {delta:.1f} weighted points."
    elif delta <= -8.0:
        decision = "build"
        winner = build_name
        justification = f"The build option leads the strongest vendor by {abs(delta):.1f} weighted points."
    else:
        decision = "hybrid"
        winner = best_vendor if vendor_score >= build_score else build_name
        justification = (
            "The top build and buy options are close enough that a hybrid approach should preserve "
            "internal differentiation while using vendor capabilities where they reduce delivery risk."
        )
    return {
        "decision": decision,
        "winning_option": winner,
        "score": weighted_scores[winner],
        "build_score": build_score,
        "best_vendor_score": vendor_score,
        "justification": justification,
    }


def _decision_factors(options: list[dict[str, Any]], weighted_scores: dict[str, float]) -> list[str]:
    if not options:
        return []
    factors = []
    winner_name = max(weighted_scores, key=weighted_scores.get)
    winner = next(option for option in options if _option_name(option) == winner_name)
    for criterion in CRITERIA:
        sorted_options = sorted(
            options,
            key=lambda option: float(option["scores"].get(criterion.value, 0.0)),
            reverse=True,
        )
        leader = sorted_options[0]
        runner_up = sorted_options[1] if len(sorted_options) > 1 else None
        if runner_up is None:
            continue
        spread = float(leader["scores"][criterion.value]) - float(runner_up["scores"][criterion.value])
        if spread >= 12.0 or _option_name(leader) == winner_name:
            factors.append(
                f"{_option_name(leader)} leads {_CRITERION_LABELS[criterion.value].lower()} "
                f"by {spread:.1f} points."
            )
    if not factors:
        factors.append(f"{winner_name} has the highest weighted total at {weighted_scores[winner_name]:.1f}.")
    if winner.get("type") == "build":
        factors.append("Build option preserves maximum customizability and roadmap control.")
    else:
        factors.append("Vendor option reduces ownership burden for support and operational maturity.")
    return factors[:5]


def _scores(item: dict[str, Any]) -> dict[str, float]:
    scores = item.get("scores")
    if not isinstance(scores, dict):
        scores = item.get("criteria_scores")
    if not isinstance(scores, dict):
        return {}
    return {str(key): _clamp(value) for key, value in scores.items()}


def _score(scores: dict[str, float], criterion: EvaluationCriterion, default: float) -> float:
    return round(_clamp(scores.get(criterion.value, default)), 1)


def _cost_score(cost: float | None, *, default: float) -> float:
    if cost is None:
        return default
    if cost <= 25_000:
        return 90.0
    if cost <= 100_000:
        return 80.0
    if cost <= 250_000:
        return 68.0
    if cost <= 500_000:
        return 55.0
    return 42.0


def _security_score(item: dict[str, Any], *, default: float) -> float:
    explicit = _number_from_paths(item, ("security_score",), ("compliance_score",), default=None)
    if explicit is not None:
        return explicit
    certifications = item.get("certifications") or item.get("compliance")
    values = _list(certifications)
    if any(str(value).lower() in {"soc2", "soc 2", "iso27001", "hipaa", "gdpr"} for value in values):
        return 84.0
    return default


def _scale_score(item: dict[str, Any], *, default: float) -> float:
    explicit = _number_from_paths(item, ("scalability_score",), ("scale_score",), default=None)
    if explicit is not None:
        return explicit
    text = " ".join(str(item.get(key, "")) for key in ("scale", "scale_tier", "description", "summary")).lower()
    if any(term in text for term in ("enterprise", "global", "high scale", "multi-region")):
        return 84.0
    return default


def _number_from_paths(item: dict[str, Any], *paths: tuple[str, ...], default: float | None) -> float | None:
    for path in paths:
        current: Any = item
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if current is not None:
            try:
                return float(current)
            except (TypeError, ValueError):
                continue
    return default


def _clamp(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(numeric, 100.0))


def _option_name(option: dict[str, Any]) -> str:
    return _text(option.get("name"), option.get("id"), "Unnamed option")


def _text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            value = value.get("title") or value.get("name") or value.get("approach")
        text = str(value).strip()
        if text:
            return text
    return ""


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")
