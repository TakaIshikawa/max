"""Deterministic domain quality scoring for generated ideas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from max.profiles.schema import DomainContext, DomainQualityConfig
from max.types.buildable_unit import BuildableUnit


@dataclass
class DomainQualityScore:
    buildable_unit_id: str
    domain: str
    profile_name: str
    rubric_version: str
    dimensions: dict[str, float]
    overall_score: float
    passed_gate: bool
    rejection_tags: list[str] = field(default_factory=list)
    reasoning: str = ""


def score_domain_quality(
    units: list[BuildableUnit],
    *,
    domain: DomainContext | None,
    config: DomainQualityConfig | None,
    profile_name: str = "",
    evidence_pack: Any | None = None,
    memory: list[dict] | None = None,
) -> list[DomainQualityScore]:
    """Score ideas against a profile-specific domain quality rubric."""
    if not domain or not config or not config.enabled:
        return []
    return [
        score_unit_domain_quality(
            unit,
            domain=domain,
            config=config,
            profile_name=profile_name,
            evidence_pack=evidence_pack,
            memory=memory or [],
        )
        for unit in units
    ]


def score_unit_domain_quality(
    unit: BuildableUnit,
    *,
    domain: DomainContext,
    config: DomainQualityConfig,
    profile_name: str = "",
    evidence_pack: Any | None = None,
    memory: list[dict] | None = None,
) -> DomainQualityScore:
    tags: list[str] = []
    dimensions: dict[str, float] = {}
    text = _idea_text(unit)

    for field_name in config.required_fields:
        if not _field_value(unit, field_name):
            tags.append(_missing_tag(field_name))

    tags.extend(_pattern_rejection_tags(text, domain, config))

    for name in config.scoring_dimensions:
        dimensions[name] = _score_dimension(name, unit, text, domain, evidence_pack, memory or [])
    if not dimensions:
        dimensions = _default_dimensions(unit, text, domain, evidence_pack, memory or [])

    weighted_total = 0.0
    weight_sum = 0.0
    for name, value in dimensions.items():
        weight = config.scoring_dimensions.get(name).weight if name in config.scoring_dimensions else 1.0
        weighted_total += value * weight
        weight_sum += weight
    overall = round((weighted_total / weight_sum) * 10.0, 2) if weight_sum else 0.0

    hard_rejections = set(config.hard_rejections)
    passed = overall >= config.min_score and not hard_rejections.intersection(tags)
    if "missing_buyer" in tags and "no_clear_buyer" in hard_rejections:
        passed = False
    reasoning = _reasoning(overall, tags, dimensions)

    return DomainQualityScore(
        buildable_unit_id=unit.id,
        domain=domain.name,
        profile_name=profile_name,
        rubric_version=config.rubric_version,
        dimensions=dimensions,
        overall_score=overall,
        passed_gate=passed,
        rejection_tags=sorted(set(tags)),
        reasoning=reasoning,
    )


def _default_dimensions(
    unit: BuildableUnit,
    text: str,
    domain: DomainContext,
    evidence_pack: Any | None,
    memory: list[dict],
) -> dict[str, float]:
    return {
        "workflow_specificity": _specificity_score(unit.workflow_context or unit.problem),
        "buyer_clarity": 9.0 if unit.buyer.strip() else 3.0,
        "evidence_support": _evidence_score(unit, evidence_pack),
        "implementation_feasibility": _implementation_score(unit),
        "differentiation": _differentiation_score(text, domain, memory),
        "distribution_path": _distribution_score(unit),
        "domain_risk_control": _risk_control_score(unit, domain),
    }


def _score_dimension(
    name: str,
    unit: BuildableUnit,
    text: str,
    domain: DomainContext,
    evidence_pack: Any | None,
    memory: list[dict],
) -> float:
    if name in {"workflow_specificity", "validation_feasibility"}:
        return _specificity_score(unit.workflow_context or unit.validation_plan or unit.problem)
    if name in {"buyer_clarity", "admin_roi"}:
        return 9.0 if unit.buyer.strip() else 3.0
    if name == "evidence_support":
        return _evidence_score(unit, evidence_pack)
    if name in {"implementation_feasibility", "ehr_dependency_risk"}:
        return _implementation_score(unit)
    if name == "measurable_infra_impact":
        return _measurable_infra_score(unit)
    if name == "deployment_fit":
        return _deployment_fit_score(unit)
    if name in {"differentiation", "compliance_fit", "clinical_safety_boundary"}:
        return _differentiation_score(text, domain, memory)
    if name == "distribution_path":
        return _distribution_score(unit)
    if name == "domain_risk_control":
        return _risk_control_score(unit, domain)
    return 6.0


def _specificity_score(value: str) -> float:
    value = value.strip()
    if not value:
        return 2.0
    score = 5.0
    if len(value.split()) >= 8:
        score += 2.0
    if any(token in value.lower() for token in ["during", "before", "after", "when", "workflow", "ci", "intake", "authorization"]):
        score += 1.5
    return min(score, 10.0)


def _evidence_score(unit: BuildableUnit, evidence_pack: Any | None) -> float:
    score = 4.0
    if unit.evidence_rationale.strip():
        score += 2.0
    if unit.inspiring_insights:
        score += min(2.0, len(unit.inspiring_insights) * 0.75)
    if unit.evidence_signals:
        score += min(2.0, len(unit.evidence_signals) * 0.5)
    if evidence_pack is not None:
        score += 0.5
    return min(score, 10.0)


def _implementation_score(unit: BuildableUnit) -> float:
    score = 5.0
    if unit.tech_approach.strip():
        score += 2.0
    if unit.validation_plan.strip():
        score += 1.5
    text = _idea_text(unit)
    if any(term in text for term in ["replace ehr", "full ehr replacement", "replace github", "migrate ecosystem"]):
        score -= 3.0
    return max(0.0, min(score, 10.0))


def _measurable_infra_score(unit: BuildableUnit) -> float:
    text = _idea_text(unit)
    score = 4.0
    metric_terms = [
        "latency",
        "cost",
        "gpu",
        "utilization",
        "throughput",
        "tokens/sec",
        "reliability",
        "uptime",
        "quality",
        "benchmark",
        "eval",
        "regression",
    ]
    if any(term in text for term in metric_terms):
        score += 3.0
    if any(term in text for term in ["measure", "score", "profile", "compare", "optimize"]):
        score += 1.5
    if unit.validation_plan.strip():
        score += 1.0
    return min(score, 10.0)


def _deployment_fit_score(unit: BuildableUnit) -> float:
    text = _idea_text(unit)
    score = 4.0
    fit_terms = [
        "kubernetes",
        "k8s",
        "ci/cd",
        "deployment",
        "serving",
        "vllm",
        "triton",
        "onnx",
        "mlflow",
        "ray",
        "docker",
        "api",
        "cli",
    ]
    if any(term in text for term in fit_terms):
        score += 3.0
    if unit.tech_approach.strip():
        score += 1.5
    if any(term in text for term in ["full platform migration", "replace ml platform"]):
        score -= 4.0
    return max(0.0, min(score, 10.0))


def _differentiation_score(text: str, domain: DomainContext, memory: list[dict]) -> float:
    score = 7.0
    for pattern in domain.bad_idea_patterns:
        if pattern.lower() in text:
            score -= 2.5
    for row in memory:
        if row.get("outcome") == "rejected" and str(row.get("pattern", "")).lower()[:60] in text:
            score -= 1.5
    return max(0.0, min(score, 10.0))


def _distribution_score(unit: BuildableUnit) -> float:
    text = _idea_text(unit)
    score = 4.0
    if unit.first_10_customers.strip():
        score += 2.0
    if any(term in text for term in ["cli", "api", "github", "slack", "ehr", "fhir", "workflow", "clinic", "oss", "open-source"]):
        score += 2.0
    if unit.buyer.strip() and unit.specific_user.strip():
        score += 1.0
    return min(score, 10.0)


def _risk_control_score(unit: BuildableUnit, domain: DomainContext) -> float:
    score = 6.0
    if unit.domain_risks:
        score += 1.0
    text = _idea_text(unit)
    for constraint in domain.hard_constraints:
        if any(word in text for word in constraint.lower().split()[:3]):
            score += 0.5
    if "diagnosis" in text and "human" not in text and "physician" not in text:
        score -= 4.0
    return max(0.0, min(score, 10.0))


def _pattern_rejection_tags(
    text: str,
    domain: DomainContext,
    config: DomainQualityConfig,
) -> list[str]:
    tags = []
    generic_patterns = [
        ("generic_ai_assistant", ["generic ai assistant", "ai assistant for everyone", "chatbot for"]),
        ("dashboard_without_workflow", ["dashboard", "analytics portal"]),
        ("impossible_ehr_access", ["replace ehr", "full ehr replacement"]),
        ("autonomous_diagnosis", ["autonomous diagnosis", "diagnose patients", "ai doctor"]),
        ("marketplace_without_distribution", ["marketplace"]),
    ]
    for tag, needles in generic_patterns:
        if any(needle in text for needle in needles):
            tags.append(tag)
    for pattern in [*domain.bad_idea_patterns, *config.rejected_patterns]:
        if pattern.lower() in text:
            tags.append(_tagify(pattern))
    return tags


def _field_value(unit: BuildableUnit, field: str) -> str:
    value = getattr(unit, field, "")
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "x" if value else ""
    return str(value or "").strip()


def _missing_tag(field: str) -> str:
    if field == "buyer":
        return "missing_buyer"
    if field == "workflow_context":
        return "missing_workflow"
    return f"missing_{field}"


def _tagify(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")


def _idea_text(unit: BuildableUnit) -> str:
    return " ".join(
        [
            unit.title,
            unit.one_liner,
            unit.problem,
            unit.solution,
            unit.value_proposition,
            unit.workflow_context,
            unit.current_workaround,
            unit.validation_plan,
            unit.tech_approach,
        ]
    ).lower()


def _reasoning(overall: float, tags: list[str], dimensions: dict[str, float]) -> str:
    weakest = sorted(dimensions.items(), key=lambda item: item[1])[:2]
    parts = [f"Domain quality score {overall:.1f}/100."]
    if weakest:
        parts.append("Weakest dimensions: " + ", ".join(f"{k}={v:.1f}" for k, v in weakest))
    if tags:
        parts.append("Rejection tags: " + ", ".join(sorted(set(tags))))
    return " ".join(parts)
