"""Generate deterministic compliance checklists for TactSpec previews."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any


COMPLIANCE_CHECKLIST_SCHEMA_VERSION = "max-compliance-checklist/v1"

COMPLIANCE_CHECKLIST_CSV_COLUMNS = [
    "schema_version",
    "kind",
    "source_idea_id",
    "source_status",
    "source_type",
    "tact_spec_schema_version",
    "title",
    "domain",
    "domain_risk_level",
    "detected_data_terms",
    "detected_integrations",
    "section_id",
    "section_title",
    "item_id",
    "category",
    "blocking",
    "owner",
    "status",
    "requirement",
    "rationale",
    "evidence_needed",
    "remediation_guidance",
    "source_fields",
    "empty_state_guidance",
]

_CATEGORY_TITLES = {
    "privacy": "Privacy and Personal Data",
    "security": "Security and Access Control",
    "data_governance": "Data Governance",
    "regulatory": "Regulatory Review",
    "accessibility": "Accessibility",
    "ai_policy": "AI and Automation Policy",
    "third_party": "Third-Party Integrations",
    "launch_governance": "Launch Governance",
}

_CATEGORY_ORDER = tuple(_CATEGORY_TITLES)

_HIGH_RISK_DOMAINS = {
    "banking",
    "education",
    "finance",
    "financial",
    "fintech",
    "government",
    "health",
    "healthcare",
    "hr",
    "insurance",
    "legal",
    "medical",
    "payments",
    "public-sector",
}

_INTEGRATION_LABELS = {
    "aws": "AWS",
    "azure": "Azure",
    "datadog": "Datadog",
    "github": "GitHub",
    "gitlab": "GitLab",
    "google": "Google",
    "hubspot": "HubSpot",
    "jira": "Jira",
    "oauth": "OAuth",
    "openai": "OpenAI",
    "postgres": "Postgres",
    "salesforce": "Salesforce",
    "slack": "Slack",
    "stripe": "Stripe",
    "teams": "Teams",
    "trello": "Trello",
    "twilio": "Twilio",
    "webhook": "Webhook",
}


def generate_compliance_checklist(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic compliance handoff gates."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    context = _compliance_context(spec, source, project, solution, execution)
    items = _checklist_items(context)
    sections = _sections(items)

    return {
        "schema_version": COMPLIANCE_CHECKLIST_SCHEMA_VERSION,
        "kind": "max.compliance_checklist",
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "domain": source.get("domain"),
            "category": source.get("category"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": _compact(project.get("title"))
            or _compact(source.get("idea_id"))
            or "Untitled TactSpec",
            "target_user": _compact(project.get("specific_user") or project.get("target_users"))
            or "primary user",
            "buyer": _compact(project.get("buyer")) or "launch sponsor",
            "workflow_context": _workflow(project),
            "domain_risk_level": context["domain_risk_level"],
            "blocking_item_count": sum(1 for item in items if item["blocking"]),
            "item_count": len(items),
            "section_count": len(sections),
            "recommendation": evaluation.get("recommendation") if evaluation else None,
            "overall_score": evaluation.get("overall_score") if evaluation else None,
        },
        "compliance_context": context,
        "sections": sections,
        "checklist_items": items,
        "empty_state_guidance": _empty_state_guidance(items),
    }


def render_compliance_checklist_json(checklist: dict[str, Any]) -> str:
    """Render a generated compliance checklist as deterministic JSON."""
    return json.dumps(checklist, indent=2) + "\n"


def render_compliance_checklist_csv(checklist: dict[str, Any]) -> str:
    """Render a generated compliance checklist as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=COMPLIANCE_CHECKLIST_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(checklist or {}):
        writer.writerow(row)
    return output.getvalue()


def render_compliance_checklist_markdown(checklist: dict[str, Any]) -> str:
    """Render a generated compliance checklist as a stable markdown handoff document."""
    summary = checklist.get("summary", {})
    source = checklist.get("source", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Compliance Checklist",
        "",
        f"- Schema version: {_text(checklist.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Domain: {_text(source.get('domain')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Domain risk level: {_text(summary.get('domain_risk_level'))}",
        f"- Blocking items: {_text(summary.get('blocking_item_count'))}",
        "",
    ]

    lines.extend(
        [
            "## Compliance Context",
            "",
            f"- High-risk domain: {_text(checklist.get('compliance_context', {}).get('high_risk_domain'))}",
            f"- Detected data terms: {_inline_list(checklist.get('compliance_context', {}).get('detected_data_terms') or [])}",
            f"- Detected integrations: {_inline_list(checklist.get('compliance_context', {}).get('detected_integrations') or [])}",
            f"- Detected risk terms: {_inline_list(checklist.get('compliance_context', {}).get('detected_risk_terms') or [])}",
            "",
        ]
    )

    for section in checklist.get("sections") or []:
        lines.extend(_render_section(section))

    lines.extend(
        [
            "## Empty-State Guidance",
            "",
            _text(checklist.get("empty_state_guidance")),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _compliance_context(
    spec: dict[str, Any],
    source: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    text = _haystack(spec)
    domain = _compact(source.get("domain") or project.get("domain"))
    category = _compact(source.get("category"))
    domain_tokens = {part for value in (domain, category) for part in value.lower().split("-") if part}
    high_risk_domain = bool(domain_tokens & _HIGH_RISK_DOMAINS) or any(
        term in text for term in _HIGH_RISK_DOMAINS
    )
    data_terms = _detected_terms(
        text,
        (
            "account",
            "children",
            "consent",
            "customer",
            "delete",
            "email",
            "export",
            "patient",
            "personal data",
            "pii",
            "retention",
            "student",
            "telemetry",
            "user data",
        ),
    )
    auth_terms = _detected_terms(
        text, ("auth", "credential", "oauth", "permission", "rbac", "role", "sso", "token")
    )
    deployment_terms = _detected_terms(
        text, ("audit", "backup", "deploy", "log", "monitor", "production", "region", "rollback")
    )
    risk_terms = _detected_terms(
        text,
        (
            "accessibility",
            "compliance",
            "gdpr",
            "hipaa",
            "legal",
            "policy",
            "regulatory",
            "soc 2",
            "wcag",
        ),
    )
    ai_terms = _detected_terms(
        text, ("ai", "automation", "embedding", "llm", "model", "openai", "prompt")
    )
    integrations = _detected_integrations(text, solution.get("suggested_stack"))
    execution_risks = [
        _compact(risk) for risk in _list(execution.get("risks")) if _compact(risk)
    ]

    return {
        "workflow_context": _workflow(project),
        "target_user": _compact(project.get("specific_user") or project.get("target_users"))
        or "primary user",
        "domain": domain,
        "category": category,
        "domain_risk_level": "high" if high_risk_domain else "standard",
        "high_risk_domain": high_risk_domain,
        "detected_data_terms": data_terms,
        "detected_auth_terms": auth_terms,
        "detected_deployment_terms": deployment_terms,
        "detected_risk_terms": risk_terms,
        "detected_ai_terms": ai_terms,
        "detected_integrations": integrations,
        "execution_risks": execution_risks,
        "mentions_personal_data": bool(data_terms),
        "mentions_auth_or_permissions": bool(auth_terms),
        "mentions_deployment_controls": bool(deployment_terms),
        "mentions_regulatory_language": bool(risk_terms),
        "mentions_ai_or_automation": bool(ai_terms),
        "mentions_external_integrations": bool(integrations),
    }


def _checklist_items(context: dict[str, Any]) -> list[dict[str, Any]]:
    has_specialized_blocker = any(
        (
            context["high_risk_domain"],
            context["mentions_personal_data"],
            context["mentions_auth_or_permissions"],
            context["mentions_deployment_controls"],
            context["mentions_regulatory_language"],
            context["mentions_ai_or_automation"],
            context["mentions_external_integrations"],
        )
    )
    items = [
        _item(
            "COMP1",
            "privacy",
            "Confirm personal data classification and user notice",
            "privacy_owner",
            context["mentions_personal_data"] or context["high_risk_domain"],
            "Map each personal, customer, patient, student, or account data field to purpose, notice, consent, and minimization decisions.",
            _evidence(context["detected_data_terms"], "project.target_users", "problem.current_workaround"),
            "Document data classes, lawful basis or user notice, and fields excluded from MVP collection.",
        ),
        _item(
            "COMP2",
            "security",
            "Review access controls and credential handling",
            "security_owner",
            context["mentions_auth_or_permissions"] or context["mentions_external_integrations"],
            "Convert authentication, authorization, token, and secret assumptions into reviewed implementation gates.",
            _evidence(
                context["detected_auth_terms"],
                "solution.technical_approach",
                "solution.suggested_stack",
            ),
            "Name identity boundaries, roles, credential storage, rotation, and log redaction requirements.",
        ),
        _item(
            "COMP3",
            "data_governance",
            "Set retention, deletion, export, and audit requirements",
            "data_owner",
            context["mentions_personal_data"] or context["mentions_deployment_controls"],
            "Data lifecycle behavior must be explicit before implementation persists records or emits logs.",
            _evidence(context["detected_data_terms"], "execution.validation_plan", "execution.risks"),
            "Define retention periods, deletion paths, export behavior, backup handling, and audit evidence.",
        ),
        _item(
            "COMP4",
            "regulatory",
            "Obtain regulated-domain or policy owner review",
            "compliance_owner",
            context["high_risk_domain"] or context["mentions_regulatory_language"],
            "Regulated domains and explicit compliance language require accept-or-block review before coding begins.",
            _evidence(context["detected_risk_terms"], "source.domain", "execution.risks"),
            "Route the spec to legal, compliance, or policy owners and record required constraints as acceptance criteria.",
        ),
        _item(
            "COMP5",
            "accessibility",
            "Plan accessibility coverage for user-facing workflows",
            "design_owner",
            "accessibility" in [term.lower() for term in context["detected_risk_terms"]]
            or "WCAG" in context["detected_risk_terms"],
            "User-facing workflows need baseline keyboard, screen reader, contrast, and error-state expectations.",
            _evidence(context["detected_risk_terms"], "project.workflow_context", "execution.mvp_scope"),
            "Add WCAG-oriented acceptance criteria or explicitly document why no user-facing surface is in scope.",
        ),
        _item(
            "COMP6",
            "ai_policy",
            "Review AI, model, and automation policy requirements",
            "policy_owner",
            context["mentions_ai_or_automation"],
            "AI and automation features can introduce model behavior, prompt injection, data-use, and human-review obligations.",
            _evidence(context["detected_ai_terms"], "solution.technical_approach"),
            "Define allowed inputs, model providers, logging/redaction rules, human review points, and fallback behavior.",
        ),
        _item(
            "COMP7",
            "third_party",
            "Validate third-party integration terms and data flows",
            "integration_owner",
            context["mentions_external_integrations"],
            "External integrations can move data across vendors, trigger writes, or impose API and marketplace policy obligations.",
            _evidence(context["detected_integrations"], "solution.suggested_stack"),
            "List vendor data exchanged, scopes requested, webhook signatures, retry limits, and required vendor approvals.",
        ),
        _item(
            "COMP8",
            "launch_governance",
            "Record compliance signoff before implementation handoff",
            "product_owner",
            has_specialized_blocker,
            "Implementation agents need an explicit compliance decision, even when no specialized category is triggered.",
            ["source.status", "evaluation.recommendation", "acceptance_criteria"],
            "Add each blocking item to acceptance criteria with owner, due date, and evidence link before build starts.",
        ),
    ]
    return sorted(items, key=lambda item: (_CATEGORY_ORDER.index(item["category"]), item["id"]))


def _sections(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections = []
    for category in _CATEGORY_ORDER:
        category_items = [item for item in items if item["category"] == category]
        sections.append(
            {
                "id": category,
                "title": _CATEGORY_TITLES[category],
                "gate_status": (
                    "blocks_implementation"
                    if any(item["blocking"] for item in category_items)
                    else "advisory"
                ),
                "item_count": len(category_items),
                "blocking_item_count": sum(1 for item in category_items if item["blocking"]),
                "items": category_items,
            }
        )
    return sections


def _item(
    item_id: str,
    category: str,
    title: str,
    owner: str,
    blocking: bool,
    rationale: str,
    evidence_needed: list[str],
    remediation_guidance: str,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "category": category,
        "category_title": _CATEGORY_TITLES[category],
        "title": title,
        "owner": owner,
        "status": "open",
        "blocking": bool(blocking),
        "rationale": _compact(rationale),
        "evidence_needed": evidence_needed,
        "remediation_guidance": _compact(remediation_guidance),
    }


def _empty_state_guidance(items: list[dict[str, Any]]) -> str:
    if any(item["blocking"] for item in items):
        return (
            "Resolve blocking checklist items before implementation handoff; advisory items should be "
            "accepted, waived, or converted into follow-up tasks."
        )
    return (
        "No specialized compliance trigger was detected; still record product-owner signoff and revisit "
        "this checklist if scope, data handling, integrations, deployment region, or target users change."
    )


def _render_section(section: dict[str, Any]) -> list[str]:
    lines = [
        f"## {_text(section.get('title'))}",
        "",
        f"- Gate status: {_text(section.get('gate_status'))}",
        f"- Items: {_text(section.get('item_count'))}",
        f"- Blocking items: {_text(section.get('blocking_item_count'))}",
        "",
    ]
    items = section.get("items") or []
    if not items:
        lines.extend(["No checklist items generated for this section.", ""])
        return lines
    for item in items:
        lines.extend(
            [
                f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
                "",
                f"- Owner: {_text(item.get('owner'))}",
                f"- Status: {_text(item.get('status'))}",
                f"- Blocking: {_text(item.get('blocking'))}",
                f"- Rationale: {_text(item.get('rationale'))}",
                f"- Evidence needed: {_inline_list(item.get('evidence_needed') or [])}",
                f"- Remediation guidance: {_text(item.get('remediation_guidance'))}",
                "",
            ]
        )
    return lines


def _csv_rows(checklist: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_item_ids: set[str] = set()

    for section in _csv_sections(checklist):
        for item in _csv_section_items(section):
            item_id = _csv_text(item.get("id"))
            if item_id:
                seen_item_ids.add(item_id)
            rows.append(_csv_row(checklist, section, item))

    section_by_id = {
        _csv_text(section.get("id")): section
        for section in _csv_sections(checklist)
        if _csv_text(section.get("id"))
    }
    for item in _csv_items(checklist.get("checklist_items")):
        item_id = _csv_text(item.get("id"))
        if item_id in seen_item_ids:
            continue
        section_id = _csv_text(item.get("category"))
        section = section_by_id.get(section_id) or {
            "id": section_id,
            "title": item.get("category_title") or _CATEGORY_TITLES.get(section_id, section_id),
        }
        rows.append(_csv_row(checklist, section, item))

    if rows:
        return sorted(rows, key=_csv_row_sort_key)

    return [_csv_row(checklist, {}, {})]


def _csv_sections(checklist: dict[str, Any]) -> list[dict[str, Any]]:
    sections = _csv_items(checklist.get("sections"))
    return sorted(sections, key=_csv_section_sort_key)


def _csv_section_items(section: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(_csv_items(section.get("items")), key=_csv_item_sort_key)


def _csv_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _csv_row(
    checklist: dict[str, Any],
    section: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, str]:
    source = checklist.get("source") if isinstance(checklist.get("source"), dict) else {}
    summary = checklist.get("summary") if isinstance(checklist.get("summary"), dict) else {}
    context = (
        checklist.get("compliance_context")
        if isinstance(checklist.get("compliance_context"), dict)
        else {}
    )
    category = item.get("category") or section.get("id")
    values = {
        "schema_version": checklist.get("schema_version"),
        "kind": checklist.get("kind"),
        "source_idea_id": source.get("idea_id"),
        "source_status": source.get("status"),
        "source_type": source.get("type"),
        "tact_spec_schema_version": source.get("tact_spec_schema_version"),
        "title": summary.get("title"),
        "domain": context.get("domain") or source.get("domain"),
        "domain_risk_level": summary.get("domain_risk_level") or context.get("domain_risk_level"),
        "detected_data_terms": context.get("detected_data_terms"),
        "detected_integrations": context.get("detected_integrations"),
        "section_id": section.get("id"),
        "section_title": section.get("title"),
        "item_id": item.get("id"),
        "category": category,
        "blocking": item.get("blocking"),
        "owner": item.get("owner"),
        "status": item.get("status"),
        "requirement": item.get("title"),
        "rationale": item.get("rationale"),
        "evidence_needed": item.get("evidence_needed"),
        "remediation_guidance": item.get("remediation_guidance"),
        "source_fields": item.get("source_fields") or item.get("evidence_needed"),
        "empty_state_guidance": checklist.get("empty_state_guidance"),
    }
    return {column: _csv_text(values.get(column)) for column in COMPLIANCE_CHECKLIST_CSV_COLUMNS}


def _csv_section_sort_key(section: dict[str, Any]) -> tuple[int, str]:
    section_id = _csv_text(section.get("id"))
    try:
        priority = _CATEGORY_ORDER.index(section_id)
    except ValueError:
        priority = len(_CATEGORY_ORDER)
    return priority, section_id or _csv_text(section.get("title"))


def _csv_item_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    category = _csv_text(item.get("category"))
    try:
        priority = _CATEGORY_ORDER.index(category)
    except ValueError:
        priority = len(_CATEGORY_ORDER)
    return priority, _csv_text(item.get("id")) or _csv_text(item.get("title"))


def _csv_row_sort_key(row: dict[str, str]) -> tuple[int, str, str]:
    section_id = row.get("section_id", "")
    try:
        priority = _CATEGORY_ORDER.index(section_id)
    except ValueError:
        priority = len(_CATEGORY_ORDER)
    return priority, section_id, row.get("item_id", "")


def _detected_integrations(text: str, stack: Any) -> list[str]:
    detected = [_INTEGRATION_LABELS[term] for term in sorted(_INTEGRATION_LABELS) if term in text]
    if isinstance(stack, dict):
        for key, value in sorted(stack.items()):
            if _compact(key):
                detected.extend(_integration_labels(str(key).lower()))
            if _compact(value):
                detected.extend(_integration_labels(str(value).lower()))
    return _dedupe(detected)


def _integration_labels(value: str) -> list[str]:
    return [_INTEGRATION_LABELS[term] for term in sorted(_INTEGRATION_LABELS) if term in value]


def _detected_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [_term_label(term) for term in terms if term in text]


def _term_label(term: str) -> str:
    labels = {
        "auth": "auth",
        "gdpr": "GDPR",
        "hipaa": "HIPAA",
        "llm": "LLM",
        "oauth": "OAuth",
        "pii": "PII",
        "rbac": "RBAC",
        "soc 2": "SOC 2",
        "sso": "SSO",
        "wcag": "WCAG",
    }
    return labels.get(term, term)


def _evidence(detected: list[str], *fallbacks: str) -> list[str]:
    return detected or [fallback for fallback in fallbacks if fallback]


def _haystack(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            parts.append(_haystack(value[key]))
    elif isinstance(value, list):
        for item in value:
            parts.append(_haystack(item))
    elif value is not None:
        parts.append(str(value))
    return " ".join(parts).lower()


def _workflow(project: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _compact(project.get("summary"))
        or "primary workflow"
    )


def _inline_list(items: list[Any]) -> str:
    values = [_text(item) for item in items if _text(item)]
    if not values:
        return "none"
    return ", ".join(f"`{value}`" for value in values)


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _compact(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return _compact(value)


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}: {_csv_text(item)}"
            for key, item in sorted(value.items())
            if _csv_text(item)
        )
    if isinstance(value, (list, tuple, set)):
        values = sorted(value, key=_csv_text) if isinstance(value, set) else value
        return "; ".join(_csv_text(item) for item in values if _csv_text(item))
    return _compact(value)
