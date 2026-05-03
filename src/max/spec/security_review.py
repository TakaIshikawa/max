"""Generate deterministic security reviews for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


SECURITY_REVIEW_SCHEMA_VERSION = "max-security-review/v1"

SECURITY_REVIEW_CSV_COLUMNS = (
    "section",
    "type",
    "source_idea_id",
    "source_status",
    "source_domain",
    "source_category",
    "tact_spec_schema_version",
    "title",
    "workflow_context",
    "target_user",
    "buyer",
    "stack",
    "recommendation",
    "overall_score",
    "finding_count",
    "high_or_critical_finding_count",
    "recommended_control_count",
    "open_question_count",
    "context_detected_dependencies",
    "context_mentions_authentication",
    "context_mentions_authorization",
    "context_mentions_secret_handling",
    "context_mentions_data_retention",
    "context_mentions_audit_logging",
    "context_mentions_abuse_cases",
    "item_id",
    "name",
    "category",
    "category_title",
    "severity",
    "status",
    "owner",
    "description",
    "recommendation_text",
    "evidence",
    "derived_from",
    "related_controls",
    "related_questions",
    "disposition",
    "question",
)

_CATEGORY_TITLES = {
    "authentication": "Authentication",
    "authorization": "Authorization",
    "secret_handling": "Secret handling",
    "data_retention": "Data retention",
    "dependency_exposure": "Dependency exposure",
    "audit_logging": "Audit logging",
    "abuse_cases": "Abuse cases",
}

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_security_review(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic security review guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    context = _security_context(spec, project, solution, execution)
    controls = _recommended_controls(context)
    questions = _open_questions(context)
    findings = _findings(context, controls, questions)

    return {
        "schema_version": SECURITY_REVIEW_SCHEMA_VERSION,
        "kind": "max.security_review",
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
            "stack": _stack_label(solution.get("suggested_stack")),
            "recommendation": evaluation.get("recommendation") if evaluation else None,
            "overall_score": evaluation.get("overall_score") if evaluation else None,
            "finding_count": len(findings),
            "high_or_critical_finding_count": sum(
                1 for finding in findings if finding["severity"] in {"critical", "high"}
            ),
            "recommended_control_count": len(controls),
            "open_question_count": len(questions),
        },
        "security_context": context,
        "findings": findings,
        "recommended_controls": controls,
        "open_questions": questions,
    }


def render_security_review_markdown(review: dict[str, Any]) -> str:
    """Render a generated security review as a stable markdown handoff document."""
    summary = review.get("summary", {})
    source = review.get("source", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Security Review",
        "",
        f"- Schema version: {_text(review.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Findings: {_text(summary.get('finding_count'))}",
        f"- High or critical findings: {_text(summary.get('high_or_critical_finding_count'))}",
        "",
    ]

    _extend_section(lines, "Findings", review.get("findings") or [], _render_finding)
    _extend_section(
        lines,
        "Recommended Controls",
        review.get("recommended_controls") or [],
        _render_control,
    )
    _extend_section(lines, "Open Questions", review.get("open_questions") or [], _render_question)

    return "\n".join(lines).rstrip() + "\n"


def render_security_review_csv(review: dict[str, Any]) -> str:
    """Render a generated security review as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=SECURITY_REVIEW_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(review):
        writer.writerow(row)
    return output.getvalue()


def _security_context(
    spec: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    stack = solution.get("suggested_stack")
    text = _haystack(spec)
    detected_auth = _detected_terms(text, ("oauth", "sso", "saml", "oidc", "jwt", "login", "auth"))
    detected_secrets = _detected_terms(
        text, ("secret", "token", "api key", "credential", "webhook", "private key")
    )
    detected_data = _detected_terms(
        text,
        (
            "customer",
            "user data",
            "pii",
            "personal data",
            "account",
            "email",
            "export",
            "retention",
        ),
    )
    detected_logging = _detected_terms(text, ("audit", "log", "trace", "event", "monitor"))
    vendors = _detected_vendors(text, stack)

    return {
        "workflow_context": _workflow(project),
        "stack_components": _stack_components(stack),
        "detected_authentication_terms": detected_auth,
        "detected_secret_terms": detected_secrets,
        "detected_data_terms": detected_data,
        "detected_logging_terms": detected_logging,
        "detected_dependencies": vendors,
        "mentions_external_dependencies": bool(vendors),
        "mentions_authentication": bool(detected_auth),
        "mentions_authorization": _contains_any(text, ("permission", "role", "rbac", "scope", "tenant")),
        "mentions_secret_handling": bool(detected_secrets),
        "mentions_data_retention": _contains_any(text, ("retention", "delete", "deletion", "ttl", "archive")),
        "mentions_audit_logging": _contains_any(text, ("audit", "log", "event", "trace")),
        "mentions_abuse_cases": _contains_any(
            text, ("rate limit", "abuse", "spam", "fraud", "prompt injection", "dos")
        ),
        "execution_risks": [
            _compact(risk) for risk in _list(execution.get("risks")) if _compact(risk)
        ],
    }


def _findings(
    context: dict[str, Any],
    controls: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    control_ids = _ids_by_category(controls)
    question_ids = _ids_by_category(questions)
    findings = [
        _finding(
            "SEC-F1",
            "authentication",
            "Authentication boundary must be explicit",
            _severity(context["mentions_authentication"], True),
            (
                "The spec references authentication mechanisms that need a concrete login, token validation, and session boundary."
                if context["mentions_authentication"]
                else "The spec does not name the authentication boundary for the workflow."
            ),
            _evidence(
                context["detected_authentication_terms"],
                "project.workflow_context",
                "solution.technical_approach",
            ),
            control_ids["authentication"],
            question_ids["authentication"],
        ),
        _finding(
            "SEC-F2",
            "authorization",
            "Authorization and tenant access need review",
            _severity(context["mentions_authorization"], True),
            (
                "Authorization terms are present; implementation should prove role, scope, and tenant checks on every protected action."
                if context["mentions_authorization"]
                else "The spec does not describe roles, scopes, ownership checks, or tenant isolation."
            ),
            ["project.specific_user", "execution.mvp_scope"],
            control_ids["authorization"],
            question_ids["authorization"],
        ),
        _finding(
            "SEC-F3",
            "secret_handling",
            "Secrets and credentials require explicit handling",
            _severity(context["mentions_secret_handling"], True),
            (
                "The spec references credentials or webhook material that must be stored, rotated, and redacted."
                if context["mentions_secret_handling"]
                else "The spec does not say how credentials, tokens, webhook secrets, or environment secrets are handled."
            ),
            _evidence(context["detected_secret_terms"], "solution.suggested_stack"),
            control_ids["secret_handling"],
            question_ids["secret_handling"],
        ),
        _finding(
            "SEC-F4",
            "data_retention",
            "Data retention and deletion policy is underspecified",
            _severity(context["mentions_data_retention"], True),
            (
                "Data retention language is present and should be converted into deletion, export, and backup behavior."
                if context["mentions_data_retention"]
                else "The spec references user or customer data without a concrete retention and deletion policy."
            ),
            _evidence(context["detected_data_terms"], "problem.current_workaround", "execution.risks"),
            control_ids["data_retention"],
            question_ids["data_retention"],
        ),
        _finding(
            "SEC-F5",
            "dependency_exposure",
            "External dependency exposure needs containment",
            "high" if context["mentions_external_dependencies"] else "medium",
            (
                "The spec names external services that can expose API, webhook, OAuth, availability, and data-transfer risk."
                if context["mentions_external_dependencies"]
                else "The spec does not identify external services, SDKs, webhooks, or API trust boundaries."
            ),
            _evidence(context["detected_dependencies"], "solution.suggested_stack"),
            control_ids["dependency_exposure"],
            question_ids["dependency_exposure"],
        ),
        _finding(
            "SEC-F6",
            "audit_logging",
            "Audit logging requirements need security coverage",
            _severity(context["mentions_audit_logging"], True),
            (
                "Logging terms are present; audit events should capture security decisions without leaking sensitive values."
                if context["mentions_audit_logging"]
                else "The spec does not identify audit events for privileged, data, or integration actions."
            ),
            _evidence(context["detected_logging_terms"], "execution.validation_plan"),
            control_ids["audit_logging"],
            question_ids["audit_logging"],
        ),
        _finding(
            "SEC-F7",
            "abuse_cases",
            "Abuse cases and rate limits are not yet proven",
            _severity(context["mentions_abuse_cases"], True),
            (
                "Abuse-case language is present and should be converted into throttles, validation, and alerting tests."
                if context["mentions_abuse_cases"]
                else "The spec does not describe abuse cases such as spam, replay, scraping, prompt injection, or denial of service."
            ),
            ["execution.risks", "acceptance_criteria"],
            control_ids["abuse_cases"],
            question_ids["abuse_cases"],
        ),
    ]
    return sorted(findings, key=lambda item: (_SEVERITY_RANK[item["severity"]], item["id"]))


def _recommended_controls(context: dict[str, Any]) -> list[dict[str, Any]]:
    dependencies = ", ".join(context["detected_dependencies"]) or "external services"
    workflow = context["workflow_context"]
    return [
        _control(
            "SEC-C1",
            "authentication",
            "Define authentication boundary",
            f"Document the identity provider, token/session validation path, and unauthenticated states for {workflow}.",
            "security_owner",
            ["project.workflow_context", "solution.technical_approach"],
        ),
        _control(
            "SEC-C2",
            "authorization",
            "Enforce least-privilege authorization",
            "Add role, ownership, scope, and tenant checks to every read, write, export, webhook, and admin action.",
            "backend_owner",
            ["project.specific_user", "execution.mvp_scope"],
        ),
        _control(
            "SEC-C3",
            "secret_handling",
            "Protect secrets by default",
            "Store credentials only in a secret manager or encrypted configuration; redact them from logs and rotate them on compromise.",
            "platform_owner",
            ["solution.suggested_stack"],
        ),
        _control(
            "SEC-C4",
            "data_retention",
            "Set retention and deletion rules",
            "Define what user, customer, export, backup, and log data is retained, for how long, and how deletion is verified.",
            "data_owner",
            ["problem.current_workaround", "execution.risks"],
        ),
        _control(
            "SEC-C5",
            "dependency_exposure",
            "Constrain dependency trust boundaries",
            f"Pin permissions and failure handling for {dependencies}; validate webhook signatures, OAuth scopes, API timeouts, and vendor data flows.",
            "integration_owner",
            ["solution.suggested_stack", "solution.technical_approach"],
        ),
        _control(
            "SEC-C6",
            "audit_logging",
            "Capture security audit events",
            "Log authentication failures, authorization denials, data exports, configuration changes, webhook verification failures, and credential rotations.",
            "security_owner",
            ["execution.validation_plan"],
        ),
        _control(
            "SEC-C7",
            "abuse_cases",
            "Test abuse resistance",
            "Add negative tests for replay, malformed input, excessive request rates, privilege escalation, data exfiltration, and integration failure loops.",
            "qa_owner",
            ["acceptance_criteria", "execution.risks"],
        ),
    ]


def _open_questions(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _question(
            "SEC-Q1",
            "authentication",
            "Which identity provider, token format, session lifetime, and unauthenticated paths are in scope?",
            "blocks_security_signoff" if not context["mentions_authentication"] else "needs_confirmation",
        ),
        _question(
            "SEC-Q2",
            "authorization",
            "Which roles, account boundaries, scopes, and ownership rules gate each MVP action?",
            "blocks_security_signoff" if not context["mentions_authorization"] else "needs_confirmation",
        ),
        _question(
            "SEC-Q3",
            "secret_handling",
            "Where are API keys, webhook secrets, OAuth tokens, and service credentials stored, rotated, and redacted?",
            "blocks_security_signoff" if not context["mentions_secret_handling"] else "needs_confirmation",
        ),
        _question(
            "SEC-Q4",
            "data_retention",
            "What data classes are stored, exported, backed up, deleted, or excluded from retention?",
            "blocks_security_signoff" if not context["mentions_data_retention"] else "needs_confirmation",
        ),
        _question(
            "SEC-Q5",
            "dependency_exposure",
            "Which external dependencies can receive data, trigger writes, or block the workflow?",
            "needs_confirmation" if context["mentions_external_dependencies"] else "blocks_security_signoff",
        ),
        _question(
            "SEC-Q6",
            "audit_logging",
            "Which events must be audit logged, who can read them, and how are sensitive fields redacted?",
            "blocks_security_signoff" if not context["mentions_audit_logging"] else "needs_confirmation",
        ),
        _question(
            "SEC-Q7",
            "abuse_cases",
            "What are the expected abuse cases, rate limits, replay protections, and alert thresholds?",
            "blocks_security_signoff" if not context["mentions_abuse_cases"] else "needs_confirmation",
        ),
    ]


def _finding(
    finding_id: str,
    category: str,
    title: str,
    severity: str,
    description: str,
    evidence: list[str],
    control_ids: list[str],
    question_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "category": category,
        "category_title": _CATEGORY_TITLES[category],
        "title": title,
        "severity": severity,
        "description": _compact(description),
        "evidence": evidence,
        "recommended_control_ids": control_ids,
        "open_question_ids": question_ids,
        "status": "open",
    }


def _control(
    control_id: str,
    category: str,
    title: str,
    recommendation: str,
    owner: str,
    derived_from: list[str],
) -> dict[str, Any]:
    return {
        "id": control_id,
        "category": category,
        "category_title": _CATEGORY_TITLES[category],
        "title": title,
        "recommendation": _compact(recommendation),
        "owner": owner,
        "derived_from": derived_from,
        "status": "recommended",
    }


def _question(question_id: str, category: str, question: str, disposition: str) -> dict[str, Any]:
    return {
        "id": question_id,
        "category": category,
        "category_title": _CATEGORY_TITLES[category],
        "question": _compact(question),
        "disposition": disposition,
    }


def _ids_by_category(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    result = {category: [] for category in _CATEGORY_TITLES}
    for item in items:
        category = item.get("category")
        item_id = item.get("id")
        if category in result and item_id:
            result[category].append(item_id)
    return result


def _severity(mentioned: bool, high_if_missing: bool) -> str:
    if mentioned:
        return "medium"
    return "high" if high_if_missing else "medium"


def _evidence(detected: list[str], *fallbacks: str) -> list[str]:
    return detected or [fallback for fallback in fallbacks if fallback]


def _detected_vendors(text: str, stack: Any) -> list[str]:
    known = (
        "aws",
        "azure",
        "github",
        "gitlab",
        "google",
        "hubspot",
        "oauth",
        "openai",
        "postgres",
        "salesforce",
        "slack",
        "stripe",
        "twilio",
        "webhook",
    )
    detected = [_vendor_label(term) for term in known if term in text]
    for component in _stack_components(stack):
        if _compact(component):
            detected.append(component)
    return _dedupe(detected)


def _vendor_label(term: str) -> str:
    labels = {
        "aws": "AWS",
        "azure": "Azure",
        "github": "GitHub",
        "gitlab": "GitLab",
        "google": "Google",
        "hubspot": "HubSpot",
        "oauth": "OAuth",
        "openai": "OpenAI",
        "postgres": "Postgres",
        "salesforce": "Salesforce",
        "slack": "Slack",
        "stripe": "Stripe",
        "twilio": "Twilio",
        "webhook": "Webhook",
    }
    return labels.get(term, term)


def _detected_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [_term_label(term) for term in terms if term in text]


def _term_label(term: str) -> str:
    return {
        "api key": "API key",
        "dos": "DoS",
        "jwt": "JWT",
        "oauth": "OAuth",
        "oidc": "OIDC",
        "pii": "PII",
        "rbac": "RBAC",
        "saml": "SAML",
        "sso": "SSO",
    }.get(term, term)


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


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict) and stack:
        values = [f"{key}={stack[key]}" for key in sorted(stack) if _compact(stack[key])]
        if values:
            return ", ".join(values)
    return "unspecified"


def _stack_components(stack: Any) -> list[str]:
    if not isinstance(stack, dict):
        return []
    return [_compact(value) for key, value in sorted(stack.items()) if key and _compact(value)]


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_finding(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        f"- Category: {_text(item.get('category_title'))}",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Evidence: {_inline_list(item.get('evidence') or [])}",
        f"- Recommended controls: {_inline_list(item.get('recommended_control_ids') or [])}",
        f"- Open questions: {_inline_list(item.get('open_question_ids') or [])}",
    ]


def _render_control(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        f"- Category: {_text(item.get('category_title'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Recommendation: {_text(item.get('recommendation'))}",
        f"- Derived from: {_inline_list(item.get('derived_from') or [])}",
    ]


def _render_question(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category_title'))}",
        f"- Disposition: {_text(item.get('disposition'))}",
        f"- Question: {_text(item.get('question'))}",
    ]


def _csv_rows(review: dict[str, Any]) -> list[dict[str, str]]:
    rows = [
        _csv_row(
            review,
            section="summary",
            type_="summary",
            item_id="summary",
            status=(review.get("summary") or {}).get("recommendation")
            if isinstance(review.get("summary"), dict)
            else None,
            description=(review.get("summary") or {}).get("workflow_context")
            if isinstance(review.get("summary"), dict)
            else None,
        )
    ]
    open_questions_by_category = _ids_by_category(_dict_items(review.get("open_questions")))
    controls_by_category = _ids_by_category(_dict_items(review.get("recommended_controls")))

    for finding in _dict_items(review.get("findings")):
        rows.append(
            _csv_row(
                review,
                section="findings",
                type_="finding",
                item_id=finding.get("id"),
                name=finding.get("title"),
                category=finding.get("category"),
                category_title=finding.get("category_title"),
                severity=finding.get("severity"),
                status=finding.get("status"),
                description=finding.get("description"),
                evidence=finding.get("evidence"),
                related_controls=finding.get("recommended_control_ids"),
                related_questions=finding.get("open_question_ids"),
            )
        )

    for control in _dict_items(review.get("recommended_controls")):
        category = _text(control.get("category"))
        rows.append(
            _csv_row(
                review,
                section="recommended_controls",
                type_="recommended_control",
                item_id=control.get("id"),
                name=control.get("title"),
                category=control.get("category"),
                category_title=control.get("category_title"),
                status=control.get("status"),
                owner=control.get("owner"),
                recommendation_text=control.get("recommendation"),
                derived_from=control.get("derived_from"),
                related_controls=[control.get("id")] if control.get("id") else [],
                related_questions=open_questions_by_category.get(category, []),
            )
        )

    for question in _dict_items(review.get("open_questions")):
        category = _text(question.get("category"))
        rows.append(
            _csv_row(
                review,
                section="open_questions",
                type_="open_question",
                item_id=question.get("id"),
                name=question.get("category_title"),
                category=question.get("category"),
                category_title=question.get("category_title"),
                disposition=question.get("disposition"),
                question=question.get("question"),
                related_controls=controls_by_category.get(category, []),
                related_questions=[question.get("id")] if question.get("id") else [],
            )
        )

    return rows


def _csv_row(
    review: dict[str, Any],
    *,
    section: Any,
    type_: Any,
    item_id: Any = None,
    name: Any = None,
    category: Any = None,
    category_title: Any = None,
    severity: Any = None,
    status: Any = None,
    owner: Any = None,
    description: Any = None,
    recommendation_text: Any = None,
    evidence: Any = None,
    derived_from: Any = None,
    related_controls: Any = None,
    related_questions: Any = None,
    disposition: Any = None,
    question: Any = None,
) -> dict[str, str]:
    source = review.get("source") if isinstance(review.get("source"), dict) else {}
    summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
    context = (
        review.get("security_context") if isinstance(review.get("security_context"), dict) else {}
    )
    values = {
        "section": section,
        "type": type_,
        "source_idea_id": source.get("idea_id"),
        "source_status": source.get("status"),
        "source_domain": source.get("domain"),
        "source_category": source.get("category"),
        "tact_spec_schema_version": source.get("tact_spec_schema_version"),
        "title": summary.get("title"),
        "workflow_context": summary.get("workflow_context"),
        "target_user": summary.get("target_user"),
        "buyer": summary.get("buyer"),
        "stack": summary.get("stack"),
        "recommendation": summary.get("recommendation"),
        "overall_score": summary.get("overall_score"),
        "finding_count": summary.get("finding_count"),
        "high_or_critical_finding_count": summary.get("high_or_critical_finding_count"),
        "recommended_control_count": summary.get("recommended_control_count"),
        "open_question_count": summary.get("open_question_count"),
        "context_detected_dependencies": context.get("detected_dependencies"),
        "context_mentions_authentication": context.get("mentions_authentication"),
        "context_mentions_authorization": context.get("mentions_authorization"),
        "context_mentions_secret_handling": context.get("mentions_secret_handling"),
        "context_mentions_data_retention": context.get("mentions_data_retention"),
        "context_mentions_audit_logging": context.get("mentions_audit_logging"),
        "context_mentions_abuse_cases": context.get("mentions_abuse_cases"),
        "item_id": item_id,
        "name": name,
        "category": category,
        "category_title": category_title,
        "severity": severity,
        "status": status,
        "owner": owner,
        "description": description,
        "recommendation_text": recommendation_text,
        "evidence": evidence,
        "derived_from": derived_from,
        "related_controls": related_controls,
        "related_questions": related_questions,
        "disposition": disposition,
        "question": question,
    }
    return {column: _csv_text(values.get(column)) for column in SECURITY_REVIEW_CSV_COLUMNS}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}={_csv_text(item)}"
            for key, item in sorted(value.items())
            if _csv_text(item)
        )
    if isinstance(value, list | tuple | set):
        return "; ".join(_csv_text(item) for item in value if _csv_text(item))
    return str(value).strip()


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
