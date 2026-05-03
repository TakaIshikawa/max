"""Generate deterministic data classification guidance for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


DATA_CLASSIFICATION_SCHEMA_VERSION = "max-data-classification/v1"
DATA_CLASSIFICATION_CSV_COLUMNS = (
    "section",
    "row_type",
    "source_idea_id",
    "source_status",
    "source_domain",
    "source_category",
    "tact_spec_schema_version",
    "title",
    "workflow_context",
    "target_user",
    "sensitivity_level",
    "item_id",
    "item_name",
    "classification",
    "sensitivity",
    "data_category",
    "handling_requirement",
    "owner",
    "control",
    "evidence",
    "source_context",
    "description",
    "risk_level",
    "guidance",
)

_CATEGORY_DEFINITIONS = (
    (
        "personal_identifiers",
        "Personal identifiers",
        ("email", "name", "phone", "address", "contact", "user data", "personal data", "pii"),
        "Data that can identify a person, customer, user, or contact.",
        "confidential",
    ),
    (
        "regulated_personal_data",
        "Regulated personal data",
        ("patient", "hipaa", "health", "medical", "student", "children", "gdpr", "consent"),
        "Data that may trigger privacy, health, education, or consent obligations.",
        "restricted",
    ),
    (
        "account_and_customer_records",
        "Account and customer records",
        ("account", "customer", "crm", "salesforce", "hubspot", "renewal", "ticket"),
        "Operational records about customers, accounts, tickets, or commercial workflows.",
        "confidential",
    ),
    (
        "payment_or_financial_data",
        "Payment or financial data",
        ("payment", "billing", "invoice", "stripe", "card", "bank", "finance", "financial"),
        "Payment, billing, invoice, or financial workflow data.",
        "restricted",
    ),
    (
        "authentication_and_secrets",
        "Authentication and secrets",
        ("oauth", "token", "secret", "api key", "credential", "password", "webhook signature"),
        "Credentials, tokens, scopes, webhook secrets, and authentication metadata.",
        "restricted",
    ),
    (
        "behavioral_telemetry",
        "Behavioral telemetry",
        ("analytics", "audit", "event", "log", "monitor", "telemetry", "trace"),
        "Logs, audit events, analytics, traces, and monitoring data emitted by the product.",
        "confidential",
    ),
    (
        "ai_inputs_and_outputs",
        "AI inputs and outputs",
        ("ai", "embedding", "llm", "model", "openai", "prompt", "summary"),
        "Prompts, model inputs, generated summaries, embeddings, and other AI-derived content.",
        "confidential",
    ),
)

_CATEGORY_ORDER = {category_id: index for index, (category_id, *_rest) in enumerate(_CATEGORY_DEFINITIONS)}
_SENSITIVITY_RANK = {"restricted": 0, "confidential": 1, "internal": 2}

_DATA_STORE_TERMS = {
    "database": "Database",
    "db": "Database",
    "postgres": "Postgres",
    "postgresql": "Postgres",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "s3": "S3",
    "storage": "Object storage",
    "warehouse": "Data warehouse",
    "cache": "Cache",
}

_TRANSFER_TERMS = {
    "api": "API",
    "email": "Email",
    "export": "Export",
    "github": "GitHub",
    "gitlab": "GitLab",
    "hubspot": "HubSpot",
    "openai": "OpenAI",
    "salesforce": "Salesforce",
    "slack": "Slack",
    "stripe": "Stripe",
    "teams": "Teams",
    "twilio": "Twilio",
    "webhook": "Webhook",
}

_REGULATED_DOMAINS = {
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
}


def generate_data_classification(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec-like dictionary into deterministic data handling guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}

    context = _classification_context(spec, source, project, solution, execution)
    categories = _data_categories(context)
    sensitivity = _overall_sensitivity(categories, context)
    risk_notes = _risk_notes(categories, context)
    retention = _retention_guidance(sensitivity, context)
    storage = _storage_touchpoints(context)
    transfer = _transfer_touchpoints(context)
    safeguards = _safeguards(categories, sensitivity, context, storage, transfer)

    return {
        "schema_version": DATA_CLASSIFICATION_SCHEMA_VERSION,
        "kind": "max.spec.data_classification",
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
            "workflow_context": _workflow(project),
            "sensitivity_level": sensitivity,
            "category_count": len(categories),
            "safeguard_count": len(safeguards),
            "storage_touchpoint_count": len(storage),
            "transfer_touchpoint_count": len(transfer),
        },
        "classification_context": context,
        "data_categories": categories,
        "sensitivity": {
            "level": sensitivity,
            "rationale": _sensitivity_rationale(sensitivity, categories, context),
        },
        "retention_guidance": retention,
        "compliance_considerations": _compliance_considerations(context, categories),
        "storage_touchpoints": storage,
        "transfer_touchpoints": transfer,
        "risk_notes": risk_notes,
        "implementation_safeguards": safeguards,
    }


def render_data_classification_markdown(classification: dict[str, Any]) -> str:
    """Render a generated data classification artifact as stable markdown."""
    summary = classification.get("summary", {})
    source = classification.get("source", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Data Classification",
        "",
        f"- Schema version: {_text(classification.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Sensitivity level: {_text(summary.get('sensitivity_level'))}",
        f"- Data categories: {_text(summary.get('category_count'))}",
        "",
        "## Data Categories",
        "",
    ]

    for category in classification.get("data_categories") or []:
        lines.extend(
            [
                f"### {_text(category.get('id'))}: {_text(category.get('label'))}",
                "",
                f"- Sensitivity: {_text(category.get('sensitivity'))}",
                f"- Description: {_text(category.get('description'))}",
                f"- Evidence: {_inline_list(category.get('evidence') or [])}",
                f"- Handling notes: {_text(category.get('handling_notes'))}",
                "",
            ]
        )

    lines.extend(
        [
            "## Retention Guidance",
            "",
            f"- Default retention: {_text(classification.get('retention_guidance', {}).get('default_retention'))}",
            f"- Deletion trigger: {_text(classification.get('retention_guidance', {}).get('deletion_trigger'))}",
            f"- Backup handling: {_text(classification.get('retention_guidance', {}).get('backup_handling'))}",
            f"- Review cadence: {_text(classification.get('retention_guidance', {}).get('review_cadence'))}",
            "",
            "## Storage Touchpoints",
            "",
            *_bullets(
                [
                    f"{item['id']} [{item['risk_level']}]: {item['name']} - {item['guidance']}"
                    for item in classification.get("storage_touchpoints") or []
                ],
                empty="None identified.",
            ),
            "",
            "## Transfer Touchpoints",
            "",
            *_bullets(
                [
                    f"{item['id']} [{item['risk_level']}]: {item['name']} - {item['guidance']}"
                    for item in classification.get("transfer_touchpoints") or []
                ],
                empty="None identified.",
            ),
            "",
            "## Compliance Considerations",
            "",
            *_bullets(classification.get("compliance_considerations") or [], empty="None."),
            "",
            "## Risk Notes",
            "",
            *_bullets(classification.get("risk_notes") or [], empty="None."),
            "",
            "## Safeguards",
            "",
            *_bullets(
                [
                    f"{item['id']} [{item['owner']}]: {item['requirement']}"
                    for item in classification.get("implementation_safeguards") or []
                ],
                empty="None.",
            ),
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def render_data_classification_csv(classification: dict[str, Any]) -> str:
    """Render a generated data classification artifact as stable CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=DATA_CLASSIFICATION_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(classification):
        writer.writerow(row)
    return output.getvalue()


def _classification_context(
    spec: dict[str, Any],
    source: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    text = _haystack(spec)
    stack = solution.get("suggested_stack")
    domain = _compact(source.get("domain") or project.get("domain"))
    category = _compact(source.get("category"))
    domain_tokens = {
        part
        for value in (domain, category)
        for part in value.replace("_", "-").lower().split("-")
        if part
    }
    regulated_domain = bool(domain_tokens & _REGULATED_DOMAINS) or any(
        term in text for term in _REGULATED_DOMAINS
    )

    return {
        "workflow_context": _workflow(project),
        "domain": domain,
        "category": category,
        "regulated_domain": regulated_domain,
        "detected_terms_by_category": _detected_terms_by_category(text),
        "detected_storage_terms": _detected_labels(text, stack, _DATA_STORE_TERMS),
        "detected_transfer_terms": _detected_labels(text, stack, _TRANSFER_TERMS),
        "mentions_retention": _contains_any(text, ("retention", "delete", "deletion", "ttl", "archive")),
        "mentions_exports": _contains_any(text, ("export", "download", "csv", "report")),
        "mentions_logging": _contains_any(text, ("audit", "log", "trace", "monitor", "telemetry")),
        "mentions_external_transfer": _contains_any(
            text, ("api", "integration", "oauth", "openai", "salesforce", "slack", "stripe", "webhook")
        ),
        "execution_risks": [
            _compact(risk) for risk in _list(execution.get("risks")) if _compact(risk)
        ],
    }


def _data_categories(context: dict[str, Any]) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    for category_id, label, _terms, description, sensitivity in _CATEGORY_DEFINITIONS:
        evidence = context["detected_terms_by_category"].get(category_id, [])
        if not evidence:
            continue
        categories.append(
            {
                "id": category_id,
                "label": label,
                "sensitivity": sensitivity,
                "description": description,
                "evidence": evidence,
                "handling_notes": _handling_notes(category_id, sensitivity),
            }
        )

    if not categories:
        categories.append(
            {
                "id": "unspecified_user_or_operational_data",
                "label": "Unspecified user or operational data",
                "sensitivity": "confidential",
                "description": "Sparse specs do not prove that the system avoids user, workflow, or operational data.",
                "evidence": ["project", "problem", "solution"],
                "handling_notes": (
                    "Treat all persisted records and logs as confidential until the implementation names exact fields."
                ),
            }
        )

    return sorted(categories, key=lambda item: (_CATEGORY_ORDER.get(item["id"], 99), item["id"]))


def _overall_sensitivity(categories: list[dict[str, Any]], context: dict[str, Any]) -> str:
    levels = [category["sensitivity"] for category in categories]
    if context["regulated_domain"] or any(level == "restricted" for level in levels):
        return "restricted"
    if any(level == "confidential" for level in levels):
        return "confidential"
    return "internal"


def _sensitivity_rationale(
    sensitivity: str, categories: list[dict[str, Any]], context: dict[str, Any]
) -> str:
    if sensitivity == "restricted":
        if context["regulated_domain"]:
            return "The source domain or narrative indicates regulated handling risk."
        restricted = [item["label"] for item in categories if item["sensitivity"] == "restricted"]
        return f"Restricted categories were detected: {', '.join(restricted)}."
    if sensitivity == "confidential":
        return "The spec references data that could expose users, customers, operations, or integrations."
    return "Only internal operational context was detected."


def _retention_guidance(sensitivity: str, context: dict[str, Any]) -> dict[str, str]:
    if context["mentions_retention"]:
        default = "Use the retention period named by product, legal, or data owners; enforce it in storage and backups."
    elif sensitivity == "restricted":
        default = "Minimize collection and default to the shortest practical retention until owner signoff."
    else:
        default = "Default to 30-90 days for logs and temporary records until product owners approve longer retention."

    return {
        "default_retention": default,
        "deletion_trigger": "Delete or anonymize records when the user, account, test fixture, or workflow is removed.",
        "backup_handling": "Apply the same retention class to backups, exports, queues, caches, and derived analytics.",
        "review_cadence": "Review retention before production launch and whenever data categories or integrations change.",
    }


def _compliance_considerations(
    context: dict[str, Any], categories: list[dict[str, Any]]
) -> list[str]:
    considerations = [
        "Record data purpose, owner, and allowed environments before implementation starts.",
    ]
    category_ids = {item["id"] for item in categories}
    if context["regulated_domain"] or "regulated_personal_data" in category_ids:
        considerations.append("Route regulated or sensitive personal data assumptions to privacy, legal, or compliance owners.")
    if "payment_or_financial_data" in category_ids:
        considerations.append("Confirm payment and financial data boundaries before storing or transmitting billing records.")
    if "authentication_and_secrets" in category_ids:
        considerations.append("Classify credentials and tokens as secrets; exclude them from logs, analytics, and exports.")
    if context["mentions_external_transfer"]:
        considerations.append("Document vendor subprocessors, scopes, regions, retry behavior, and webhook verification.")
    if "ai_inputs_and_outputs" in category_ids:
        considerations.append("Define AI provider data-use constraints, prompt redaction, and generated-output review requirements.")
    return _dedupe(considerations)


def _risk_notes(categories: list[dict[str, Any]], context: dict[str, Any]) -> list[str]:
    notes = []
    if any(item["id"] == "unspecified_user_or_operational_data" for item in categories):
        notes.append("Sparse input means data minimization, field inventory, and retention are unresolved.")
    if context["regulated_domain"]:
        notes.append("Regulated-domain language raises the default sensitivity until reviewed.")
    if context["mentions_exports"]:
        notes.append("Exports and reports can bypass application access controls unless scoped and audited.")
    if context["mentions_logging"]:
        notes.append("Logs, traces, and audit events can duplicate sensitive data and need redaction rules.")
    if context["mentions_external_transfer"]:
        notes.append("External integrations and APIs create cross-system transfer and vendor review obligations.")
    for risk in context["execution_risks"]:
        notes.append(f"Execution risk: {risk}")
    return _dedupe(notes) or ["No explicit risk notes were provided; keep conservative handling until fields are known."]


def _storage_touchpoints(context: dict[str, Any]) -> list[dict[str, Any]]:
    labels = context["detected_storage_terms"] or ["Persistence boundary"]
    touchpoints = [
        {
            "id": f"STORE{index:02d}",
            "name": label,
            "risk_level": "high" if context["regulated_domain"] else "medium",
            "guidance": "Define stored fields, encryption, backup retention, access owner, and deletion behavior.",
        }
        for index, label in enumerate(labels, start=1)
    ]
    return touchpoints


def _transfer_touchpoints(context: dict[str, Any]) -> list[dict[str, Any]]:
    labels = context["detected_transfer_terms"]
    if not labels and context["mentions_external_transfer"]:
        labels = ["External integration"]
    touchpoints = [
        {
            "id": f"XFER{index:02d}",
            "name": label,
            "risk_level": "high" if context["regulated_domain"] else "medium",
            "guidance": "Document payload fields, scopes, authentication, retry policy, and audit evidence.",
        }
        for index, label in enumerate(labels, start=1)
    ]
    return touchpoints


def _safeguards(
    categories: list[dict[str, Any]],
    sensitivity: str,
    context: dict[str, Any],
    storage: list[dict[str, Any]],
    transfer: list[dict[str, Any]],
) -> list[dict[str, str]]:
    requirements = [
        ("data_owner", "Maintain a field inventory with purpose, sensitivity, source, owner, and retention class."),
        ("engineering_owner", "Minimize collection and avoid persisting fields that are not needed for the MVP workflow."),
        ("engineering_owner", "Redact sensitive values from logs, analytics, traces, test fixtures, and error reports."),
    ]
    if sensitivity == "restricted":
        requirements.append(
            ("security_owner", "Require encryption, access review, and explicit production-data approval before launch.")
        )
    if storage:
        requirements.append(
            ("platform_owner", "Apply deletion, backup, restore, and migration behavior consistently across storage layers.")
        )
    if transfer:
        requirements.append(
            ("integration_owner", "Validate external payloads, scopes, webhook signatures, retries, and vendor data handling.")
        )
    if context["mentions_logging"]:
        requirements.append(("security_owner", "Add audit logging that records access without copying sensitive payloads."))
    if any(item["id"] == "ai_inputs_and_outputs" for item in categories):
        requirements.append(
            ("policy_owner", "Review prompt, embedding, and generated-output handling before using production data.")
        )
    return [
        {"id": f"DATA-SG{index:02d}", "owner": owner, "requirement": requirement}
        for index, (owner, requirement) in enumerate(_dedupe_pairs(requirements), start=1)
    ]


def _csv_rows(classification: dict[str, Any]) -> list[dict[str, str]]:
    summary = classification.get("summary") if isinstance(classification.get("summary"), dict) else {}
    sensitivity = (
        classification.get("sensitivity")
        if isinstance(classification.get("sensitivity"), dict)
        else {}
    )
    rows: list[dict[str, str]] = [
        _csv_row(
            classification,
            section="summary",
            row_type="summary",
            item_id="summary",
            item_name=summary.get("title"),
            classification=summary.get("sensitivity_level"),
            sensitivity=summary.get("sensitivity_level"),
            source_context=classification.get("schema_version"),
            description=sensitivity.get("rationale"),
        )
    ]

    for category in _dict_items(classification.get("data_categories")):
        rows.append(
            _csv_row(
                classification,
                section="data_categories",
                row_type="data_category",
                item_id=category.get("id"),
                item_name=category.get("label"),
                classification=category.get("label"),
                sensitivity=category.get("sensitivity"),
                data_category=category.get("id"),
                handling_requirement=category.get("handling_notes"),
                evidence=category.get("evidence"),
                source_context="classification_context.detected_terms_by_category",
                description=category.get("description"),
            )
        )

    retention = (
        classification.get("retention_guidance")
        if isinstance(classification.get("retention_guidance"), dict)
        else {}
    )
    for item_id, item_name in (
        ("default_retention", "Default retention"),
        ("deletion_trigger", "Deletion trigger"),
        ("backup_handling", "Backup handling"),
        ("review_cadence", "Review cadence"),
    ):
        if item_id not in retention:
            continue
        rows.append(
            _csv_row(
                classification,
                section="retention_guidance",
                row_type="handling_requirement",
                item_id=item_id,
                item_name=item_name,
                classification="retention",
                sensitivity=summary.get("sensitivity_level"),
                handling_requirement=retention.get(item_id),
                source_context="retention_guidance",
            )
        )

    for item in _dict_items(classification.get("storage_touchpoints")):
        rows.append(
            _csv_row(
                classification,
                section="storage_touchpoints",
                row_type="storage_touchpoint",
                item_id=item.get("id"),
                item_name=item.get("name"),
                classification="storage",
                sensitivity=summary.get("sensitivity_level"),
                risk_level=item.get("risk_level"),
                guidance=item.get("guidance"),
                source_context="classification_context.detected_storage_terms",
            )
        )

    for item in _dict_items(classification.get("transfer_touchpoints")):
        rows.append(
            _csv_row(
                classification,
                section="transfer_touchpoints",
                row_type="transfer_touchpoint",
                item_id=item.get("id"),
                item_name=item.get("name"),
                classification="transfer",
                sensitivity=summary.get("sensitivity_level"),
                risk_level=item.get("risk_level"),
                guidance=item.get("guidance"),
                source_context="classification_context.detected_transfer_terms",
            )
        )

    for index, item in enumerate(_list(classification.get("compliance_considerations")), start=1):
        rows.append(
            _csv_row(
                classification,
                section="compliance_considerations",
                row_type="handling_requirement",
                item_id=f"COMPLIANCE{index:02d}",
                item_name="Compliance consideration",
                classification="compliance",
                sensitivity=summary.get("sensitivity_level"),
                handling_requirement=item,
                source_context="compliance_considerations",
            )
        )

    for index, item in enumerate(_list(classification.get("risk_notes")), start=1):
        rows.append(
            _csv_row(
                classification,
                section="risk_notes",
                row_type="risk_note",
                item_id=f"RISK{index:02d}",
                item_name="Risk note",
                classification="risk",
                sensitivity=summary.get("sensitivity_level"),
                source_context="risk_notes",
                description=item,
            )
        )

    for item in _dict_items(classification.get("implementation_safeguards")):
        rows.append(
            _csv_row(
                classification,
                section="implementation_safeguards",
                row_type="control",
                item_id=item.get("id"),
                item_name=item.get("id"),
                classification="safeguard",
                sensitivity=summary.get("sensitivity_level"),
                handling_requirement=item.get("requirement"),
                owner=item.get("owner"),
                control=item.get("id"),
                source_context="implementation_safeguards",
            )
        )

    return rows


def _csv_row(artifact: dict[str, Any], **values: Any) -> dict[str, str]:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    row = {
        "source_idea_id": source.get("idea_id"),
        "source_status": source.get("status"),
        "source_domain": source.get("domain"),
        "source_category": source.get("category"),
        "tact_spec_schema_version": source.get("tact_spec_schema_version"),
        "title": summary.get("title"),
        "workflow_context": summary.get("workflow_context"),
        "target_user": summary.get("target_user"),
        "sensitivity_level": summary.get("sensitivity_level"),
        **values,
    }
    return {column: _csv_text(row.get(column)) for column in DATA_CLASSIFICATION_CSV_COLUMNS}


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
    return _compact(value)


def _handling_notes(category_id: str, sensitivity: str) -> str:
    if category_id == "authentication_and_secrets":
        return "Store in secret-managed locations only; redact from logs and exports."
    if category_id == "ai_inputs_and_outputs":
        return "Keep prompts and outputs inside approved providers and review redaction before model calls."
    if sensitivity == "restricted":
        return "Require owner approval, least-privilege access, encryption, and documented deletion paths."
    return "Limit access by role, redact unnecessary fields, and include the category in retention review."


def _detected_terms_by_category(text: str) -> dict[str, list[str]]:
    return {
        category_id: [_term_label(term) for term in terms if term in text]
        for category_id, _label, terms, _description, _sensitivity in _CATEGORY_DEFINITIONS
    }


def _detected_labels(text: str, stack: Any, labels: dict[str, str]) -> list[str]:
    detected = [label for term, label in sorted(labels.items()) if term in text]
    if isinstance(stack, dict):
        for key, value in sorted(stack.items()):
            detected.extend(_labels_for_value(str(key).lower(), labels))
            detected.extend(_labels_for_value(str(value).lower(), labels))
    return _dedupe(detected)


def _labels_for_value(value: str, labels: dict[str, str]) -> list[str]:
    return [label for term, label in sorted(labels.items()) if term in value]


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
        "api key": "API key",
        "crm": "CRM",
        "gdpr": "GDPR",
        "hipaa": "HIPAA",
        "llm": "LLM",
        "oauth": "OAuth",
        "pii": "PII",
    }
    return labels.get(term, term)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _dedupe_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for owner, requirement in values:
        key = (_compact(owner), _compact(requirement))
        if key[0] and key[1] and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _bullets(items: list[Any], *, empty: str | None = None) -> list[str]:
    values = [f"- {_text(item)}" for item in items if _text(item)]
    if values:
        return values
    return [empty] if empty else []


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
