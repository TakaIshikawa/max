"""Generate deterministic data retention schedules for buildable specs."""

from __future__ import annotations

from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


DATA_RETENTION_SCHEDULE_SCHEMA_VERSION = "max-data-retention-schedule/v1"

_CATEGORY_DEFINITIONS = (
    (
        "customer_identifiers",
        "Customer and user identifiers",
        ("email", "name", "phone", "address", "contact", "customer", "user", "profile", "pii"),
        "Information that identifies a customer, user, account contact, or workflow participant.",
        "Deliver the core workflow and support account-level communication.",
        "active account plus 90 days",
        "Account closure, user deletion request, or pilot end.",
        "product_owner",
        "Personal identifiers should be retained only while needed for the active relationship and short support tail.",
    ),
    (
        "regulated_sensitive_records",
        "Regulated or sensitive records",
        (
            "children",
            "consent",
            "education",
            "financial",
            "gdpr",
            "health",
            "healthcare",
            "hipaa",
            "medical",
            "patient",
            "payment",
            "student",
        ),
        "Health, financial, education, child, consent, or other regulated personal data.",
        "Support the named regulated workflow only after privacy or legal review.",
        "shortest approved legal/privacy period",
        "Purpose completion, consent withdrawal, contract termination, or legal/privacy owner instruction.",
        "privacy_owner",
        "Regulated data requires documented legal basis, data minimization, and owner-approved retention limits.",
    ),
    (
        "workflow_records",
        "Workflow and account records",
        ("account", "case", "crm", "document", "message", "record", "renewal", "ticket", "workflow"),
        "Operational records created while users complete the product workflow.",
        "Provide continuity, support, auditability, and customer-visible history.",
        "active workspace plus 1 year",
        "Workspace deletion, contract end, or explicit customer deletion request.",
        "data_owner",
        "Operational records need a bounded support and audit window tied to customer purpose.",
    ),
    (
        "billing_and_payment_records",
        "Billing and payment records",
        ("billing", "card", "charge", "invoice", "payment", "stripe", "subscription", "tax"),
        "Payment, invoice, subscription, tax, or billing administration data.",
        "Process transactions, reconcile invoices, and meet finance obligations.",
        "7 years unless finance/legal approves a shorter period",
        "Finance record retention expiry, account closure, or processor deletion event.",
        "finance_owner",
        "Financial records may need statutory retention while sensitive payment fields stay in approved processors.",
    ),
    (
        "authentication_and_access",
        "Authentication and access data",
        ("api key", "credential", "login", "oauth", "password", "permission", "role", "secret", "sso", "token"),
        "Credentials, tokens, roles, permissions, and access-control metadata.",
        "Authenticate users and protect the service from unauthorized access.",
        "until revoked plus 30 days for audit metadata",
        "Credential rotation, access revocation, employee departure, or account deletion.",
        "security_owner",
        "Secrets and access metadata should be minimized, rotated, and excluded from analytics, exports, and logs.",
    ),
    (
        "logs_and_telemetry",
        "Logs, audit events, and telemetry",
        ("analytics", "audit", "event", "log", "metric", "monitor", "telemetry", "trace", "usage"),
        "Operational logs, audit trails, analytics events, metrics, traces, and diagnostics.",
        "Operate, secure, debug, and measure the workflow during validation and launch.",
        "30-90 days",
        "Retention timer expiry, incident closure, or environment teardown.",
        "engineering_owner",
        "Operational telemetry often duplicates sensitive fields and should be short-lived unless audit needs are documented.",
    ),
    (
        "ai_inputs_outputs",
        "AI inputs, prompts, outputs, and embeddings",
        ("ai", "embedding", "generated", "llm", "model", "openai", "prompt", "summary"),
        "Prompts, model inputs, generated outputs, summaries, embeddings, and AI-derived artifacts.",
        "Generate, summarize, rank, or transform workflow content for the stated product purpose.",
        "pilot data: 30 days; approved production outputs: active account plus 90 days",
        "Output regeneration, prompt deletion, model-provider deletion request, or account deletion.",
        "policy_owner",
        "AI-derived data may preserve source content and needs provider terms, redaction, and deletion behavior recorded.",
    ),
    (
        "exports_and_reports",
        "Exports and reports",
        ("csv", "download", "export", "report", "spreadsheet"),
        "Downloaded reports, exports, spreadsheets, and generated customer-facing files.",
        "Support review, sharing, customer handoff, and validation evidence.",
        "30 days for generated exports unless customer contract requires otherwise",
        "Export expiry, workspace deletion, customer request, or replacement by newer report.",
        "data_owner",
        "Exports can leave product access controls and need explicit expiry and access tracking.",
    ),
)

_CATEGORY_ORDER = {category_id: index for index, (category_id, *_rest) in enumerate(_CATEGORY_DEFINITIONS)}

_EXTERNAL_TRANSFER_TERMS = (
    "api",
    "github",
    "hubspot",
    "integration",
    "openai",
    "salesforce",
    "slack",
    "stripe",
    "third-party",
    "twilio",
    "vendor",
    "webhook",
)


def generate_data_retention_schedule(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn a buildable idea into deterministic retention guidance."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}

    context = _retention_context(unit, evaluation, spec, source, project, solution, execution, evidence)
    categories = _data_categories(context)
    retention_rules = _retention_rules(categories, context)
    deletion_triggers = _deletion_triggers(retention_rules, context)
    owners = _owners(retention_rules)
    gaps = _gaps(unit, evaluation, spec, project, execution, context)

    return {
        "schema_version": DATA_RETENTION_SCHEDULE_SCHEMA_VERSION,
        "kind": "max.spec.data_retention_schedule",
        "idea_id": unit.id,
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "idea",
            "idea_id": source.get("idea_id") or unit.id,
            "status": source.get("status") or unit.status,
            "domain": source.get("domain") or unit.domain,
            "category": str(source.get("category") or unit.category),
            "evaluation_available": evaluation is not None,
            "tact_spec_available": bool(spec),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(context["evidence_refs"]),
        },
        "summary": {
            "title": context["title"],
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "retention_gate": _retention_gate(retention_rules, gaps, context),
            "data_category_count": len(categories),
            "retention_rule_count": len(retention_rules),
            "gap_count": len(gaps),
            "next_action_count": len(_next_actions(gaps, retention_rules, context)),
        },
        "retention_context": context,
        "data_categories": categories,
        "retention_rules": retention_rules,
        "deletion_triggers": deletion_triggers,
        "owners": owners,
        "gaps": gaps,
        "missing_inputs": [gap["missing_input"] for gap in gaps],
        "next_actions": _next_actions(gaps, retention_rules, context),
    }


def render_data_retention_schedule_markdown(
    schedule: dict[str, Any], output_format: str = "markdown"
) -> str:
    """Render a generated data retention schedule as deterministic Markdown."""
    if output_format != "markdown":
        raise ValueError(f"Unsupported data retention schedule render format: {output_format}")

    summary = schedule.get("summary", {})
    source = schedule.get("source", {})
    title = _text(summary.get("title")) or _text(schedule.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Data Retention Schedule",
        "",
        f"- Schema version: {_text(schedule.get('schema_version'))}",
        f"- Idea ID: {_text(schedule.get('idea_id'))}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Category: {_text(source.get('category')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Evaluation available: {_text(source.get('evaluation_available'))}",
        f"- Evidence references: {_text(source.get('evidence_reference_count'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Retention gate: {_text(summary.get('retention_gate'))}",
        "",
    ]

    _extend_section(lines, "Data Categories", schedule.get("data_categories") or [], _render_category)
    _extend_section(lines, "Retention Rules", schedule.get("retention_rules") or [], _render_rule)
    _extend_section(lines, "Deletion Triggers", schedule.get("deletion_triggers") or [], _render_trigger)
    _extend_section(lines, "Owners", schedule.get("owners") or [], _render_owner)
    _extend_section(
        lines,
        "Missing Input Notes",
        schedule.get("gaps") or [],
        _render_gap,
        empty="No missing retention inputs detected.",
    )
    _extend_section(lines, "Next Actions", schedule.get("next_actions") or [], _render_action)
    return "\n".join(lines).rstrip() + "\n"


def _retention_context(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
    source: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    text = _haystack(
        {
            "unit": unit.model_dump(mode="json"),
            "spec": spec,
        }
    )
    workflow = (
        _compact(project.get("workflow_context") or unit.workflow_context)
        or f"{unit.title} workflow"
    )
    evidence_refs = _evidence_refs(unit, evidence)
    return {
        "title": _compact(project.get("title") or unit.title) or "Untitled idea",
        "target_user": _compact(project.get("specific_user") or unit.specific_user or project.get("target_users") or unit.target_users)
        or "primary user",
        "buyer": _compact(project.get("buyer") or unit.buyer) or "launch sponsor",
        "workflow_context": workflow,
        "primary_scope": _first_string(execution.get("mvp_scope")) or unit.solution or f"first usable {workflow}",
        "value_proposition": _compact(project.get("value_proposition") or unit.value_proposition)
        or "validated customer value",
        "validation_plan": _compact(execution.get("validation_plan") or unit.validation_plan),
        "detected_terms_by_category": _detected_terms_by_category(text),
        "mentions_retention": _contains_any(text, ("retention", "retain", "ttl", "delete", "deletion", "archive", "purge")),
        "mentions_privacy": _contains_any(text, ("privacy", "gdpr", "hipaa", "consent", "personal data", "pii")),
        "mentions_external_transfer": _contains_any(text, _EXTERNAL_TRANSFER_TERMS),
        "mentions_backups": _contains_any(text, ("backup", "restore", "snapshot")),
        "mentions_exports": _contains_any(text, ("export", "download", "csv", "report", "spreadsheet")),
        "mentions_logging": _contains_any(text, ("audit", "log", "trace", "monitor", "telemetry")),
        "domain_risks": [_compact(risk) for risk in unit.domain_risks if _compact(risk)],
        "execution_risks": [
            _compact(risk) for risk in _list(execution.get("risks")) if _compact(risk)
        ],
        "evidence_refs": evidence_refs,
        "evaluation_recommendation": evaluation.recommendation if evaluation else None,
        "overall_score": evaluation.overall_score if evaluation else None,
    }


def _data_categories(context: dict[str, Any]) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    for (
        category_id,
        label,
        _terms,
        description,
        purpose,
        _period,
        _trigger,
        owner,
        rationale,
    ) in _CATEGORY_DEFINITIONS:
        evidence = context["detected_terms_by_category"].get(category_id, [])
        if not evidence:
            continue
        categories.append(
            {
                "id": category_id,
                "label": label,
                "description": description,
                "purpose": purpose,
                "owner": owner,
                "legal_privacy_rationale": rationale,
                "evidence_refs": _evidence(evidence, *context["evidence_refs"]),
            }
        )

    if not categories:
        categories.append(
            {
                "id": "unspecified_product_data",
                "label": "Unspecified product, user, or operational data",
                "description": "Sparse specs do not prove that the product avoids retained user, workflow, or operational records.",
                "purpose": f"Operate and validate {context['workflow_context']} while the field inventory is completed.",
                "owner": "data_owner",
                "legal_privacy_rationale": "Unknown fields require conservative minimization and a short default retention window.",
                "evidence_refs": _evidence(context["evidence_refs"], "unit.problem", "unit.solution"),
            }
        )

    return sorted(categories, key=lambda item: (_CATEGORY_ORDER.get(item["id"], 99), item["id"]))


def _retention_rules(
    categories: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    definition_by_id = {
        item[0]: item
        for item in _CATEGORY_DEFINITIONS
    }
    for index, category in enumerate(categories, start=1):
        definition = definition_by_id.get(category["id"])
        if definition:
            period = definition[5]
            trigger = definition[6]
        else:
            period = "30-90 days until the data owner approves a field-level schedule"
            trigger = "Pilot end, account deletion, workflow deletion, or owner-approved retention timer expiry."
        rules.append(
            {
                "id": f"RET{index:02d}",
                "data_category_id": category["id"],
                "data_category": category["label"],
                "purpose": category["purpose"],
                "retention_period": period,
                "deletion_trigger": trigger,
                "owner": category["owner"],
                "legal_privacy_rationale": category["legal_privacy_rationale"],
                "evidence_refs": category["evidence_refs"],
            }
        )

    rules.append(
        {
            "id": f"RET{len(rules) + 1:02d}",
            "data_category_id": "backups_caches_and_derived_copies",
            "data_category": "Backups, caches, queues, and derived copies",
            "purpose": "Keep recovery, processing, and derived artifacts aligned with primary retention rules.",
            "retention_period": "match the source record retention class; purge temporary copies within 30 days",
            "deletion_trigger": "Source record deletion, restore-window expiry, cache TTL expiry, or queue processing completion.",
            "owner": "platform_owner",
            "legal_privacy_rationale": "Secondary copies can preserve deleted data unless retention is enforced across storage boundaries.",
            "evidence_refs": _evidence(context["evidence_refs"], "solution.suggested_stack", "solution.technical_approach"),
        }
    )
    if context["mentions_external_transfer"]:
        rules.append(
            {
                "id": f"RET{len(rules) + 1:02d}",
                "data_category_id": "third_party_transfers",
                "data_category": "Third-party transfer copies",
                "purpose": "Operate approved integrations while keeping vendor copies within customer and privacy commitments.",
                "retention_period": "vendor contract period or shorter product retention period, whichever is stricter",
                "deletion_trigger": "Integration disconnect, customer deletion request, contract end, or subprocessor deletion workflow.",
                "owner": "integration_owner",
                "legal_privacy_rationale": "Transferred data must be deletable or contractually controlled outside the product boundary.",
                "evidence_refs": _evidence(context["evidence_refs"], "solution.suggested_stack", "solution.composability_notes"),
            }
        )
    return rules


def _deletion_triggers(
    retention_rules: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    triggers = [
        {
            "id": "DEL01",
            "name": "retention_timer_expired",
            "description": "Delete, anonymize, or tombstone records when the approved retention period expires.",
            "owner": "data_owner",
            "applies_to_rule_ids": [rule["id"] for rule in retention_rules],
        },
        {
            "id": "DEL02",
            "name": "account_or_workspace_deleted",
            "description": "Cascade deletion to workflow records, exports, logs, backups, caches, and derived outputs when the account boundary is removed.",
            "owner": "engineering_owner",
            "applies_to_rule_ids": [rule["id"] for rule in retention_rules if rule["owner"] != "finance_owner"],
        },
        {
            "id": "DEL03",
            "name": "pilot_or_validation_ended",
            "description": f"Review and purge validation data after {context['workflow_context']} pilot evidence is accepted or rejected.",
            "owner": "product_owner",
            "applies_to_rule_ids": [rule["id"] for rule in retention_rules],
        },
    ]
    if context["mentions_privacy"]:
        triggers.append(
            {
                "id": "DEL04",
                "name": "privacy_or_consent_request",
                "description": "Honor deletion, withdrawal, or data subject requests within the approved privacy workflow.",
                "owner": "privacy_owner",
                "applies_to_rule_ids": [rule["id"] for rule in retention_rules],
            }
        )
    if context["mentions_external_transfer"]:
        triggers.append(
            {
                "id": f"DEL{len(triggers) + 1:02d}",
                "name": "integration_disconnected",
                "description": "Delete synced payloads and request vendor-side deletion when an integration is disconnected.",
                "owner": "integration_owner",
                "applies_to_rule_ids": [
                    rule["id"]
                    for rule in retention_rules
                    if rule["owner"] in {"integration_owner", "data_owner", "privacy_owner"}
                ],
            }
        )
    return triggers


def _owners(retention_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for rule in retention_rules:
        grouped.setdefault(rule["owner"], []).append(rule["id"])
    return [
        {
            "owner": owner,
            "rule_ids": rule_ids,
            "responsibility": _owner_responsibility(owner),
        }
        for owner, rule_ids in sorted(grouped.items())
    ]


def _gaps(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
    project: dict[str, Any],
    execution: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps = []
    if evaluation is None:
        gaps.append(_gap("GAP01", "missing_evaluation", "Utility evaluation is missing; retention priority cannot use risk/recommendation confidence.", "evaluation"))
    if not spec:
        gaps.append(_gap("GAP02", "missing_tact_spec", "TactSpec preview is missing; retention evidence is limited to BuildableUnit fields.", "tact_spec"))
    if not _compact(project.get("workflow_context") or unit.workflow_context):
        gaps.append(_gap("GAP03", "missing_workflow_context", "Workflow context is missing; retention purpose and trigger wording may be too generic.", "workflow_context"))
    if not context["mentions_retention"]:
        gaps.append(_gap("GAP04", "missing_explicit_retention", "Source inputs do not name retention periods, TTLs, deletion behavior, or archive rules.", "retention_policy"))
    if not context["evidence_refs"]:
        gaps.append(_gap("GAP05", "missing_evidence_refs", "No signal, insight, source idea, or evidence references are attached to the idea.", "evidence_refs"))
    if not _compact(execution.get("validation_plan") or unit.validation_plan):
        gaps.append(_gap("GAP06", "missing_validation_plan", "Validation plan is missing; pilot-data purge timing needs owner confirmation.", "validation_plan"))
    return gaps


def _next_actions(
    gaps: list[dict[str, Any]], retention_rules: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    actions = []
    if gaps:
        actions.append(
            {
                "id": "NA0",
                "owner": "product_owner",
                "action": "Resolve or explicitly accept missing retention inputs before launch review.",
                "evidence_refs": [gap["id"] for gap in gaps],
            }
        )
    actions.extend(
        [
            {
                "id": f"NA{len(actions) + 1}",
                "owner": "data_owner",
                "action": "Convert each retention rule into field-level storage, deletion, archive, and backup requirements.",
                "evidence_refs": [rule["id"] for rule in retention_rules],
            },
            {
                "id": f"NA{len(actions) + 2}",
                "owner": "engineering_owner",
                "action": "Implement deletion jobs, cache TTLs, export expiry, and deletion audit evidence before pilot data is loaded.",
                "evidence_refs": [rule["id"] for rule in retention_rules],
            },
            {
                "id": f"NA{len(actions) + 3}",
                "owner": "privacy_owner",
                "action": "Approve legal/privacy rationale for personal, regulated, exported, transferred, and AI-derived data.",
                "evidence_refs": [rule["id"] for rule in retention_rules if rule["owner"] in {"privacy_owner", "policy_owner", "integration_owner"}] or context["evidence_refs"],
            },
        ]
    )
    if context["mentions_external_transfer"]:
        actions.append(
            {
                "id": f"NA{len(actions) + 1}",
                "owner": "integration_owner",
                "action": "Record vendor retention, deletion, region, retry, and subprocessor commitments for each integration.",
                "evidence_refs": ["solution.suggested_stack", "solution.composability_notes"],
            }
        )
    return actions


def _retention_gate(
    retention_rules: list[dict[str, Any]], gaps: list[dict[str, Any]], context: dict[str, Any]
) -> str:
    rule_owner_ids = {rule["owner"] for rule in retention_rules}
    if "privacy_owner" in rule_owner_ids or context["mentions_privacy"]:
        return "privacy_review_required"
    if gaps:
        return "retention_inputs_required"
    return "ready_with_owner_approval"


def _gap(gap_id: str, category: str, note: str, missing_input: str) -> dict[str, str]:
    return {
        "id": gap_id,
        "category": category,
        "missing_input": missing_input,
        "note": note,
        "owner": "product_owner",
    }


def _owner_responsibility(owner: str) -> str:
    responsibilities = {
        "data_owner": "Own field inventory, purpose limits, retention periods, deletion evidence, and customer-facing commitments.",
        "engineering_owner": "Build and monitor deletion, anonymization, TTL, export expiry, and log-redaction paths.",
        "finance_owner": "Confirm finance, tax, invoicing, and processor retention requirements.",
        "integration_owner": "Confirm vendor, subprocessor, regional, retry, and downstream deletion behavior.",
        "platform_owner": "Apply retention to backups, restores, caches, queues, migrations, and derived storage.",
        "policy_owner": "Approve AI provider, prompt, embedding, generated-output, and model-data handling rules.",
        "privacy_owner": "Approve legal basis, consent, privacy rights, minimization, and regulated-data retention.",
        "product_owner": "Accept retention tradeoffs and close launch-blocking missing inputs.",
        "security_owner": "Approve access metadata, credential rotation, secret handling, and audit-retention controls.",
    }
    return responsibilities.get(owner, "Own retention decisions and evidence for assigned data categories.")


def _render_category(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('label'))}",
        "",
        f"- Purpose: {_text(item.get('purpose'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Legal/privacy rationale: {_text(item.get('legal_privacy_rationale'))}",
        f"- Evidence: {_inline_list(item.get('evidence_refs') or [])}",
    ]


def _render_rule(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('data_category'))}",
        "",
        f"- Purpose: {_text(item.get('purpose'))}",
        f"- Retention period: {_text(item.get('retention_period'))}",
        f"- Deletion trigger: {_text(item.get('deletion_trigger'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Legal/privacy rationale: {_text(item.get('legal_privacy_rationale'))}",
        f"- Evidence: {_inline_list(item.get('evidence_refs') or [])}",
    ]


def _render_trigger(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Applies to: {_inline_list(item.get('applies_to_rule_ids') or [])}",
    ]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('owner'))}",
        "",
        f"- Rule IDs: {_inline_list(item.get('rule_ids') or [])}",
        f"- Responsibility: {_text(item.get('responsibility'))}",
    ]


def _render_gap(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category'))}",
        "",
        f"- Missing input: {_text(item.get('missing_input'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Note: {_text(item.get('note'))}",
    ]


def _render_action(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('owner'))}",
        "",
        f"- Action: {_text(item.get('action'))}",
        f"- Evidence: {_inline_list(item.get('evidence_refs') or [])}",
    ]


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    renderer,
    empty: str = "None.",
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend([empty, ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _detected_terms_by_category(text: str) -> dict[str, list[str]]:
    return {
        category_id: [_term_label(term) for term in terms if term in text]
        for category_id, _label, terms, *_rest in _CATEGORY_DEFINITIONS
    }


def _evidence_refs(unit: BuildableUnit, evidence: dict[str, Any]) -> list[str]:
    refs = []
    refs.extend(f"signal:{item}" for item in _list(evidence.get("signal_ids") or unit.evidence_signals))
    refs.extend(f"insight:{item}" for item in _list(evidence.get("insight_ids") or unit.inspiring_insights))
    refs.extend(f"source_idea:{item}" for item in _list(evidence.get("source_idea_ids") or unit.source_idea_ids))
    rationale = _compact(evidence.get("rationale") or unit.evidence_rationale)
    if rationale:
        refs.append("evidence.rationale")
    return _dedupe(refs)


def _evidence(items: list[str], *fallback: str) -> list[str]:
    return _dedupe([_compact(item) for item in [*items, *fallback] if _compact(item)])


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


def _first_string(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            compacted = _compact(item)
            if compacted:
                return compacted
        return ""
    return _compact(value)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _inline_list(items: list[Any]) -> str:
    compacted = [_text(item) for item in items if _text(item)]
    return ", ".join(compacted) if compacted else "none"


def _term_label(term: str) -> str:
    return term.replace("_", " ")


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
