"""Generate deterministic threat models for buildable ideas."""

from __future__ import annotations

import re
from typing import Any

from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


THREAT_MODEL_SCHEMA_VERSION = "max-threat-model/v1"

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_EXTERNAL_TERMS = {
    "Datadog": ("datadog",),
    "GitHub": ("github",),
    "Jira": ("jira", "atlassian"),
    "OpenAI": ("openai", "llm", "embedding", "model provider"),
    "Salesforce": ("salesforce",),
    "Slack": ("slack",),
    "Stripe": ("stripe",),
    "Teams": ("microsoft teams", "teams"),
    "Twilio": ("twilio",),
    "Webhook": ("webhook",),
}

_DATA_TERMS = (
    "account",
    "audit",
    "customer",
    "email",
    "export",
    "payment",
    "personal data",
    "pii",
    "record",
    "retention",
    "user data",
)

_AUTH_TERMS = ("auth", "jwt", "login", "oauth", "oidc", "permission", "rbac", "role", "saml", "sso")
_SECRET_TERMS = ("api key", "credential", "private key", "secret", "token", "webhook secret")


def generate_threat_model(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-ready threat model from an idea and optional spec preview."""
    spec = tact_spec if isinstance(tact_spec, dict) else generate_spec_preview(unit, evaluation)
    context = _context(unit, evaluation, spec)
    assets = _assets(context)
    boundaries = _trust_boundaries(context, assets)
    mitigations = _mitigations(context)
    scenarios = _threat_scenarios(context, assets, mitigations)
    residual_risks = _residual_risks(context, scenarios)
    review_gate = _review_gate(context, scenarios, residual_risks)
    scope = _scope(context, assets, boundaries)
    scope["high_severity_scenario_count"] = sum(
        1 for scenario in scenarios if scenario["severity"] == "high"
    )

    return {
        "schema_version": THREAT_MODEL_SCHEMA_VERSION,
        "kind": "max.threat_model",
        "idea_id": unit.id,
        "scope": scope,
        "assets": assets,
        "trust_boundaries": boundaries,
        "threat_scenarios": scenarios,
        "mitigations": mitigations,
        "residual_risks": residual_risks,
        "review_gate": review_gate,
    }


def render_threat_model_markdown(threat_model: dict[str, Any]) -> str:
    """Render a generated threat model as a stable markdown handoff document."""
    scope = threat_model.get("scope", {})
    title = _text(scope.get("title")) or _text(threat_model.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Threat Model",
        "",
        f"- Schema version: {_text(threat_model.get('schema_version'))}",
        f"- Idea ID: {_text(threat_model.get('idea_id'))}",
        f"- Workflow context: {_text(scope.get('workflow_context'))}",
        f"- Target user: {_text(scope.get('target_user'))}",
        f"- Stack: {_text(scope.get('stack'))}",
        f"- Evaluation available: {_text(scope.get('evaluation_available'))}",
        f"- High severity scenarios: {_text(scope.get('high_severity_scenario_count'))}",
        "",
    ]

    _extend_section(lines, "Scope", [scope], _render_scope)
    _extend_section(lines, "Assets", threat_model.get("assets") or [], _render_asset)
    _extend_section(
        lines, "Trust Boundaries", threat_model.get("trust_boundaries") or [], _render_boundary
    )
    _extend_section(
        lines, "Threat Scenarios", threat_model.get("threat_scenarios") or [], _render_scenario
    )
    _extend_section(lines, "Mitigations", threat_model.get("mitigations") or [], _render_mitigation)
    _extend_section(
        lines, "Residual Risks", threat_model.get("residual_risks") or [], _render_residual_risk
    )
    _extend_section(lines, "Review Gate", [threat_model.get("review_gate") or {}], _render_gate)

    return "\n".join(lines).rstrip() + "\n"


def _context(
    unit: BuildableUnit, evaluation: UtilityEvaluation | None, spec: dict[str, Any]
) -> dict[str, Any]:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    stack = solution.get("suggested_stack") or unit.suggested_stack
    text = _haystack(unit, spec)

    return {
        "unit": unit,
        "evaluation": evaluation,
        "spec": spec,
        "title": _compact(project.get("title")) or unit.title or unit.id,
        "summary": _compact(project.get("summary")) or unit.one_liner,
        "workflow": _compact(project.get("workflow_context")) or unit.workflow_context or "primary workflow",
        "target_user": _compact(project.get("specific_user") or project.get("target_users"))
        or unit.specific_user
        or unit.target_users
        or "primary user",
        "buyer": _compact(project.get("buyer")) or unit.buyer or "launch sponsor",
        "stack": stack,
        "stack_label": _stack_label(stack),
        "mvp_scope": [_compact(item) for item in _list(execution.get("mvp_scope")) if _compact(item)],
        "risks": [_compact(item) for item in [*unit.domain_risks, *_list(execution.get("risks"))] if _compact(item)],
        "insight_ids": [_compact(item) for item in _list(evidence.get("insight_ids") or unit.inspiring_insights) if _compact(item)],
        "signal_ids": [_compact(item) for item in _list(evidence.get("signal_ids") or unit.evidence_signals) if _compact(item)],
        "external_services": _external_services(text, stack),
        "data_terms": _detected_terms(text, _DATA_TERMS),
        "auth_terms": _detected_terms(text, _AUTH_TERMS),
        "secret_terms": _detected_terms(text, _SECRET_TERMS),
        "has_auth": _contains_any(text, _AUTH_TERMS),
        "has_authorization": _contains_any(text, ("permission", "rbac", "role", "scope", "tenant")),
        "has_data": _contains_any(text, _DATA_TERMS),
        "has_secrets": _contains_any(text, _SECRET_TERMS),
        "has_audit": _contains_any(text, ("audit", "log", "trace", "event")),
        "has_rate_limit": _contains_any(text, ("abuse", "dos", "rate limit", "replay", "spam", "throttle")),
        "evaluation_available": evaluation is not None,
        "recommendation": evaluation.recommendation if evaluation else None,
        "overall_score": evaluation.overall_score if evaluation else None,
    }


def _scope(
    context: dict[str, Any],
    assets: list[dict[str, Any]],
    boundaries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "title": context["title"],
        "summary": context["summary"] or "Threat model for the generated TactSpec companion artifact.",
        "workflow_context": context["workflow"],
        "target_user": context["target_user"],
        "buyer": context["buyer"],
        "stack": context["stack_label"],
        "in_scope": _dedupe(
            [
                context["workflow"],
                "authentication and authorization decisions",
                "data storage, logging, and integration flows",
                *context["mvp_scope"],
            ]
        ),
        "out_of_scope": [
            "formal penetration test execution",
            "vendor security questionnaire completion",
            "production incident response after launch",
        ],
        "asset_count": len(assets),
        "trust_boundary_count": len(boundaries),
        "high_severity_scenario_count": 0,
        "evaluation_available": context["evaluation_available"],
        "recommendation": context["recommendation"],
        "overall_score": context["overall_score"],
        "evidence": _evidence_refs(context),
    }


def _assets(context: dict[str, Any]) -> list[dict[str, Any]]:
    assets = [
        _asset(
            "AST1",
            "primary-workflow",
            context["title"],
            f"Core workflow for {context['workflow']}.",
            "medium",
            ["project.workflow_context", "execution.mvp_scope"],
        ),
        _asset(
            "AST2",
            "identity",
            "User and operator identity",
            "Accounts, sessions, roles, and ownership context for the target user.",
            "high" if context["has_auth"] else "medium",
            _evidence(context["auth_terms"], "project.specific_user", "solution.technical_approach"),
        ),
    ]
    if context["has_data"] or context["data_terms"]:
        assets.append(
            _asset(
                "AST3",
                "data",
                "Customer and workflow data",
                "Records, exports, audit context, or personal data handled by the workflow.",
                "high",
                _evidence(context["data_terms"], "problem.current_workaround", "execution.risks"),
            )
        )
    else:
        assets.append(
            _asset(
                "AST3",
                "data",
                "Workflow data",
                "Conservative data asset assumption because most implementations persist inputs, outputs, logs, or configuration.",
                "medium",
                ["project.summary", "execution.mvp_scope"],
            )
        )
    if context["has_secrets"] or context["external_services"]:
        assets.append(
            _asset(
                "AST4",
                "secret",
                "Credentials and integration secrets",
                "API tokens, OAuth material, webhook secrets, and environment configuration.",
                "high",
                _evidence(context["secret_terms"], "solution.suggested_stack", "solution.technical_approach"),
            )
        )
    for service in context["external_services"]:
        assets.append(
            _asset(
                f"AST{len(assets) + 1}",
                "external-service",
                service,
                f"Third-party service used by the workflow and outside direct application control.",
                "high",
                ["solution.suggested_stack", "solution.technical_approach"],
            )
        )
    if context["has_audit"]:
        assets.append(
            _asset(
                f"AST{len(assets) + 1}",
                "audit-log",
                "Audit and operational logs",
                "Security-relevant events used for traceability without leaking sensitive fields.",
                "medium",
                ["execution.validation_plan", "solution.technical_approach"],
            )
        )
    return _dedupe_assets(assets)


def _trust_boundaries(
    context: dict[str, Any], assets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    boundaries = [
        _boundary(
            "TBD1",
            "user-to-application",
            "Target user to application runtime",
            "public or operator-controlled client",
            "application runtime",
            ["AST1", "AST2"],
            ["authentication", "input validation", "transport encryption"],
            ["project.workflow_context", "project.target_users"],
        ),
        _boundary(
            "TBD2",
            "authorization-boundary",
            "Application authorization checks",
            "authenticated actor",
            "protected workflow action",
            ["AST1", "AST2", "AST3"],
            ["least privilege", "ownership checks", "deny-by-default policy"],
            ["project.specific_user", "execution.mvp_scope"],
        ),
        _boundary(
            "TBD3",
            "application-to-data",
            "Runtime to persisted data and logs",
            "application runtime",
            "data store, queue, cache, or log sink",
            ["AST3", *([asset["id"] for asset in assets if asset["type"] == "audit-log"])],
            ["encryption", "retention policy", "backup access controls"],
            ["solution.suggested_stack", "execution.risks"],
        ),
    ]
    external_asset_ids = [asset["id"] for asset in assets if asset["type"] == "external-service"]
    if external_asset_ids:
        boundaries.append(
            _boundary(
                "TBD4",
                "application-to-vendor",
                "Application runtime to external services",
                "application runtime",
                "third-party API, webhook, or SaaS boundary",
                ["AST4", *external_asset_ids],
                ["scoped credentials", "signature verification", "timeouts", "egress allowlist"],
                ["solution.suggested_stack", "solution.technical_approach"],
            )
        )
    else:
        boundaries.append(
            _boundary(
                "TBD4",
                "deployment-boundary",
                "Build and deployment environment to runtime",
                "source control or CI environment",
                "runtime configuration",
                ["AST1", "AST4"] if any(asset["id"] == "AST4" for asset in assets) else ["AST1"],
                ["protected branches", "secret scanning", "release approval"],
                ["solution.suggested_stack", "execution.validation_plan"],
            )
        )
    return boundaries


def _threat_scenarios(
    context: dict[str, Any],
    assets: list[dict[str, Any]],
    mitigations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mitigation_ids = _mitigation_ids(mitigations)
    scenarios = [
        _scenario(
            "THR1",
            "Spoofed or replayed access reaches protected workflow",
            "high" if not context["has_auth"] else "medium",
            "User and operator identity",
            "An attacker reuses a session, token, callback, or unauthenticated endpoint to trigger workflow actions.",
            mitigation_ids["authentication"],
            _evidence(context["auth_terms"], "project.specific_user", "solution.technical_approach"),
        ),
        _scenario(
            "THR2",
            "Privilege escalation exposes another user's workflow data",
            "high" if not context["has_authorization"] else "medium",
            "Customer and workflow data" if any(asset["type"] == "data" for asset in assets) else context["title"],
            "A valid user changes identifiers, tenant context, roles, or scopes to read or mutate out-of-scope records.",
            mitigation_ids["authorization"],
            ["project.specific_user", "execution.mvp_scope"],
        ),
        _scenario(
            "THR3",
            "Credential leakage enables service impersonation",
            "high",
            "Credentials and integration secrets",
            "A token, API key, webhook secret, or environment value is stored in logs, source control, client code, or broad runtime configuration.",
            mitigation_ids["secret_handling"],
            _evidence(context["secret_terms"], "solution.suggested_stack", "solution.technical_approach"),
        ),
        _scenario(
            "THR4",
            "Sensitive workflow data is over-retained or exported",
            "high" if context["has_data"] else "medium",
            "Customer and workflow data",
            "Stored records, exports, logs, or backups outlive the business need or are retrievable by unintended operators.",
            mitigation_ids["data_protection"],
            _evidence(context["data_terms"], "problem.current_workaround", "execution.risks"),
        ),
        _scenario(
            "THR5",
            "Dependency or integration boundary is abused",
            "high" if context["external_services"] else "medium",
            ", ".join(context["external_services"]) or "External service boundary",
            "A third-party API, webhook, or SDK receives excessive privileges, malformed callbacks, unbounded retries, or sensitive payloads.",
            mitigation_ids["dependency_boundary"],
            _evidence(context["external_services"], "solution.suggested_stack", "solution.technical_approach"),
        ),
        _scenario(
            "THR6",
            "Abuse traffic degrades the launch workflow",
            "medium",
            context["title"],
            "Malformed input, replayed callbacks, high request rates, or integration failure loops cause inaccurate results or unavailable workflows.",
            mitigation_ids["abuse_resistance"],
            ["execution.risks", "execution.validation_plan"],
        ),
    ]
    return sorted(scenarios, key=lambda item: (_SEVERITY_RANK[item["severity"]], item["id"]))


def _mitigations(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _mitigation(
            "MIT1",
            "authentication",
            "Define and test the authentication boundary",
            "Require a named identity provider or token verifier, reject unauthenticated workflow actions, and cover callback replay checks.",
            "security_owner",
            ["project.workflow_context", "solution.technical_approach"],
        ),
        _mitigation(
            "MIT2",
            "authorization",
            "Enforce least-privilege workflow authorization",
            "Check role, ownership, tenant, and scope on every read, write, export, integration callback, and administrative action.",
            "backend_owner",
            ["project.specific_user", "execution.mvp_scope"],
        ),
        _mitigation(
            "MIT3",
            "secret_handling",
            "Keep secrets out of code, logs, and client state",
            "Store secrets in managed configuration, rotate them on compromise, redact logs, and scope vendor tokens to the minimum capability.",
            "platform_owner",
            ["solution.suggested_stack"],
        ),
        _mitigation(
            "MIT4",
            "data_protection",
            "Limit retained workflow data",
            "Classify stored records, set retention and deletion behavior, encrypt persisted data, and prevent sensitive values in diagnostic logs.",
            "data_owner",
            ["problem.current_workaround", "execution.risks"],
        ),
        _mitigation(
            "MIT5",
            "dependency_boundary",
            "Constrain external dependency behavior",
            "Validate webhook signatures, use scoped credentials, set timeouts and retry limits, and document data shared with each vendor.",
            "integration_owner",
            ["solution.suggested_stack", "solution.technical_approach"],
        ),
        _mitigation(
            "MIT6",
            "abuse_resistance",
            "Add negative tests and abuse throttles",
            "Test malformed input, replay, privilege escalation, oversized payloads, and dependency failure loops before launch.",
            "qa_owner",
            ["execution.validation_plan", "execution.risks"],
        ),
    ]


def _residual_risks(
    context: dict[str, Any], scenarios: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    risks = [
        _residual(
            "RR1",
            "Incomplete threat evidence",
            "medium" if _evidence_refs(context) else "high",
            "Threat model relies on available idea and spec fields; missing production architecture can hide assets or boundaries.",
            ["scope.evidence", "trust_boundaries"],
        )
    ]
    if context["external_services"]:
        risks.append(
            _residual(
                "RR2",
                "Third-party control drift",
                "medium",
                "Vendor permission models, webhook behavior, and outage modes can change after implementation.",
                ["trust_boundaries.TBD4", "threat_scenarios.THR5"],
            )
        )
    if any(item["severity"] == "high" for item in scenarios):
        risks.append(
            _residual(
                f"RR{len(risks) + 1}",
                "High severity scenarios remain open",
                "high",
                "Threat scenarios marked high require owner acceptance or implementation evidence before launch approval.",
                [item["id"] for item in scenarios if item["severity"] == "high"],
            )
        )
    return risks


def _review_gate(
    context: dict[str, Any],
    scenarios: list[dict[str, Any]],
    residual_risks: list[dict[str, Any]],
) -> dict[str, Any]:
    high_scenarios = [item for item in scenarios if item["severity"] == "high"]
    missing = []
    if not context["evaluation_available"]:
        missing.append("utility evaluation is missing")
    if not context["has_auth"]:
        missing.append("authentication boundary is not explicit")
    if not context["has_authorization"]:
        missing.append("authorization rules are not explicit")
    if not context["has_rate_limit"]:
        missing.append("abuse and replay limits are not explicit")

    decision = "pass"
    if high_scenarios or missing:
        decision = "needs_security_review"
    if len(high_scenarios) >= 4 or len(missing) >= 3:
        decision = "hold"

    return {
        "decision": decision,
        "high_severity_scenario_ids": [item["id"] for item in high_scenarios],
        "residual_risk_ids": [item["id"] for item in residual_risks],
        "blocking_reasons": missing,
        "required_mitigations": _dedupe(
            mitigation_id
            for item in high_scenarios
            for mitigation_id in item.get("mitigation_ids", [])
        ),
        "review_owner": "security_owner",
    }


def _asset(
    asset_id: str,
    asset_type: str,
    name: str,
    description: str,
    sensitivity: str,
    source_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": asset_id,
        "type": asset_type,
        "name": _compact(name),
        "description": _compact(description),
        "sensitivity": sensitivity,
        "source_refs": _dedupe(source_refs),
    }


def _boundary(
    boundary_id: str,
    category: str,
    name: str,
    from_zone: str,
    to_zone: str,
    asset_ids: list[str],
    controls: list[str],
    source_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": boundary_id,
        "category": category,
        "name": name,
        "from": from_zone,
        "to": to_zone,
        "asset_ids": _dedupe(asset_ids),
        "required_controls": controls,
        "source_refs": _dedupe(source_refs),
    }


def _scenario(
    scenario_id: str,
    title: str,
    severity: str,
    affected_asset: str,
    attack_path: str,
    mitigation_ids: list[str],
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "title": title,
        "severity": severity,
        "affected_asset": _compact(affected_asset),
        "attack_path": _compact(attack_path),
        "mitigation": "Apply " + ", ".join(mitigation_ids) + " before launch.",
        "mitigation_ids": mitigation_ids,
        "evidence": _dedupe(evidence),
        "status": "open",
    }


def _mitigation(
    mitigation_id: str,
    category: str,
    title: str,
    action: str,
    owner: str,
    source_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": mitigation_id,
        "category": category,
        "title": title,
        "action": _compact(action),
        "owner": owner,
        "source_refs": source_refs,
        "status": "recommended",
    }


def _residual(
    risk_id: str, title: str, severity: str, description: str, source_refs: list[str]
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "title": title,
        "severity": severity,
        "description": _compact(description),
        "source_refs": _dedupe(source_refs),
        "status": "requires_acceptance",
    }


def _render_scope(scope: dict[str, Any]) -> list[str]:
    return [
        f"- Summary: {_text(scope.get('summary'))}",
        f"- In scope: {_inline_list(scope.get('in_scope') or [])}",
        f"- Out of scope: {_inline_list(scope.get('out_of_scope') or [])}",
        f"- Evidence: {_inline_list(scope.get('evidence') or [])}",
    ]


def _render_asset(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item.get('id')}: {_text(item.get('name'))}",
        "",
        f"- Type: {_text(item.get('type'))}",
        f"- Sensitivity: {_text(item.get('sensitivity'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Source refs: {_inline_list(item.get('source_refs') or [])}",
    ]


def _render_boundary(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item.get('id')}: {_text(item.get('name'))}",
        "",
        f"- Category: {_text(item.get('category'))}",
        f"- Flow: {_text(item.get('from'))} -> {_text(item.get('to'))}",
        f"- Assets: {_inline_list(item.get('asset_ids') or [])}",
        f"- Required controls: {_inline_list(item.get('required_controls') or [])}",
        f"- Source refs: {_inline_list(item.get('source_refs') or [])}",
    ]


def _render_scenario(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item.get('id')}: {_text(item.get('title'))}",
        "",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Affected asset: {_text(item.get('affected_asset'))}",
        f"- Attack path: {_text(item.get('attack_path'))}",
        f"- Mitigation: {_text(item.get('mitigation'))}",
        f"- Evidence: {_inline_list(item.get('evidence') or [])}",
    ]


def _render_mitigation(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item.get('id')}: {_text(item.get('title'))}",
        "",
        f"- Category: {_text(item.get('category'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Source refs: {_inline_list(item.get('source_refs') or [])}",
    ]


def _render_residual_risk(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item.get('id')}: {_text(item.get('title'))}",
        "",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Source refs: {_inline_list(item.get('source_refs') or [])}",
    ]


def _render_gate(item: dict[str, Any]) -> list[str]:
    return [
        f"- Decision: {_text(item.get('decision'))}",
        f"- Review owner: {_text(item.get('review_owner'))}",
        f"- High severity scenarios: {_inline_list(item.get('high_severity_scenario_ids') or [])}",
        f"- Required mitigations: {_inline_list(item.get('required_mitigations') or [])}",
        f"- Blocking reasons: {_inline_list(item.get('blocking_reasons') or [])}",
    ]


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    renderer,
) -> None:
    lines.extend([f"## {title}", ""])
    if items:
        for item in items:
            lines.extend(renderer(item))
            lines.append("")
    else:
        lines.extend(["None.", ""])


def _mitigation_ids(mitigations: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for mitigation in mitigations:
        result.setdefault(mitigation["category"], []).append(mitigation["id"])
    return result


def _external_services(text: str, stack: Any) -> list[str]:
    labels = [label for label, terms in sorted(_EXTERNAL_TERMS.items()) if any(term in text for term in terms)]
    if isinstance(stack, dict):
        for key, value in sorted(stack.items()):
            key_text = _compact(key).lower()
            value_text = _compact(value)
            if key_text in {"ai", "analytics", "auth", "billing", "crm", "email", "messaging", "observability", "payments"}:
                labels.append(_service_label(value_text))
    return _dedupe(label for label in labels if label)


def _service_label(value: str) -> str:
    text = _compact(value)
    if not text:
        return ""
    return {
        "oauth": "OAuth",
        "postgres": "Postgres",
        "redis": "Redis",
    }.get(text.lower(), text)


def _dedupe_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for asset in assets:
        key = (asset["type"], asset["name"].lower())
        if key in seen:
            continue
        seen.add(key)
        asset = dict(asset)
        asset["id"] = f"AST{len(result) + 1}"
        result.append(asset)
    return result


def _evidence_refs(context: dict[str, Any]) -> list[str]:
    refs = []
    refs.extend(f"insight:{item}" for item in context["insight_ids"])
    refs.extend(f"signal:{item}" for item in context["signal_ids"])
    return _dedupe(refs)


def _evidence(detected: list[str], *fallbacks: str) -> list[str]:
    return detected or [fallback for fallback in fallbacks if fallback]


def _detected_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [_term_label(term) for term in terms if term in text]


def _term_label(term: str) -> str:
    return {
        "api key": "API key",
        "jwt": "JWT",
        "oauth": "OAuth",
        "oidc": "OIDC",
        "pii": "PII",
        "rbac": "RBAC",
        "saml": "SAML",
        "sso": "SSO",
        "dos": "DoS",
    }.get(term, term)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _haystack(unit: BuildableUnit, spec: dict[str, Any]) -> str:
    parts: list[str] = [
        unit.title,
        unit.one_liner,
        unit.problem,
        unit.solution,
        unit.target_users,
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
        *unit.domain_risks,
    ]
    if unit.suggested_stack:
        parts.extend(str(value) for _, value in sorted(unit.suggested_stack.items()))
    parts.append(_flatten(spec))
    return " ".join(_compact(part).lower() for part in parts if _compact(part))


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten(value[key]) for key in sorted(value))
    if isinstance(value, list):
        return " ".join(_flatten(item) for item in value)
    return _compact(value)


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict):
        if stack:
            return ", ".join(f"{key}={_compact(value)}" for key, value in sorted(stack.items()))
        return "unspecified"
    if _compact(stack):
        return _compact(stack)
    return "unspecified"


def _inline_list(items: list[Any]) -> str:
    values = [_text(item) for item in items if _text(item)]
    return ", ".join(values) if values else "none"


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _dedupe(items) -> list[str]:
    result: list[str] = []
    for item in items:
        value = _compact(item)
        if value and value not in result:
            result.append(value)
    return result


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value)).strip()
