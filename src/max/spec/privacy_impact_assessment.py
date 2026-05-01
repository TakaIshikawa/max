"""Generate deterministic privacy impact assessments for TactSpec previews."""

from __future__ import annotations

from typing import Any


PRIVACY_IMPACT_ASSESSMENT_SCHEMA_VERSION = "max-privacy-impact-assessment/v1"

_SUBJECT_DEFINITIONS = (
    (
        "customer",
        "Customers and account contacts",
        ("customer", "account", "buyer", "contact", "client"),
        "People represented in customer, account, or commercial workflow records.",
    ),
    (
        "end_user",
        "End users",
        ("user", "login", "profile", "participant", "consumer"),
        "People directly using the product or whose actions are processed by it.",
    ),
    (
        "patient",
        "Patients",
        ("patient", "clinic", "clinical", "health", "healthcare", "hipaa", "medical"),
        "People whose health, care, or clinical workflow data may be processed.",
    ),
    (
        "employee",
        "Employees and candidates",
        ("employee", "candidate", "hr", "payroll", "recruiting", "workforce"),
        "People in workforce, hiring, HR, or internal operations workflows.",
    ),
    (
        "student",
        "Students and guardians",
        ("student", "education", "school", "teacher", "course", "guardian"),
        "People in education, learning, or student support workflows.",
    ),
    (
        "operator",
        "Operators and administrators",
        ("admin", "operator", "maintainer", "support", "analyst", "moderator"),
        "People administering, supporting, or monitoring the workflow.",
    ),
)

_DATA_DEFINITIONS = (
    (
        "identifiers",
        "Direct identifiers",
        ("name", "email", "phone", "address", "contact", "profile", "identity", "pii"),
        "Names, contact details, profile fields, or other direct personal identifiers.",
        "high",
    ),
    (
        "account_records",
        "Account and workflow records",
        ("account", "customer", "crm", "ticket", "case", "record", "document", "message"),
        "Customer, account, ticket, message, document, or workflow content about a person.",
        "medium",
    ),
    (
        "regulated_sensitive_data",
        "Regulated or sensitive personal data",
        (
            "patient",
            "hipaa",
            "health",
            "medical",
            "payment",
            "financial",
            "student",
            "employee",
            "children",
            "gdpr",
            "consent",
        ),
        "Health, financial, education, workforce, child, consent, or other regulated personal data.",
        "high",
    ),
    (
        "authentication_data",
        "Authentication and access data",
        ("oauth", "sso", "saml", "oidc", "login", "token", "credential", "permission", "role"),
        "Authentication, authorization, role, credential, token, and access-control metadata.",
        "high",
    ),
    (
        "usage_telemetry",
        "Usage telemetry and audit data",
        ("analytics", "audit", "event", "log", "monitor", "telemetry", "trace", "usage"),
        "Usage events, audit trails, logs, diagnostics, and operational monitoring data.",
        "medium",
    ),
    (
        "ai_derived_data",
        "AI inputs and derived outputs",
        ("ai", "llm", "model", "openai", "prompt", "embedding", "summary", "generated"),
        "Prompts, model inputs, embeddings, generated summaries, and derived recommendations.",
        "medium",
    ),
)

_INTEGRATION_TERMS = {
    "api": "API",
    "github": "GitHub",
    "hubspot": "HubSpot",
    "openai": "OpenAI",
    "salesforce": "Salesforce",
    "slack": "Slack",
    "stripe": "Stripe",
    "teams": "Teams",
    "twilio": "Twilio",
    "webhook": "Webhook",
}

_REGULATED_TERMS = (
    "children",
    "consent",
    "education",
    "financial",
    "gdpr",
    "health",
    "healthcare",
    "hipaa",
    "hr",
    "medical",
    "patient",
    "payment",
    "student",
)


def generate_privacy_impact_assessment(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec-like dictionary into deterministic privacy impact guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}

    context = _privacy_context(spec, source, project, solution, execution)
    data_subjects = _data_subjects(context)
    personal_data = _personal_data(context)
    purposes = _processing_purposes(context, personal_data)
    risks = _privacy_risks(context, personal_data)
    mitigations = _mitigations(context, personal_data, risks)
    review_actions = _review_actions(context, personal_data, risks)

    return {
        "schema_version": PRIVACY_IMPACT_ASSESSMENT_SCHEMA_VERSION,
        "kind": "max.spec.privacy_impact_assessment",
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
            "workflow_context": context["workflow_context"],
            "privacy_gate": _privacy_gate(context, personal_data, risks),
            "privacy_sensitive_input_status": ("detected" if personal_data else "not_detected"),
            "data_subject_count": len(data_subjects),
            "personal_data_category_count": len(personal_data),
            "processing_purpose_count": len(purposes),
            "risk_count": len(risks),
            "mitigation_count": len(mitigations),
            "review_action_count": len(review_actions),
        },
        "privacy_context": context,
        "data_subjects": data_subjects,
        "personal_data": personal_data,
        "processing_purposes": purposes,
        "risks": risks,
        "mitigations": mitigations,
        "review_actions": review_actions,
    }


def render_privacy_impact_assessment_markdown(assessment: dict[str, Any]) -> str:
    """Render a generated privacy impact assessment as stable markdown."""
    summary = assessment.get("summary", {})
    source = assessment.get("source", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Privacy Impact Assessment",
        "",
        f"- Schema version: {_text(assessment.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Privacy gate: {_text(summary.get('privacy_gate'))}",
        f"- Privacy-sensitive inputs: {_text(summary.get('privacy_sensitive_input_status'))}",
        "",
    ]

    _extend_section(lines, "Data Subjects", assessment.get("data_subjects") or [], _render_subject)
    _extend_section(
        lines,
        "Personal Data",
        assessment.get("personal_data") or [],
        _render_personal_data,
        empty="No privacy-sensitive inputs were detected in the spec. Confirm field inventory before implementation.",
    )
    _extend_section(
        lines,
        "Processing Purposes",
        assessment.get("processing_purposes") or [],
        _render_purpose,
    )
    _extend_section(lines, "Privacy Risks", assessment.get("risks") or [], _render_risk)
    _extend_section(lines, "Mitigations", assessment.get("mitigations") or [], _render_mitigation)
    _extend_section(
        lines,
        "Review Actions",
        assessment.get("review_actions") or [],
        _render_review_action,
    )

    return "\n".join(lines).rstrip() + "\n"


def _privacy_context(
    spec: dict[str, Any],
    source: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    text = _haystack(spec)
    stack = solution.get("suggested_stack")
    integrations = _detected_integrations(text, stack)
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}

    return {
        "workflow_context": _workflow(project),
        "target_user": _compact(project.get("specific_user") or project.get("target_users"))
        or "primary user",
        "buyer": _compact(project.get("buyer")) or "launch sponsor",
        "domain": _compact(source.get("domain") or project.get("domain")),
        "category": _compact(source.get("category")),
        "detected_subject_terms": _detected_terms_by_definition(text, _SUBJECT_DEFINITIONS),
        "detected_data_terms": _detected_terms_by_definition(text, _DATA_DEFINITIONS),
        "detected_integrations": integrations,
        "regulated_or_sensitive_context": _contains_any(text, _REGULATED_TERMS),
        "mentions_consent": _contains_any(text, ("consent", "notice", "opt-in", "permission")),
        "mentions_retention": _contains_any(
            text, ("retention", "delete", "deletion", "ttl", "archive")
        ),
        "mentions_exports": _contains_any(text, ("export", "download", "csv", "report")),
        "mentions_logging": _contains_any(text, ("audit", "log", "trace", "monitor", "telemetry")),
        "mentions_external_transfer": bool(integrations)
        or _contains_any(text, ("api", "integration", "vendor", "third-party", "webhook")),
        "execution_risks": [
            _compact(risk) for risk in _list(execution.get("risks")) if _compact(risk)
        ],
        "evidence_refs": _evidence_refs(evidence),
    }


def _data_subjects(context: dict[str, Any]) -> list[dict[str, Any]]:
    subjects = []
    for subject_id, label, _terms, description in _SUBJECT_DEFINITIONS:
        evidence = context["detected_subject_terms"].get(subject_id, [])
        if not evidence:
            continue
        subjects.append(
            {
                "id": subject_id,
                "label": label,
                "description": description,
                "evidence": _evidence(
                    evidence, "project.specific_user", "project.workflow_context"
                ),
            }
        )

    if subjects:
        return subjects

    return [
        {
            "id": "target_user",
            "label": "Target user",
            "description": f"Conservative assumption for {context['target_user']} in the named workflow.",
            "evidence": ["project.specific_user", "project.target_users"],
        }
    ]


def _personal_data(context: dict[str, Any]) -> list[dict[str, Any]]:
    categories = []
    for category_id, label, _terms, description, risk_level in _DATA_DEFINITIONS:
        evidence = context["detected_data_terms"].get(category_id, [])
        if not evidence:
            continue
        categories.append(
            {
                "id": category_id,
                "label": label,
                "risk_level": risk_level,
                "description": description,
                "evidence": _evidence(
                    evidence, "problem.current_workaround", "solution.technical_approach"
                ),
                "handling_expectation": _handling_expectation(category_id, risk_level),
            }
        )
    return categories


def _processing_purposes(
    context: dict[str, Any], personal_data: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    purposes = [
        {
            "id": "PURP01",
            "title": "Deliver the core workflow",
            "description": f"Process the minimum information needed for {context['workflow_context']}.",
            "owner": "product_owner",
            "evidence": ["project.workflow_context", "execution.mvp_scope"],
        },
        {
            "id": "PURP02",
            "title": "Validate product and operational fit",
            "description": "Use pilot and validation data only to prove the workflow before broader launch.",
            "owner": "research_owner",
            "evidence": _evidence(context["evidence_refs"], "execution.validation_plan"),
        },
    ]
    if context["mentions_logging"] or personal_data:
        purposes.append(
            {
                "id": "PURP03",
                "title": "Maintain security, auditability, and reliability",
                "description": "Process operational metadata needed for access review, audit trails, abuse prevention, and support.",
                "owner": "security_owner",
                "evidence": ["solution.technical_approach", "execution.validation_plan"],
            }
        )
    if context["mentions_external_transfer"]:
        purposes.append(
            {
                "id": "PURP04",
                "title": "Operate approved integrations",
                "description": "Transmit only necessary fields to approved vendors, APIs, and customer systems.",
                "owner": "integration_owner",
                "evidence": _evidence(context["detected_integrations"], "solution.suggested_stack"),
            }
        )
    return purposes


def _privacy_risks(
    context: dict[str, Any], personal_data: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    risks = []
    if not personal_data:
        risks.append(
            _risk(
                "PIA-R01",
                "field_inventory_gap",
                "Personal data fields are not explicitly inventoried",
                "medium",
                "The spec does not name privacy-sensitive inputs, so data minimization and notice cannot be proven yet.",
                ["project", "problem", "solution"],
            )
        )
    if context["regulated_or_sensitive_context"] or any(
        item["id"] == "regulated_sensitive_data" for item in personal_data
    ):
        risks.append(
            _risk(
                "PIA-R02",
                "regulated_data_handling",
                "Regulated or sensitive data may need formal review",
                "high",
                "Domain or data terms indicate heightened privacy, consent, retention, or legal obligations.",
                _evidence(["regulated terms"], "source.domain", "problem.current_workaround"),
            )
        )
    if context["mentions_external_transfer"]:
        risks.append(
            _risk(
                "PIA-R03",
                "third_party_transfer",
                "External transfer paths can expand privacy obligations",
                "high" if context["regulated_or_sensitive_context"] else "medium",
                "Integrations, APIs, or webhooks may disclose personal data to subprocessors or customer systems.",
                _evidence(context["detected_integrations"], "solution.suggested_stack"),
            )
        )
    if context["mentions_logging"] or any(
        item["id"] == "usage_telemetry" for item in personal_data
    ):
        risks.append(
            _risk(
                "PIA-R04",
                "logging_duplication",
                "Logs and telemetry can duplicate personal data",
                "medium",
                "Operational events can copy identifiers, records, prompts, or sensitive fields outside primary storage.",
                ["solution.technical_approach", "execution.validation_plan"],
            )
        )
    if not context["mentions_retention"]:
        risks.append(
            _risk(
                "PIA-R05",
                "retention_gap",
                "Retention and deletion behavior is unresolved",
                "medium",
                "The spec does not prove how personal data, exports, logs, backups, or derived outputs are deleted.",
                ["execution.risks", "execution.validation_plan"],
            )
        )
    for risk in context["execution_risks"]:
        risks.append(
            _risk(
                f"PIA-R{len(risks) + 1:02d}",
                "execution_risk",
                "Execution risk references privacy handling",
                "medium",
                risk,
                ["execution.risks"],
            )
        )
    return _dedupe_items(risks)


def _mitigations(
    context: dict[str, Any],
    personal_data: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    actions = [
        (
            "product_owner",
            "Define required, optional, and prohibited personal data fields for each MVP workflow.",
        ),
        (
            "engineering_owner",
            "Minimize collection and redact personal data from logs, analytics, test fixtures, and errors.",
        ),
        (
            "privacy_owner",
            "Confirm notice, consent, customer instructions, and lawful basis before pilot use.",
        ),
        (
            "engineering_owner",
            "Set retention, deletion, export, backup, and derived-output handling before production launch.",
        ),
    ]
    if personal_data:
        actions.append(
            (
                "security_owner",
                "Protect detected personal data with role-based access, encryption, and audit review.",
            )
        )
    if any(risk["severity"] == "high" for risk in risks):
        actions.append(
            (
                "privacy_owner",
                "Require privacy or legal signoff before using production data in the workflow.",
            )
        )
    if context["mentions_external_transfer"]:
        actions.append(
            (
                "integration_owner",
                "Document vendor processors, payload fields, scopes, regions, retries, and deletion commitments.",
            )
        )
    return [
        {"id": f"PIA-M{index:02d}", "owner": owner, "action": action}
        for index, (owner, action) in enumerate(_dedupe_pairs(actions), start=1)
    ]


def _review_actions(
    context: dict[str, Any],
    personal_data: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions = [
        _review_action(
            "PIA-A01",
            "data_owner",
            "Complete field inventory",
            "List personal data fields, source systems, purpose, retention class, and allowed environments.",
            ["project", "problem", "solution"],
        ),
        _review_action(
            "PIA-A02",
            "engineering_owner",
            "Define deletion and export behavior",
            "Document deletion triggers for primary records, logs, backups, caches, exports, and generated outputs.",
            ["execution.validation_plan", "execution.risks"],
        ),
    ]
    if personal_data:
        actions.append(
            _review_action(
                "PIA-A03",
                "security_owner",
                "Review access and audit controls",
                "Confirm least-privilege access, audit events, and redaction for detected personal data categories.",
                [item["id"] for item in personal_data],
            )
        )
    if context["mentions_external_transfer"]:
        actions.append(
            _review_action(
                f"PIA-A{len(actions) + 1:02d}",
                "integration_owner",
                "Review third-party data transfers",
                "Approve processors, subprocessors, payloads, scopes, regions, and customer data-processing terms.",
                _evidence(context["detected_integrations"], "solution.suggested_stack"),
            )
        )
    if any(risk["severity"] == "high" for risk in risks):
        actions.append(
            _review_action(
                f"PIA-A{len(actions) + 1:02d}",
                "privacy_owner",
                "Record privacy gate decision",
                "Resolve high-severity privacy risks or explicitly accept residual risk before launch.",
                [risk["id"] for risk in risks if risk["severity"] == "high"],
            )
        )
    return actions


def _privacy_gate(
    context: dict[str, Any], personal_data: list[dict[str, Any]], risks: list[dict[str, Any]]
) -> str:
    if any(risk["severity"] == "high" for risk in risks):
        return "privacy_review_required"
    if not personal_data:
        return "field_inventory_required"
    if context["mentions_retention"] and not context["mentions_external_transfer"]:
        return "ready_with_controls"
    return "owner_review_required"


def _risk(
    risk_id: str,
    category: str,
    title: str,
    severity: str,
    description: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "category": category,
        "title": title,
        "severity": severity,
        "description": description,
        "evidence": evidence,
    }


def _review_action(
    action_id: str,
    owner: str,
    title: str,
    action: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "id": action_id,
        "owner": owner,
        "title": title,
        "action": action,
        "evidence": evidence,
    }


def _handling_expectation(category_id: str, risk_level: str) -> str:
    if category_id == "regulated_sensitive_data":
        return "Require privacy owner approval, explicit purpose, retention limit, and legal or compliance review."
    if category_id == "authentication_data":
        return "Exclude credentials and tokens from logs, exports, prompts, analytics, and test fixtures."
    if category_id == "ai_derived_data":
        return "Review prompt redaction, provider data-use terms, and output retention before production use."
    if risk_level == "high":
        return "Require least-privilege access, encryption, deletion path, and audit evidence."
    return "Limit collection, document purpose, redact unnecessary fields, and include in retention review."


def _render_subject(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('label'))}",
        "",
        f"- Description: {_text(item.get('description'))}",
        f"- Evidence: {_inline_list(item.get('evidence') or [])}",
    ]


def _render_personal_data(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('label'))}",
        "",
        f"- Risk level: {_text(item.get('risk_level'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Evidence: {_inline_list(item.get('evidence') or [])}",
        f"- Handling expectation: {_text(item.get('handling_expectation'))}",
    ]


def _render_purpose(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Evidence: {_inline_list(item.get('evidence') or [])}",
    ]


def _render_risk(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        "",
        f"- Category: {_text(item.get('category'))}",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Evidence: {_inline_list(item.get('evidence') or [])}",
    ]


def _render_mitigation(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Action: {_text(item.get('action'))}",
    ]


def _render_review_action(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Evidence: {_inline_list(item.get('evidence') or [])}",
    ]


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    render_item: Any,
    *,
    empty: str = "None.",
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend([empty, ""])
        return
    for item in items:
        lines.extend([*render_item(item), ""])


def _detected_terms_by_definition(
    text: str, definitions: tuple[tuple[Any, ...], ...]
) -> dict[str, list[str]]:
    return {
        definition[0]: [_term_label(term) for term in definition[2] if term in text]
        for definition in definitions
    }


def _detected_integrations(text: str, stack: Any) -> list[str]:
    detected = [label for term, label in sorted(_INTEGRATION_TERMS.items()) if term in text]
    if isinstance(stack, dict):
        for key, value in sorted(stack.items()):
            haystack = f"{key} {value}".lower()
            detected.extend(
                label for term, label in sorted(_INTEGRATION_TERMS.items()) if term in haystack
            )
    return _dedupe(detected)


def _evidence(values: list[str], *fallbacks: str) -> list[str]:
    return _dedupe([*values, *fallbacks])


def _evidence_refs(evidence: dict[str, Any]) -> list[str]:
    refs = []
    refs.extend(f"insight:{item}" for item in _list(evidence.get("insight_ids")))
    refs.extend(f"signal:{item}" for item in _list(evidence.get("signal_ids")))
    return _dedupe(refs)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


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


def _term_label(term: str) -> str:
    labels = {
        "ai": "AI",
        "api": "API",
        "crm": "CRM",
        "gdpr": "GDPR",
        "hipaa": "HIPAA",
        "llm": "LLM",
        "oauth": "OAuth",
        "oidc": "OIDC",
        "pii": "PII",
        "saml": "SAML",
        "sso": "SSO",
    }
    return labels.get(term, term)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _compact(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _dedupe_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for owner, action in values:
        key = (_compact(owner), _compact(action))
        if key[0] and key[1] and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (_text(item.get("category")), _text(item.get("description")).lower())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _inline_list(items: list[Any]) -> str:
    values = [_text(item) for item in items if _text(item)]
    if not values:
        return "none"
    return ", ".join(f"`{value}`" for value in values)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return _compact(value)
