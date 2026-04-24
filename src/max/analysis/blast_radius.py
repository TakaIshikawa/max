"""Deterministic implementation blast-radius estimation for buildable ideas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


BLAST_RADIUS_SCHEMA_VERSION = "max-blast-radius/v1"

INTEGRATION_KEYWORDS = {
    "api",
    "webhook",
    "integration",
    "integrates",
    "connector",
    "sync",
    "import",
    "export",
    "oauth",
    "sso",
    "slack",
    "github",
    "jira",
    "salesforce",
    "stripe",
    "zapier",
    "mcp",
}
DATA_SECURITY_KEYWORDS = {
    "auth",
    "authentication",
    "authorization",
    "oauth",
    "sso",
    "permission",
    "privacy",
    "pii",
    "compliance",
    "security",
    "audit",
    "billing",
    "payment",
    "health",
    "medical",
    "legal",
    "financial",
}
OPS_KEYWORDS = {
    "ci",
    "cd",
    "deploy",
    "deployment",
    "cloud",
    "hosting",
    "queue",
    "scheduler",
    "cron",
    "monitoring",
    "observability",
    "database",
    "cache",
    "migration",
}
HIGH_EFFORT_KEYWORDS = {
    "platform",
    "multi-tenant",
    "realtime",
    "real-time",
    "distributed",
    "workflow",
    "automation",
    "orchestration",
    "agent",
    "agents",
    "enterprise",
    "marketplace",
}


@dataclass(frozen=True)
class BlastRadiusSurface:
    name: str
    score: float
    level: str
    drivers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BlastRadiusEstimate:
    schema_version: str
    kind: str
    idea_id: str
    title: str
    score: float
    level: str
    affected_surfaces: list[BlastRadiusSurface]
    drivers: list[str]
    mitigations: list[str]
    confidence: float
    evaluation_available: bool


def estimate_idea_blast_radius(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
) -> BlastRadiusEstimate:
    """Estimate implementation blast radius before publishing an idea.

    The estimator is intentionally transparent and deterministic. It favors
    signals already present on a BuildableUnit plus optional utility evaluation
    effort/confidence when available.
    """
    text = _idea_text(unit)
    stack_terms = _stack_terms(unit.suggested_stack)
    domain_risk_count = len([risk for risk in unit.domain_risks if risk.strip()])
    evidence_count = _evidence_count(unit)

    surfaces = [
        _surface("integrations", _integration_score(unit, text, stack_terms)),
        _surface("product_workflow", _workflow_score(unit, text)),
        _surface("runtime_stack", _stack_score(unit, text, stack_terms)),
        _surface("data_security", _data_security_score(unit, text, domain_risk_count)),
        _surface("operations", _operations_score(unit, text)),
        _surface("evidence_traceability", _evidence_score(evidence_count)),
        _surface("domain_risk", _domain_risk_score(unit, domain_risk_count)),
    ]
    affected_surfaces = sorted(
        [surface for surface in surfaces if surface.score >= 4.0],
        key=lambda surface: (-surface.score, surface.name),
    )

    effort_points, effort_driver = _evaluation_effort_points(evaluation)
    raw_score = 8.0 + effort_points + sum(surface.score for surface in affected_surfaces)
    score = round(min(100.0, raw_score), 1)
    level = _level(score)

    drivers = _drivers(unit, affected_surfaces, effort_driver, evidence_count, domain_risk_count)
    mitigations = _mitigations(affected_surfaces, evaluation)

    return BlastRadiusEstimate(
        schema_version=BLAST_RADIUS_SCHEMA_VERSION,
        kind="max.blast_radius",
        idea_id=unit.id,
        title=unit.title,
        score=score,
        level=level,
        affected_surfaces=affected_surfaces,
        drivers=drivers,
        mitigations=mitigations,
        confidence=_confidence(unit, evaluation, evidence_count),
        evaluation_available=evaluation is not None,
    )


def _surface(name: str, result: tuple[float, list[str]]) -> BlastRadiusSurface:
    score, drivers = result
    return BlastRadiusSurface(
        name=name,
        score=round(min(20.0, max(0.0, score)), 1),
        level=_surface_level(score),
        drivers=drivers,
    )


def _idea_text(unit: BuildableUnit) -> str:
    parts = [
        unit.title,
        unit.one_liner,
        unit.category,
        unit.problem,
        unit.solution,
        unit.target_users,
        unit.value_proposition,
        unit.specific_user,
        unit.buyer,
        unit.workflow_context,
        unit.current_workaround,
        unit.why_now,
        unit.validation_plan,
        unit.first_10_customers,
        unit.evidence_rationale,
        unit.tech_approach,
        unit.composability_notes,
        unit.domain,
        " ".join(unit.domain_risks),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _stack_terms(stack: dict[str, Any]) -> set[str]:
    terms: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                terms.add(str(key).lower())
                collect(nested)
        elif isinstance(value, list | tuple | set):
            for nested in value:
                collect(nested)
        elif value is not None:
            for token in str(value).replace("/", " ").replace(",", " ").split():
                terms.add(token.lower())

    collect(stack)
    return terms


def _keyword_hits(text: str, keywords: set[str]) -> list[str]:
    return sorted(keyword for keyword in keywords if keyword in text)


def _integration_score(
    unit: BuildableUnit,
    text: str,
    stack_terms: set[str],
) -> tuple[float, list[str]]:
    drivers: list[str] = []
    hits = sorted(
        set(_keyword_hits(text, INTEGRATION_KEYWORDS)) | (stack_terms & INTEGRATION_KEYWORDS)
    )
    score = min(12.0, len(hits) * 3.0)
    if hits:
        drivers.append(f"integration terms: {', '.join(hits[:5])}")
    if str(unit.category) in {"integration", "mcp_server", "automation"}:
        score += 6.0
        drivers.append(f"category is {unit.category}")
    if len(hits) >= 4:
        score += 4.0
        drivers.append("multiple external touchpoints")
    return score, drivers


def _workflow_score(unit: BuildableUnit, text: str) -> tuple[float, list[str]]:
    drivers: list[str] = []
    score = 0.0
    if str(unit.category) in {"application", "feature", "automation"}:
        score += 5.0
        drivers.append(f"category is {unit.category}")
    if unit.target_users == "both":
        score += 4.0
        drivers.append("targets both humans and agents")
    if unit.workflow_context.strip():
        score += 3.0
        drivers.append("workflow context is specified")
    hits = _keyword_hits(text, HIGH_EFFORT_KEYWORDS)
    if hits:
        score += min(8.0, len(hits) * 2.0)
        drivers.append(f"scope terms: {', '.join(hits[:5])}")
    return score, drivers


def _stack_score(
    unit: BuildableUnit,
    text: str,
    stack_terms: set[str],
) -> tuple[float, list[str]]:
    drivers: list[str] = []
    score = 0.0
    if unit.suggested_stack:
        score += min(8.0, len(stack_terms) * 1.5)
        drivers.append(f"suggested stack has {len(stack_terms)} term(s)")
    if "frontend" in text or "ui" in text or "dashboard" in text:
        score += 3.0
        drivers.append("user interface surface")
    if "backend" in text or "api" in text or "server" in text:
        score += 3.0
        drivers.append("backend/API surface")
    if str(unit.category) in {"library", "cli_tool"}:
        score += 2.0
        drivers.append(f"distribution surface is {unit.category}")
    return score, drivers


def _data_security_score(
    unit: BuildableUnit,
    text: str,
    domain_risk_count: int,
) -> tuple[float, list[str]]:
    drivers: list[str] = []
    hits = _keyword_hits(text, DATA_SECURITY_KEYWORDS)
    score = min(12.0, len(hits) * 3.0)
    if hits:
        drivers.append(f"sensitive terms: {', '.join(hits[:5])}")
    if domain_risk_count:
        score += min(6.0, domain_risk_count * 2.0)
        drivers.append(f"{domain_risk_count} domain risk(s)")
    if unit.domain in {"healthcare", "fintech", "legaltech", "cybersecurity"}:
        score += 4.0
        drivers.append(f"regulated or security-sensitive domain: {unit.domain}")
    return score, drivers


def _operations_score(unit: BuildableUnit, text: str) -> tuple[float, list[str]]:
    drivers: list[str] = []
    hits = _keyword_hits(text, OPS_KEYWORDS)
    score = min(12.0, len(hits) * 2.5)
    if hits:
        drivers.append(f"operational terms: {', '.join(hits[:5])}")
    if str(unit.category) in {"application", "mcp_server", "automation"}:
        score += 3.0
        drivers.append(f"deployable category is {unit.category}")
    return score, drivers


def _evidence_score(evidence_count: int) -> tuple[float, list[str]]:
    if evidence_count <= 1:
        return 6.0, ["limited direct evidence"]
    if evidence_count >= 6:
        return 4.0, [f"{evidence_count} evidence links to preserve"]
    return float(evidence_count), [f"{evidence_count} evidence links"]


def _domain_risk_score(unit: BuildableUnit, domain_risk_count: int) -> tuple[float, list[str]]:
    if domain_risk_count == 0:
        return 0.0, []
    score = min(16.0, 4.0 + domain_risk_count * 4.0)
    return score, [f"{domain_risk_count} explicit domain risk(s)"]


def _evaluation_effort_points(evaluation: UtilityEvaluation | None) -> tuple[float, str | None]:
    if evaluation is None:
        return 5.0, "utility evaluation is missing"
    effort = evaluation.build_effort.value
    if effort <= 3.0:
        return 18.0, "evaluation indicates very high build effort"
    if effort <= 5.0:
        return 12.0, "evaluation indicates high build effort"
    if effort <= 7.0:
        return 6.0, "evaluation indicates moderate build effort"
    return 1.0, "evaluation indicates low build effort"


def _evidence_count(unit: BuildableUnit) -> int:
    return len(set(unit.evidence_signals) | set(unit.inspiring_insights))


def _drivers(
    unit: BuildableUnit,
    affected_surfaces: list[BlastRadiusSurface],
    effort_driver: str | None,
    evidence_count: int,
    domain_risk_count: int,
) -> list[str]:
    drivers: list[str] = []
    if effort_driver:
        drivers.append(effort_driver)
    if affected_surfaces:
        top = affected_surfaces[0]
        drivers.append(f"largest affected surface: {top.name} ({top.level})")
    if len(affected_surfaces) >= 4:
        drivers.append(f"{len(affected_surfaces)} implementation surfaces likely affected")
    if domain_risk_count:
        drivers.append(f"{domain_risk_count} explicit domain risk(s)")
    if evidence_count <= 1:
        drivers.append("limited evidence makes implementation boundaries less certain")
    if str(unit.category) in {"integration", "mcp_server", "automation"}:
        drivers.append(f"{unit.category} ideas usually cross system boundaries")
    return list(dict.fromkeys(drivers))


def _mitigations(
    affected_surfaces: list[BlastRadiusSurface],
    evaluation: UtilityEvaluation | None,
) -> list[str]:
    mitigations = [
        "Define MVP non-goals and publish-blocking acceptance criteria before implementation.",
        "Sequence delivery so the riskiest affected surface is validated first.",
    ]
    names = {surface.name for surface in affected_surfaces}
    if "integrations" in names:
        mitigations.append(
            "Stub external integrations and require contract tests before live credentials."
        )
    if "data_security" in names:
        mitigations.append("Add a security and data-handling review to the launch checklist.")
    if "operations" in names:
        mitigations.append(
            "Include rollback, observability, and migration checks in the first milestone."
        )
    if evaluation is None:
        mitigations.append(
            "Run utility evaluation before treating the estimate as publication-ready."
        )
    return mitigations


def _confidence(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    evidence_count: int,
) -> float:
    confidence = 0.45
    confidence += min(0.20, evidence_count * 0.04)
    if unit.tech_approach.strip():
        confidence += 0.08
    if unit.suggested_stack:
        confidence += 0.08
    if unit.domain_risks:
        confidence += 0.04
    if evaluation is not None:
        dimension_confidences = [
            evaluation.pain_severity.confidence,
            evaluation.addressable_scale.confidence,
            evaluation.build_effort.confidence,
            evaluation.composability.confidence,
            evaluation.competitive_density.confidence,
            evaluation.timing_fit.confidence,
            evaluation.compounding_value.confidence,
        ]
        confidence += min(0.15, sum(dimension_confidences) / len(dimension_confidences) * 0.15)
    return round(min(0.95, confidence), 2)


def _level(score: float) -> str:
    if score >= 75.0:
        return "critical"
    if score >= 55.0:
        return "high"
    if score >= 35.0:
        return "medium"
    return "low"


def _surface_level(score: float) -> str:
    if score >= 15.0:
        return "high"
    if score >= 8.0:
        return "medium"
    return "low"
