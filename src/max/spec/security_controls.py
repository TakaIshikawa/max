"""Generate deterministic security control specifications for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


SECURITY_CONTROLS_SCHEMA_VERSION = "max-security-controls/v1"

SECURITY_CONTROLS_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "source_idea_id",
    "control_id",
    "control_category",
    "control_title",
    "control_owner",
    "control_status",
    "control_priority",
    "control_recommendation",
    "control_implementation_notes",
    "source_fields",
    "related_findings",
    "related_questions",
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

_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_security_controls(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic security control specifications."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source")
    source = source if isinstance(source, dict) else {}
    project = spec.get("project")
    project = project if isinstance(project, dict) else {}
    solution = spec.get("solution")
    solution = solution if isinstance(solution, dict) else {}
    execution = spec.get("execution")
    execution = execution if isinstance(execution, dict) else {}

    context = _security_context(spec, project, solution, execution)
    controls = _security_control_records(context)
    controls = _prioritize_controls(controls)

    return {
        "schema_version": SECURITY_CONTROLS_SCHEMA_VERSION,
        "kind": "max.security_controls",
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": _compact(project.get("title"))
            or _compact(source.get("idea_id"))
            or "Untitled TactSpec",
            "control_count": len(controls),
            "critical_control_count": sum(1 for item in controls if item["priority"] == "critical"),
            "high_control_count": sum(1 for item in controls if item["priority"] == "high"),
        },
        "controls": controls,
    }


def render_security_controls_csv(config: dict[str, Any]) -> str:
    """Render security controls as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(SECURITY_CONTROLS_CSV_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(config or {}):
        writer.writerow(row)  # type: ignore[arg-type]
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


def _security_control_records(context: dict[str, Any]) -> list[dict[str, Any]]:
    dependencies = ", ".join(context["detected_dependencies"]) or "external services"
    workflow = context["workflow_context"]
    records: list[dict[str, Any]] = []

    # Authentication control
    if context["mentions_authentication"]:
        records.append(
            _control(
                control_category="authentication",
                control_title="Define authentication boundary",
                control_recommendation=f"Document the identity provider, token/session validation path, and unauthenticated states for {workflow}.",
                control_owner="security_owner",
                control_priority="high",
                control_implementation_notes="Implement token validation, session management, and clear unauthenticated state handling.",
                source_fields=["project.workflow_context", "solution.technical_approach"],
            )
        )
    else:
        records.append(
            _control(
                control_category="authentication",
                control_title="Specify authentication requirements",
                control_recommendation="Clarify whether authentication is required and document the authentication mechanism.",
                control_owner="security_owner",
                control_priority="medium",
                control_implementation_notes="Determine if authentication is needed for the workflow; if not, document the rationale.",
                source_fields=["project.workflow_context"],
            )
        )

    # Authorization control
    if context["mentions_authorization"]:
        records.append(
            _control(
                control_category="authorization",
                control_title="Enforce least-privilege authorization",
                control_recommendation="Add role, ownership, scope, and tenant checks to every read, write, export, webhook, and admin action.",
                control_owner="backend_owner",
                control_priority="high",
                control_implementation_notes="Implement RBAC or attribute-based access control with explicit permission checks.",
                source_fields=["project.specific_user", "execution.mvp_scope"],
            )
        )
    else:
        records.append(
            _control(
                control_category="authorization",
                control_title="Define authorization model",
                control_recommendation="Specify roles, permissions, and access control requirements for protected resources.",
                control_owner="backend_owner",
                control_priority="medium",
                control_implementation_notes="Document authorization requirements even if simple; consider future extensibility.",
                source_fields=["project.specific_user"],
            )
        )

    # Secret handling control
    if context["mentions_secret_handling"]:
        records.append(
            _control(
                control_category="secret_handling",
                control_title="Protect secrets by default",
                control_recommendation="Store credentials only in a secret manager or encrypted configuration; redact them from logs and rotate them on compromise.",
                control_owner="platform_owner",
                control_priority="critical",
                control_implementation_notes="Use environment variables or secret management service; never commit secrets to source control.",
                source_fields=["solution.suggested_stack"],
            )
        )
    else:
        records.append(
            _control(
                control_category="secret_handling",
                control_title="Plan secret management strategy",
                control_recommendation="Determine if secrets are needed and document storage, rotation, and access control requirements.",
                control_owner="platform_owner",
                control_priority="medium",
                control_implementation_notes="Proactively plan for secret management even if not immediately required.",
                source_fields=["solution.suggested_stack"],
            )
        )

    # Data retention control
    if context["mentions_data_retention"]:
        records.append(
            _control(
                control_category="data_retention",
                control_title="Set retention and deletion rules",
                control_recommendation="Define what user, customer, export, backup, and log data is retained, for how long, and how deletion is verified.",
                control_owner="data_owner",
                control_priority="high",
                control_implementation_notes="Implement automated deletion workflows and data lifecycle policies; ensure compliance with regulations.",
                source_fields=["problem.current_workaround", "execution.risks"],
            )
        )
    else:
        records.append(
            _control(
                control_category="data_retention",
                control_title="Define data lifecycle policy",
                control_recommendation="Document data storage requirements, retention periods, and deletion criteria.",
                control_owner="data_owner",
                control_priority="medium",
                control_implementation_notes="Consider GDPR, CCPA, and other regulatory requirements for data lifecycle management.",
                source_fields=["problem.current_workaround"],
            )
        )

    # Dependency exposure control
    if context["mentions_external_dependencies"]:
        records.append(
            _control(
                control_category="dependency_exposure",
                control_title="Constrain dependency trust boundaries",
                control_recommendation=f"Pin permissions and failure handling for {dependencies}; validate webhook signatures, OAuth scopes, API timeouts, and vendor data flows.",
                control_owner="integration_owner",
                control_priority="high",
                control_implementation_notes="Implement circuit breakers, timeouts, and input validation for all external dependencies.",
                source_fields=["solution.suggested_stack", "solution.technical_approach"],
            )
        )
    else:
        records.append(
            _control(
                control_category="dependency_exposure",
                control_title="Document external dependencies",
                control_recommendation="Identify and document all external service dependencies and their trust requirements.",
                control_owner="integration_owner",
                control_priority="low",
                control_implementation_notes="Maintain a dependency inventory even if no external dependencies are currently identified.",
                source_fields=["solution.suggested_stack"],
            )
        )

    # Audit logging control
    if context["mentions_audit_logging"]:
        records.append(
            _control(
                control_category="audit_logging",
                control_title="Capture security audit events",
                control_recommendation="Log authentication failures, authorization denials, data exports, configuration changes, webhook verification failures, and credential rotations.",
                control_owner="security_owner",
                control_priority="high",
                control_implementation_notes="Implement structured logging with correlation IDs; ensure sensitive data is redacted.",
                source_fields=["execution.validation_plan"],
            )
        )
    else:
        records.append(
            _control(
                control_category="audit_logging",
                control_title="Plan audit logging strategy",
                control_recommendation="Define which events require audit logging and establish log retention policies.",
                control_owner="security_owner",
                control_priority="medium",
                control_implementation_notes="Consider compliance requirements and incident response needs when planning logging.",
                source_fields=["execution.validation_plan"],
            )
        )

    # Abuse cases control
    if context["mentions_abuse_cases"]:
        records.append(
            _control(
                control_category="abuse_cases",
                control_title="Test abuse resistance",
                control_recommendation="Add negative tests for replay, malformed input, excessive request rates, privilege escalation, data exfiltration, and integration failure loops.",
                control_owner="qa_owner",
                control_priority="high",
                control_implementation_notes="Implement rate limiting, input validation, and automated abuse detection mechanisms.",
                source_fields=["acceptance_criteria", "execution.risks"],
            )
        )
    else:
        records.append(
            _control(
                control_category="abuse_cases",
                control_title="Identify potential abuse scenarios",
                control_recommendation="Analyze the system for potential abuse vectors and document mitigation strategies.",
                control_owner="qa_owner",
                control_priority="medium",
                control_implementation_notes="Consider common attack patterns like rate abuse, input manipulation, and authorization bypass.",
                source_fields=["acceptance_criteria"],
            )
        )

    return records


def _control(
    *,
    control_category: str,
    control_title: str,
    control_recommendation: str,
    control_owner: str,
    control_priority: str,
    control_implementation_notes: str,
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": "",
        "category": control_category,
        "category_title": _CATEGORY_TITLES.get(control_category, control_category),
        "title": _compact(control_title),
        "owner": control_owner,
        "status": "recommended",
        "priority": control_priority,
        "recommendation": _compact(control_recommendation),
        "implementation_notes": _compact(control_implementation_notes),
        "source_fields": [field for field in source_fields if field],
    }


def _prioritize_controls(controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        controls,
        key=lambda item: (
            _PRIORITY_RANK.get(item["priority"], 4),
            item["category"],
        ),
    )
    return [{**item, "id": f"SC{index:02d}"} for index, item in enumerate(ordered, start=1)]


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


def _stack_components(stack: Any) -> list[str]:
    if not isinstance(stack, dict):
        return []
    return [_compact(value) for key, value in sorted(stack.items()) if key and _compact(value)]


def _csv_rows(config: dict[str, Any]) -> list[dict[str, str]]:
    controls = config.get("controls")
    if not isinstance(controls, list):
        return []
    return [_csv_row(config, item) for item in controls if isinstance(item, dict)]


def _csv_row(config: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    source = config.get("source")
    source = source if isinstance(source, dict) else {}
    return {
        "schema_version": _csv_cell(config.get("schema_version")),
        "kind": _csv_cell(config.get("kind")),
        "source_idea_id": _csv_cell(source.get("idea_id")),
        "control_id": _csv_cell(item.get("id")),
        "control_category": _csv_cell(item.get("category")),
        "control_title": _csv_cell(item.get("title")),
        "control_owner": _csv_cell(item.get("owner")),
        "control_status": _csv_cell(item.get("status")),
        "control_priority": _csv_cell(item.get("priority")),
        "control_recommendation": _csv_cell(item.get("recommendation")),
        "control_implementation_notes": _csv_cell(item.get("implementation_notes")),
        "source_fields": _csv_cell(item.get("source_fields")),
        "related_findings": _csv_cell(item.get("related_findings")),
        "related_questions": _csv_cell(item.get("related_questions")),
    }


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_cell(key)}={_csv_cell(item)}"
            for key, item in sorted(value.items())
            if _csv_cell(item)
        )
    if isinstance(value, (list, tuple, set)):
        return " | ".join(_csv_cell(item) for item in _list(value) if _csv_cell(item))
    return _compact(value)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
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
