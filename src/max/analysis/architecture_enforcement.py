"""Architecture enforcement checks for generated ideas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from max.evaluation.weights import get_weights
from max.profiles.schema import ArchitectureConstraintsConfig, PipelineProfile
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit

DEFAULT_UNIT_LIMIT = 100

DEPLOYMENT_TERMS = (
    "serverless",
    "kubernetes",
    "k8s",
    "docker",
    "container",
    "on-prem",
    "on prem",
    "self-hosted",
    "saas",
    "cloud",
    "local",
    "edge",
    "browser extension",
    "desktop",
    "mobile",
)

INTEGRATION_TERMS = (
    "github",
    "gitlab",
    "slack",
    "jira",
    "linear",
    "notion",
    "figma",
    "vscode",
    "jetbrains",
    "mcp",
    "openai",
    "anthropic",
    "aws",
    "azure",
    "gcp",
    "kubernetes",
    "docker",
)


@dataclass(frozen=True)
class ArchitectureFinding:
    """One enforceable architecture issue or warning for an idea."""

    idea_id: str
    title: str
    severity: str
    code: str
    message: str
    field: str
    expected: list[str] = field(default_factory=list)
    observed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "title": self.title,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "expected": self.expected,
            "observed": self.observed,
        }


@dataclass(frozen=True)
class IdeaArchitectureAssessment:
    """Architecture enforcement assessment for one idea."""

    idea_id: str
    title: str
    category: str
    target_users: str
    domain: str
    suggested_stack: dict[str, Any]
    stack_decisions: dict[str, list[str]]
    deployment_assumptions: list[str]
    integration_assumptions: list[str]
    findings: list[ArchitectureFinding] = field(default_factory=list)
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "title": self.title,
            "category": self.category,
            "target_users": self.target_users,
            "domain": self.domain,
            "suggested_stack": self.suggested_stack,
            "stack_decisions": self.stack_decisions,
            "deployment_assumptions": self.deployment_assumptions,
            "integration_assumptions": self.integration_assumptions,
            "findings": [finding.to_dict() for finding in self.findings],
            "status": self.status,
        }


@dataclass(frozen=True)
class ArchitectureEnforcementReport:
    """Report comparing generated ideas with profile architecture expectations."""

    generated_at: str
    profile_name: str
    domain: str
    unit_limit: int
    units_analyzed: int
    categories_allowed: list[str]
    target_users_allowed: list[str]
    evaluation_weights: dict[str, float]
    constraints_configured: bool
    assessments: list[IdeaArchitectureAssessment]
    findings: list[ArchitectureFinding]
    recommended_constraint_additions: list[str] = field(default_factory=list)
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "profile_name": self.profile_name,
            "domain": self.domain,
            "unit_limit": self.unit_limit,
            "units_analyzed": self.units_analyzed,
            "categories_allowed": self.categories_allowed,
            "target_users_allowed": self.target_users_allowed,
            "evaluation_weights": self.evaluation_weights,
            "constraints_configured": self.constraints_configured,
            "assessments": [assessment.to_dict() for assessment in self.assessments],
            "findings": [finding.to_dict() for finding in self.findings],
            "recommended_constraint_additions": self.recommended_constraint_additions,
            "status": self.status,
        }


def build_architecture_enforcement_report(
    profile: PipelineProfile,
    store: Store,
    *,
    unit_limit: int = DEFAULT_UNIT_LIMIT,
) -> ArchitectureEnforcementReport:
    """Build an architecture enforcement report for recent profile ideas."""

    if unit_limit < 1:
        raise ValueError("unit_limit must be at least 1")

    units = _recent_profile_units(profile, store, limit=unit_limit)
    constraints = profile.architecture_constraints
    assessments = [_assess_unit(unit, profile, constraints) for unit in units]
    findings = [finding for assessment in assessments for finding in assessment.findings]
    status = _report_status(findings)

    return ArchitectureEnforcementReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        profile_name=profile.name,
        domain=profile.domain.name,
        unit_limit=unit_limit,
        units_analyzed=len(units),
        categories_allowed=_allowed_categories(profile),
        target_users_allowed=_allowed_target_users(profile),
        evaluation_weights=_profile_weights(profile),
        constraints_configured=_has_constraints(constraints),
        assessments=assessments,
        findings=findings,
        recommended_constraint_additions=_recommended_constraint_additions(profile, assessments),
        status=status,
    )


def _recent_profile_units(profile: PipelineProfile, store: Store, *, limit: int) -> list[BuildableUnit]:
    units = store.get_buildable_units(limit=limit, domain=profile.domain.name)
    if units:
        return units

    candidates = store.get_buildable_units(limit=limit)
    scoped = [
        unit
        for unit in candidates
        if unit.domain in {profile.name, profile.domain.name}
    ]
    return scoped or [unit for unit in candidates if not unit.domain]


def _assess_unit(
    unit: BuildableUnit,
    profile: PipelineProfile,
    constraints: ArchitectureConstraintsConfig,
) -> IdeaArchitectureAssessment:
    findings: list[ArchitectureFinding] = []
    stack_decisions = _stack_decisions(unit.suggested_stack)
    deployment_assumptions = _deployment_assumptions(unit)
    integration_assumptions = _integration_assumptions(unit)

    _check_membership(
        findings,
        unit=unit,
        field_name="category",
        observed=unit.category,
        allowed=_allowed_categories(profile),
        code="unsupported_category",
        message="Idea category is outside the profile architecture category set.",
    )
    _check_membership(
        findings,
        unit=unit,
        field_name="target_users",
        observed=unit.target_users,
        allowed=_allowed_target_users(profile),
        code="unsupported_target_users",
        message="Idea target users are outside the profile target user set.",
    )
    _check_membership(
        findings,
        unit=unit,
        field_name="domain",
        observed=unit.domain,
        allowed=_allowed_domains(profile),
        code="unsupported_domain",
        message="Idea domain does not match the selected profile.",
        warn_if_missing=False,
    )

    if not unit.suggested_stack and not unit.tech_approach.strip():
        findings.append(_finding(unit, "warning", "missing_stack", "suggested_stack", "Idea has no stack or tech approach decision."))

    for required in constraints.required_stack_decisions:
        if _norm(required) not in {_norm(key) for key in stack_decisions}:
            findings.append(
                _finding(
                    unit,
                    "warning",
                    "missing_stack_decision",
                    "suggested_stack",
                    f"Missing required stack decision: {required}.",
                    expected=[required],
                    observed=sorted(stack_decisions),
                )
            )

    for key, allowed_values in constraints.allowed_stack_items.items():
        observed = stack_decisions.get(key, [])
        if observed:
            unsupported = _not_in_allowed(observed, allowed_values)
            if unsupported:
                findings.append(
                    _finding(
                        unit,
                        "error",
                        "unsupported_stack_item",
                        f"suggested_stack.{key}",
                        f"Stack decision {key} uses unsupported item(s).",
                        expected=allowed_values,
                        observed=unsupported,
                    )
                )

    for key, rejected_values in constraints.rejected_stack_items.items():
        observed = stack_decisions.get(key, [])
        rejected = _matching_terms(observed, rejected_values)
        if rejected:
            findings.append(
                _finding(
                    unit,
                    "error",
                    "rejected_stack_item",
                    f"suggested_stack.{key}",
                    f"Stack decision {key} uses rejected item(s).",
                    expected=rejected_values,
                    observed=rejected,
                )
            )

    _check_assumption_list(
        findings,
        unit=unit,
        field_name="deployment_assumptions",
        observed=deployment_assumptions,
        allowed=constraints.allowed_deployment_patterns,
        rejected=constraints.rejected_deployment_patterns,
        unsupported_code="unsupported_deployment_assumption",
        rejected_code="rejected_deployment_assumption",
    )
    _check_assumption_list(
        findings,
        unit=unit,
        field_name="integration_assumptions",
        observed=integration_assumptions,
        allowed=constraints.allowed_integrations,
        rejected=constraints.rejected_integrations,
        unsupported_code="unsupported_integration_assumption",
        rejected_code="rejected_integration_assumption",
    )

    for required in constraints.required_integrations:
        if not _contains_term(integration_assumptions, required):
            findings.append(
                _finding(
                    unit,
                    "warning",
                    "missing_required_integration",
                    "integration_assumptions",
                    f"Missing required integration assumption: {required}.",
                    expected=[required],
                    observed=integration_assumptions,
                )
            )

    text = _idea_text(unit)
    for term in constraints.required_tech_approach_terms:
        if _norm(term) not in text:
            findings.append(
                _finding(
                    unit,
                    "warning",
                    "missing_required_tech_term",
                    "tech_approach",
                    f"Tech approach does not mention required term: {term}.",
                    expected=[term],
                    observed=[unit.tech_approach] if unit.tech_approach else [],
                )
            )
    rejected_terms = [term for term in constraints.rejected_tech_approach_terms if _norm(term) in text]
    if rejected_terms:
        findings.append(
            _finding(
                unit,
                "error",
                "rejected_tech_term",
                "tech_approach",
                "Tech approach mentions rejected architecture term(s).",
                expected=constraints.rejected_tech_approach_terms,
                observed=rejected_terms,
            )
        )

    return IdeaArchitectureAssessment(
        idea_id=unit.id,
        title=unit.title,
        category=str(unit.category),
        target_users=unit.target_users,
        domain=unit.domain,
        suggested_stack=unit.suggested_stack,
        stack_decisions=stack_decisions,
        deployment_assumptions=deployment_assumptions,
        integration_assumptions=integration_assumptions,
        findings=findings,
        status=_assessment_status(findings),
    )


def _allowed_categories(profile: PipelineProfile) -> list[str]:
    return profile.architecture_constraints.allowed_categories or profile.domain.categories


def _allowed_target_users(profile: PipelineProfile) -> list[str]:
    return profile.architecture_constraints.allowed_target_users or profile.domain.target_user_types


def _allowed_domains(profile: PipelineProfile) -> list[str]:
    return profile.architecture_constraints.allowed_domains or [profile.name, profile.domain.name]


def _profile_weights(profile: PipelineProfile) -> dict[str, float]:
    if profile.evaluation.custom_weights:
        return dict(profile.evaluation.custom_weights)
    return get_weights(profile.evaluation.weight_profile)


def _has_constraints(constraints: ArchitectureConstraintsConfig) -> bool:
    return any(
        bool(value)
        for key, value in constraints.model_dump().items()
        if key != "notes"
    )


def _stack_decisions(stack: dict[str, Any]) -> dict[str, list[str]]:
    decisions: dict[str, list[str]] = {}
    for key, value in stack.items():
        if value is None:
            continue
        values = _flatten_value(value)
        if values:
            decisions[str(key)] = values
    return decisions


def _flatten_value(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        values: list[str] = []
        for nested_key, nested_value in value.items():
            nested_values = _flatten_value(nested_value)
            if nested_values:
                values.extend(f"{nested_key}:{nested}" for nested in nested_values)
            elif nested_key:
                values.append(str(nested_key))
        return values
    if isinstance(value, (list, tuple, set)):
        values = []
        for item in value:
            values.extend(_flatten_value(item))
        return values
    return [str(value)]


def _deployment_assumptions(unit: BuildableUnit) -> list[str]:
    return _extract_terms(unit, DEPLOYMENT_TERMS, stack_keys=("deployment", "hosting", "runtime", "infrastructure"))


def _integration_assumptions(unit: BuildableUnit) -> list[str]:
    extracted = _extract_terms(unit, INTEGRATION_TERMS, stack_keys=("integration", "integrations", "api", "apis"))
    for key, value in unit.suggested_stack.items():
        if "integration" in _norm(key):
            extracted.extend(_flatten_value(value))
    return sorted(dict.fromkeys(term for term in extracted if term))


def _extract_terms(unit: BuildableUnit, terms: tuple[str, ...], *, stack_keys: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    text = _idea_text(unit)
    for term in terms:
        if _norm(term) in text:
            found.append(term)
    for key, value in unit.suggested_stack.items():
        if any(stack_key in _norm(key) for stack_key in stack_keys):
            found.extend(_flatten_value(value))
    return sorted(dict.fromkeys(found))


def _idea_text(unit: BuildableUnit) -> str:
    parts = [
        unit.title,
        unit.one_liner,
        unit.solution,
        unit.tech_approach,
        unit.composability_notes,
        " ".join(str(value) for values in _stack_decisions(unit.suggested_stack).values() for value in values),
    ]
    return _norm(" ".join(parts))


def _check_membership(
    findings: list[ArchitectureFinding],
    *,
    unit: BuildableUnit,
    field_name: str,
    observed: str,
    allowed: list[str],
    code: str,
    message: str,
    warn_if_missing: bool = True,
) -> None:
    if not observed:
        if warn_if_missing:
            findings.append(_finding(unit, "warning", f"missing_{field_name}", field_name, f"Idea is missing {field_name}.", expected=allowed))
        return
    if allowed and not _contains_term(allowed, observed):
        findings.append(_finding(unit, "error", code, field_name, message, expected=allowed, observed=[observed]))


def _check_assumption_list(
    findings: list[ArchitectureFinding],
    *,
    unit: BuildableUnit,
    field_name: str,
    observed: list[str],
    allowed: list[str],
    rejected: list[str],
    unsupported_code: str,
    rejected_code: str,
) -> None:
    if allowed:
        unsupported = _not_in_allowed(observed, allowed)
        if unsupported:
            findings.append(
                _finding(
                    unit,
                    "error",
                    unsupported_code,
                    field_name,
                    f"{field_name.replace('_', ' ').title()} include unsupported item(s).",
                    expected=allowed,
                    observed=unsupported,
                )
            )
    rejected_matches = _matching_terms(observed, rejected)
    if rejected_matches:
        findings.append(
            _finding(
                unit,
                "error",
                rejected_code,
                field_name,
                f"{field_name.replace('_', ' ').title()} include rejected item(s).",
                expected=rejected,
                observed=rejected_matches,
            )
        )


def _finding(
    unit: BuildableUnit,
    severity: str,
    code: str,
    field_name: str,
    message: str,
    *,
    expected: list[str] | None = None,
    observed: list[str] | None = None,
) -> ArchitectureFinding:
    return ArchitectureFinding(
        idea_id=unit.id,
        title=unit.title,
        severity=severity,
        code=code,
        message=message,
        field=field_name,
        expected=expected or [],
        observed=observed or [],
    )


def _not_in_allowed(observed: list[str], allowed: list[str]) -> list[str]:
    return [value for value in observed if not _contains_term(allowed, value)]


def _matching_terms(observed: list[str], rejected: list[str]) -> list[str]:
    return [value for value in observed if _contains_term(rejected, value)]


def _contains_term(haystack: list[str], needle: str) -> bool:
    normalized_needle = _norm(needle)
    return any(
        _norm(value) == normalized_needle
        or normalized_needle in _norm(value)
        or _norm(value) in normalized_needle
        for value in haystack
    )


def _recommended_constraint_additions(
    profile: PipelineProfile,
    assessments: list[IdeaArchitectureAssessment],
) -> list[str]:
    constraints = profile.architecture_constraints
    recommendations: list[str] = []
    if not constraints.required_stack_decisions:
        observed_keys = sorted({key for assessment in assessments for key in assessment.stack_decisions})
        if observed_keys:
            recommendations.append(
                "Consider architecture_constraints.required_stack_decisions for observed stack keys: "
                + ", ".join(observed_keys[:8])
            )
    if not constraints.allowed_deployment_patterns:
        observed = sorted({item for assessment in assessments for item in assessment.deployment_assumptions})
        if observed:
            recommendations.append(
                "Consider architecture_constraints.allowed_deployment_patterns for observed deployment assumptions: "
                + ", ".join(observed[:8])
            )
    if not constraints.allowed_integrations:
        observed = sorted({item for assessment in assessments for item in assessment.integration_assumptions})
        if observed:
            recommendations.append(
                "Consider architecture_constraints.allowed_integrations for observed integrations: "
                + ", ".join(observed[:8])
            )
    if not constraints.allowed_categories and profile.domain.categories:
        recommendations.append(
            "Use architecture_constraints.allowed_categories if only some domain categories are architecturally acceptable."
        )
    return recommendations


def _assessment_status(findings: list[ArchitectureFinding]) -> str:
    if any(finding.severity == "error" for finding in findings):
        return "violation"
    if findings:
        return "warning"
    return "ok"


def _report_status(findings: list[ArchitectureFinding]) -> str:
    if any(finding.severity == "error" for finding in findings):
        return "violation"
    if findings:
        return "warning"
    return "ok"


def _norm(value: Any) -> str:
    return str(value).strip().lower().replace("_", "-")
