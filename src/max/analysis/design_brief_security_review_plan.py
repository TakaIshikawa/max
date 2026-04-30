"""Deterministic security review plans for persisted design briefs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.security_review_plan.v1"

_SENSITIVE_DATA_KEYWORDS = {
    "customer": "customer data",
    "data": "product or workflow data",
    "email": "email address",
    "events": "event data",
    "feedback": "user feedback",
    "metrics": "metrics",
    "oauth": "OAuth tokens",
    "pii": "PII",
    "privacy": "privacy-regulated data",
    "telemetry": "telemetry",
    "token": "tokens",
    "workflow": "workflow data",
}

_INTEGRATION_KEYWORDS = {
    "api": "external API",
    "browser": "browser surface",
    "ci": "CI system",
    "database": "database",
    "github": "GitHub",
    "jira": "Jira",
    "linear": "Linear",
    "oauth": "OAuth provider",
    "slack": "Slack",
    "webhook": "webhook",
}

_SECURITY_EVIDENCE_KEYWORDS = (
    "abuse",
    "auth",
    "compliance",
    "credential",
    "oauth",
    "pii",
    "privacy",
    "risk",
    "security",
    "threat",
    "token",
)


def build_design_brief_security_review_plan(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a security review plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    evidence_references = _collect_evidence_references(store, source_ideas)
    sensitive_data = _sensitive_data(design_brief, source_ideas)
    integration_risks = _integration_risks(design_brief, source_ideas)
    abuse_cases = _abuse_cases(design_brief, source_ideas, sensitive_data, integration_risks)
    evidence_gaps = _evidence_gaps(design_brief, source_ideas, evidence_references, sensitive_data, integration_risks)
    open_questions = _open_questions(evidence_gaps, sensitive_data, integration_risks)
    acceptance_checks = _acceptance_checks(sensitive_data, integration_risks, abuse_cases, evidence_gaps)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.security_review_plan",
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "review_gate": _review_gate(design_brief, evidence_gaps),
            "risk_count": len(integration_risks) + len(abuse_cases),
            "check_count": len(acceptance_checks),
            "evidence_gap_count": len(evidence_gaps),
            "sensitive_data_count": len(sensitive_data),
            "integration_risk_count": len(integration_risks),
        },
        "threat_model_scope": _threat_model_scope(design_brief, source_ideas, source_idea_ids),
        "sensitive_data": sensitive_data,
        "integration_risks": integration_risks,
        "abuse_cases": abuse_cases,
        "security_acceptance_checks": acceptance_checks,
        "evidence_references": evidence_references,
        "evidence_gaps": evidence_gaps,
        "open_questions": open_questions,
        "source_ideas": source_ideas,
    }


def render_design_brief_security_review_plan(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a security review plan as Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported security review plan format: {fmt}")

    brief = report["design_brief"]
    scope = report["threat_model_scope"]
    lines = [
        f"# Security Review Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Review gate: {report['summary']['review_gate']}",
        "",
        "## Review Scope",
        "",
        f"- Objective: {scope['objective']}",
        f"- Primary users: {scope['primary_users']}",
        f"- Source ideas: {_inline_ids(scope['source_idea_ids'])}",
        f"- Assets: {_inline_list(scope['assets'])}",
        f"- Entry points: {_inline_list(scope['entry_points'])}",
        f"- Trust boundaries: {_inline_list(scope['trust_boundaries'])}",
        f"- Out of scope: {_inline_list(scope['out_of_scope'])}",
        "",
        "## Risks",
        "",
        "### Sensitive Data",
        "",
    ]
    lines.extend(_render_items(report["sensitive_data"], "No sensitive data candidates were inferred."))
    lines.extend(["", "### Integration Risks", ""])
    lines.extend(_render_items(report["integration_risks"], "No integration risks were inferred."))
    lines.extend(["", "### Abuse Cases", ""])
    lines.extend(_render_items(report["abuse_cases"], "No abuse cases were inferred."))

    lines.extend(["", "## Checks", ""])
    for check in report["security_acceptance_checks"]:
        lines.extend(
            [
                f"### {check['id']}: {check['check']}",
                "",
                f"- Status: {check['status']}",
                f"- Required: {check['required']}",
                f"- Owner: {check['owner']}",
                f"- Evidence needed: {check['evidence_needed']}",
                f"- Source fields: {_inline_list(check['source_fields'])}",
                "",
            ]
        )

    lines.extend(["## Evidence Gaps", ""])
    lines.extend(_render_items(report["evidence_gaps"], "No evidence gaps were detected."))
    lines.extend(["", "## Open Questions", ""])
    lines.extend(f"- {question}" for question in report["open_questions"])
    return "\n".join(lines).rstrip() + "\n"


def security_review_plan_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-security-review-plan.{extension}"
    )


def _threat_model_scope(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> dict[str, Any]:
    concept = _first_text(design_brief.get("merged_product_concept"), _joined_fields(source_ideas, ("solution",)), design_brief["title"])
    workflow = _first_text(design_brief.get("workflow_context"), _joined_fields(source_ideas, ("workflow_context",)), "the primary handoff workflow")
    users = _first_text(design_brief.get("specific_user"), _joined_fields(source_ideas, ("specific_user", "target_users")), "unknown target users")
    return {
        "objective": f"Review how {concept} can be built without exposing users, credentials, data, or connected systems.",
        "primary_users": users,
        "workflow": workflow,
        "source_idea_ids": source_idea_ids,
        "assets": _scope_assets(design_brief, source_ideas),
        "entry_points": _entry_points(design_brief, source_ideas),
        "trust_boundaries": _trust_boundaries(design_brief, source_ideas),
        "out_of_scope": [
            "Penetration testing of systems not named by the persisted design brief.",
            "Production compliance certification or legal sign-off.",
        ],
    }


def _sensitive_data(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = _all_text(design_brief, source_ideas)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for keyword, label in sorted(_SENSITIVE_DATA_KEYWORDS.items(), key=lambda pair: pair[1]):
        if label in seen:
            continue
        if re.search(rf"\b{re.escape(keyword)}\b", text, flags=re.IGNORECASE):
            seen.add(label)
            items.append(
                {
                    "id": f"SD{len(items) + 1}",
                    "name": label,
                    "classification": "restricted" if keyword in {"oauth", "pii", "token"} else "internal",
                    "handling_requirement": _data_handling_requirement(keyword),
                    "source_fields": _fields_containing(design_brief, source_ideas, keyword),
                }
            )
    return items


def _integration_risks(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = _all_text(design_brief, source_ideas)
    risks: list[dict[str, Any]] = []
    for keyword, name in sorted(_INTEGRATION_KEYWORDS.items(), key=lambda pair: pair[1]):
        if not re.search(rf"\b{re.escape(keyword)}\b", text, flags=re.IGNORECASE):
            continue
        severity = "high" if keyword in {"api", "github", "oauth", "webhook"} else "medium"
        risks.append(
            {
                "id": f"IR{len(risks) + 1}",
                "name": name,
                "severity": severity,
                "risk": f"{name} creates an authentication, authorization, availability, or data exposure boundary.",
                "review_action": "Validate credentials, permission scope, rate limits, failure handling, and auditability before build.",
                "source_fields": _fields_containing(design_brief, source_ideas, keyword),
            }
        )
    if not risks:
        risks.append(
            {
                "id": "IR1",
                "name": "Primary application surface",
                "severity": "medium",
                "risk": "The brief implies a user-facing workflow but does not name external integrations.",
                "review_action": "Confirm whether the first build is self-contained or depends on unnamed systems.",
                "source_fields": ["merged_product_concept", "workflow_context"],
            }
        )
    return risks


def _abuse_cases(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    sensitive_data: list[dict[str, Any]],
    integration_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risks = _risk_texts(design_brief, source_ideas)
    cases = [
        {
            "id": "AC1",
            "abuse_case": "A user or autonomous builder overuses generated specs to access data or systems beyond the intended workflow.",
            "impact": "Privilege boundaries and implementation scope can drift during execution.",
            "mitigation": "Require least privilege permissions, explicit scope limits, and review before publication or build assignment.",
            "source_fields": ["mvp_scope", "workflow_context"],
        },
        {
            "id": "AC2",
            "abuse_case": "Malformed or adversarial input causes unsafe generated implementation guidance.",
            "impact": "Downstream builders may create vulnerable code paths or unsafe operational instructions.",
            "mitigation": "Add input validation, output review, and security acceptance checks to the handoff.",
            "source_fields": ["validation_plan", "risks"],
        },
    ]
    if sensitive_data:
        cases.append(
            {
                "id": "AC3",
                "abuse_case": "Sensitive data is logged, retained, or shared without a documented purpose.",
                "impact": "Users or customers may be exposed through telemetry, fixtures, prompts, or audit logs.",
                "mitigation": "Classify data, minimize collection, redact fixtures, and define retention before build.",
                "source_fields": ["workflow_context", "risks", "evidence_rationale"],
            }
        )
    if any(risk["severity"] == "high" for risk in integration_risks):
        cases.append(
            {
                "id": f"AC{len(cases) + 1}",
                "abuse_case": "Connected systems are called with excessive permissions or unsafe retry behavior.",
                "impact": "External accounts, repositories, tickets, or messages could be modified unexpectedly.",
                "mitigation": "Use scoped credentials, dry-run modes, idempotency, rate limits, and audit logs.",
                "source_fields": ["tech_approach", "suggested_stack"],
            }
        )
    for risk in risks[:2]:
        cases.append(
            {
                "id": f"AC{len(cases) + 1}",
                "abuse_case": f"Captured design risk materializes during implementation: {risk}",
                "impact": "Known domain risk could become a security blocker if not reviewed before execution.",
                "mitigation": "Turn the risk into an owner, decision, and acceptance check before build starts.",
                "source_fields": ["risks", "domain_risks"],
            }
        )
    return cases


def _acceptance_checks(
    sensitive_data: list[dict[str, Any]],
    integration_risks: list[dict[str, Any]],
    abuse_cases: list[dict[str, Any]],
    evidence_gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checks = [
        _check("SRC1", "Threat model scope is accepted by product and security owners.", "reviewed scope, assets, entry points, and out-of-scope list", ["merged_product_concept", "workflow_context", "mvp_scope"]),
        _check("SRC2", "Authentication and authorization boundaries are documented.", "permission model, privileged actions, and role assumptions", ["tech_approach", "suggested_stack"]),
        _check("SRC3", "Sensitive data handling is classified before implementation.", "data inventory, retention, redaction, and fixture guidance", ["workflow_context", "risks"]),
        _check("SRC4", "Integration credentials and failure modes are reviewed.", "credential scope, sandbox strategy, rate limits, retries, and audit events", ["tech_approach", "suggested_stack"]),
        _check("SRC5", "Abuse cases have mitigations or explicit acceptance decisions.", "owner decision for each listed abuse case", ["risks", "domain_risks"]),
    ]
    if sensitive_data:
        checks.append(_check("SRC6", "Logs, telemetry, and generated fixtures exclude unnecessary sensitive data.", "redaction tests or fixture policy", ["validation_plan", "workflow_context"]))
    if any(risk["severity"] == "high" for risk in integration_risks):
        checks.append(_check("SRC7", "High-risk integrations run with least privilege and observable audit trails.", "scoped credentials, dry-run path, and audit event checklist", ["tech_approach", "suggested_stack"]))
    if evidence_gaps:
        checks.append(_check("SRC8", "Evidence gaps are resolved or accepted before autonomous build assignment.", "dated decisions for missing evidence and unknowns", ["evidence_signals", "inspiring_insights"]))
    for check in checks:
        check["related_counts"] = {
            "sensitive_data": len(sensitive_data),
            "integration_risks": len(integration_risks),
            "abuse_cases": len(abuse_cases),
            "evidence_gaps": len(evidence_gaps),
        }
    return checks


def _check(item_id: str, check: str, evidence_needed: str, source_fields: list[str]) -> dict[str, Any]:
    return {
        "id": item_id,
        "check": check,
        "status": "pending",
        "required": True,
        "owner": "security_owner",
        "evidence_needed": evidence_needed,
        "source_fields": source_fields,
    }


def _evidence_gaps(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence_references: list[dict[str, Any]],
    sensitive_data: list[dict[str, Any]],
    integration_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not _clean(design_brief.get("workflow_context")):
        gaps.append(_gap("EG1", "unknown", "Workflow boundaries are not explicit.", "Document entry points, actors, privileged actions, and expected outputs."))
    if not _string_list(design_brief.get("mvp_scope")):
        gaps.append(_gap("EG2", "unknown", "MVP scope is not decomposed for review.", "List the build slices that need security acceptance checks."))
    if not _clean(design_brief.get("validation_plan")):
        gaps.append(_gap("EG3", "unknown", "Validation plan is missing security review criteria.", "Add security smoke tests, fixture policy, and approval gate."))
    if not evidence_references:
        gaps.append(_gap("EG4", "evidence_gap", "No security, privacy, risk, or compliance evidence is linked.", "Attach relevant persisted signals or insights to source ideas."))
    if not sensitive_data:
        gaps.append(_gap("EG5", "unknown", "Sensitive data classification is not explicit.", "Confirm whether personal, customer, credential, telemetry, or workflow data is in scope."))
    if len(source_ideas) < 2:
        gaps.append(_gap("EG6", "evidence_gap", "Brief has fewer than two persisted source ideas.", "Review whether the threat model depends on one uncorroborated idea."))
    if integration_risks and all(risk["name"] == "Primary application surface" for risk in integration_risks):
        gaps.append(_gap("EG7", "unknown", "External integration surface is not explicit.", "Confirm whether any APIs, webhooks, identity providers, or work tools are required."))
    return gaps


def _gap(item_id: str, kind: str, gap: str, resolution_path: str) -> dict[str, str]:
    return {"id": item_id, "kind": kind, "gap": gap, "resolution_path": resolution_path}


def _open_questions(
    evidence_gaps: list[dict[str, Any]],
    sensitive_data: list[dict[str, Any]],
    integration_risks: list[dict[str, Any]],
) -> list[str]:
    questions = [
        "Who owns the security approval decision before specs are assigned to builders?",
        "What actions must block launch if the review finds unresolved security risk?",
    ]
    if sensitive_data:
        questions.append("Which data classes are required for the MVP, and which can be removed or redacted?")
    if any(risk["severity"] == "high" for risk in integration_risks):
        questions.append("Which credentials, scopes, and audit events are required for each high-risk integration?")
    questions.extend(gap["resolution_path"] for gap in evidence_gaps[:3])
    return list(dict.fromkeys(questions))


def _scope_assets(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    assets = [
        "persisted design brief",
        "generated implementation handoff",
    ]
    if _first_text(design_brief.get("validation_plan"), _joined_fields(source_ideas, ("validation_plan",))):
        assets.append("validation artifacts")
    if _sensitive_data(design_brief, source_ideas):
        assets.append("sensitive workflow data")
    if _joined_fields(source_ideas, ("tech_approach", "suggested_stack")):
        assets.append("implementation credentials and configuration")
    return assets


def _entry_points(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    entries = ["design brief export", "generated Markdown or JSON artifact"]
    text = _all_text(design_brief, source_ideas)
    if re.search(r"\b(api|fastapi|route)\b", text, re.IGNORECASE):
        entries.append("API endpoint")
    if re.search(r"\b(cli|command)\b", text, re.IGNORECASE):
        entries.append("CLI command")
    if re.search(r"\b(mcp|agent|autonomous)\b", text, re.IGNORECASE):
        entries.append("agent or MCP tool request")
    return entries


def _trust_boundaries(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    boundaries = ["stored brief to generated review artifact", "human review to autonomous build assignment"]
    if _integration_risks(design_brief, source_ideas):
        boundaries.append("owned application code to external systems")
    if _sensitive_data(design_brief, source_ideas):
        boundaries.append("source evidence to generated fixtures, logs, or telemetry")
    return boundaries


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = list(design_brief.get("sources", []))
    if not sources:
        lead_id = design_brief.get("lead_idea_id")
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        for rank, idea_id in enumerate(design_brief.get("source_idea_ids", []), start=1):
            if idea_id != lead_id:
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

    for source in sources:
        idea_id = str(source["idea_id"])
        if idea_id in seen:
            continue
        seen.add(idea_id)
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append({"id": idea_id, "role": source.get("role", "source"), "rank": source.get("rank", 0), "missing": True})
            continue
        data = unit.model_dump(mode="json")
        data["role"] = source.get("role") or ("lead" if idea_id == design_brief.get("lead_idea_id") else "source")
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _collect_evidence_references(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    signal_source_ideas: dict[str, list[str]] = {}
    insight_source_ideas: dict[str, list[str]] = {}
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            signal_source_ideas.setdefault(signal_id, []).append(idea["id"])
        for insight_id in _string_list(idea.get("inspiring_insights")):
            insight_source_ideas.setdefault(insight_id, []).append(idea["id"])

    for signal_id in sorted(signal_source_ideas):
        signal = store.get_signal(signal_id)
        if not signal:
            continue
        source_type = signal.source_type.value if hasattr(signal.source_type, "value") else str(signal.source_type)
        text = " ".join([signal.title, signal.content, source_type, signal.signal_role, " ".join(signal.tags)])
        if _matches_security_evidence(text):
            refs.append(
                {
                    "kind": "signal",
                    "id": signal_id,
                    "title": signal.title,
                    "source_type": source_type,
                    "source_adapter": signal.source_adapter,
                    "url": signal.url,
                    "source_idea_ids": list(dict.fromkeys(signal_source_ideas[signal_id])),
                }
            )

    for insight_id in sorted(insight_source_ideas):
        insight = store.get_insight(insight_id)
        if not insight:
            continue
        category = insight.category.value if hasattr(insight.category, "value") else str(insight.category)
        if _matches_security_evidence(" ".join([insight.title, insight.summary, category])):
            refs.append(
                {
                    "kind": "insight",
                    "id": insight_id,
                    "title": insight.title,
                    "source_type": category,
                    "source_adapter": None,
                    "url": None,
                    "source_idea_ids": list(dict.fromkeys(insight_source_ideas[insight_id])),
                }
            )
    return sorted(refs, key=lambda ref: (ref["kind"], ref["id"]))


def _matches_security_evidence(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _SECURITY_EVIDENCE_KEYWORDS)


def _risk_texts(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    risks = _string_list(design_brief.get("risks"))
    for idea in source_ideas:
        risks.extend(_string_list(idea.get("domain_risks")))
    return list(dict.fromkeys(_compact(risk) for risk in risks if _compact(risk)))


def _data_handling_requirement(keyword: str) -> str:
    if keyword in {"oauth", "token"}:
        return "Do not persist secrets in prompts, logs, fixtures, or generated specs; use scoped secret storage."
    if keyword in {"pii", "privacy", "customer", "email"}:
        return "Minimize collection, document purpose, redact fixtures, and define retention and deletion."
    return "Document owner, purpose, minimum fields, retention, and logging rules."


def _fields_containing(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    keyword: str,
) -> list[str]:
    fields: list[str] = []
    for field in (
        "title",
        "domain",
        "theme",
        "buyer",
        "specific_user",
        "workflow_context",
        "why_this_now",
        "merged_product_concept",
        "synthesis_rationale",
        "mvp_scope",
        "first_milestones",
        "validation_plan",
        "risks",
    ):
        if re.search(rf"\b{re.escape(keyword)}\b", " ".join(_string_list(design_brief.get(field))), re.IGNORECASE):
            fields.append(f"design_brief.{field}")
    for idea in source_ideas:
        for field in (
            "problem",
            "solution",
            "target_users",
            "specific_user",
            "buyer",
            "workflow_context",
            "validation_plan",
            "domain_risks",
            "evidence_rationale",
            "tech_approach",
            "suggested_stack",
        ):
            if re.search(rf"\b{re.escape(keyword)}\b", " ".join(_string_list(idea.get(field))), re.IGNORECASE):
                fields.append(f"source_idea.{idea['id']}.{field}")
    return list(dict.fromkeys(fields)) or ["inferred"]


def _review_gate(design_brief: dict[str, Any], evidence_gaps: list[dict[str, Any]]) -> str:
    status = design_brief.get("design_status")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if any(gap["kind"] == "unknown" for gap in evidence_gaps):
        return "needs_security_discovery"
    if status in {"approved", "published"} and readiness >= 75:
        return "ready_for_security_review"
    return "needs_design_review"


def _all_text(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for field in (
        "title",
        "domain",
        "theme",
        "buyer",
        "specific_user",
        "workflow_context",
        "why_this_now",
        "merged_product_concept",
        "synthesis_rationale",
        "mvp_scope",
        "first_milestones",
        "validation_plan",
        "risks",
    ):
        values.extend(_string_list(design_brief.get(field)))
    for idea in source_ideas:
        for field in (
            "title",
            "one_liner",
            "problem",
            "solution",
            "target_users",
            "value_proposition",
            "specific_user",
            "buyer",
            "workflow_context",
            "validation_plan",
            "domain_risks",
            "evidence_rationale",
            "tech_approach",
            "suggested_stack",
        ):
            values.extend(_string_list(idea.get(field)))
    return " ".join(values)


def _joined_fields(source_ideas: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for idea in source_ideas:
        for field in fields:
            values.extend(_string_list(idea.get(field)))
    return "; ".join(list(dict.fromkeys(values)))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, dict):
        items: list[str] = []
        for key, item in value.items():
            items.extend([_compact(key), *_string_list(item)])
        return [item for item in items if item]
    if isinstance(value, (list, tuple, set)):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _clean(value: Any) -> str:
    return _compact(value)


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _render_items(items: list[dict[str, Any]], empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    lines: list[str] = []
    for item in items:
        label = item.get("name") or item.get("abuse_case") or item.get("gap") or item.get("risk")
        prefix = item.get("id", "-")
        lines.append(f"- **{prefix}**: {label}")
        if item.get("severity"):
            lines.append(f"  Severity: `{item['severity']}`.")
        if item.get("classification"):
            lines.append(f"  Classification: `{item['classification']}`.")
        if item.get("review_action"):
            lines.append(f"  Review action: {item['review_action']}")
        if item.get("mitigation"):
            lines.append(f"  Mitigation: {item['mitigation']}")
        if item.get("resolution_path"):
            lines.append(f"  Resolution: {item['resolution_path']}")
    return lines


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_") or "design-brief"
