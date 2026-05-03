"""Deterministic partner integration checklists for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.partner_integration_checklist"
SCHEMA_VERSION = "max.design_brief.partner_integration_checklist.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "kind",
    "design_brief_id",
    "design_brief_title",
    "section",
    "row_type",
    "item_id",
    "item_name",
    "target_id",
    "target_name",
    "target_type",
    "sequence",
    "owner",
    "priority",
    "severity",
    "producer",
    "consumer",
    "payload",
    "required_fields",
    "check",
    "question",
    "warning",
    "validation_action",
    "handoff",
    "recommended_action",
    "source_idea_ids",
    "source_reference_ids",
    "details",
)

_KNOWN_SYSTEMS: tuple[tuple[str, str, str, str, str], ...] = (
    ("salesforce_crm", "Salesforce CRM", "crm", "CRM partner", "salesforce"),
    ("hubspot_crm", "HubSpot CRM", "crm", "CRM partner", "hubspot"),
    ("slack", "Slack", "collaboration", "Product operations", "slack"),
    ("microsoft_teams", "Microsoft Teams", "collaboration", "Product operations", "teams"),
    ("stripe", "Stripe", "billing", "Finance operations", "stripe"),
    ("github", "GitHub", "developer_platform", "Engineering owner", "github"),
    ("linear", "Linear", "project_system", "Product operations", "linear"),
    ("jira", "Jira", "project_system", "Product operations", "jira"),
    ("google_calendar", "Google Calendar", "calendar", "Customer operations", "calendar"),
    ("snowflake", "Snowflake", "data_warehouse", "Data platform", "snowflake"),
    ("bigquery", "BigQuery", "data_warehouse", "Data platform", "bigquery"),
    ("postgres", "Postgres", "database", "Engineering owner", "postgres"),
    ("oauth_sso", "OAuth or SSO provider", "identity", "Security owner", "oauth"),
    ("webhook_api", "Webhook or partner API", "api", "Engineering owner", "webhook"),
)


def build_design_brief_partner_integration_checklist(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a partner integration checklist from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    context = _integration_context(design_brief, source_ideas, lead_idea)
    evidence = _evidence_references(design_brief, source_ideas)
    evidence_ids = [reference["id"] for reference in evidence]
    targets = _integration_targets(context, source_ideas, source_idea_ids, evidence_ids)
    data_contracts = _data_contracts(context, targets, source_idea_ids, evidence_ids)
    security_checks = _auth_and_security_checks(context, targets, source_idea_ids, evidence_ids)
    operational = _operational_readiness(context, targets, source_idea_ids, evidence_ids)
    owner_matrix = _partner_owner_matrix(targets, data_contracts, security_checks, operational)
    sequencing = _sequencing(context, targets, source_idea_ids, evidence_ids)
    questions = _open_questions(context, targets, evidence_ids)
    warnings = _readiness_warnings(design_brief, context, targets, evidence)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
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
            "integration_goal": (
                f"Confirm partner and system readiness for {design_brief['title']} "
                f"before implementation handoff."
            ),
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "primary_scope": context["primary_scope"],
            "fallbacks_used": context["fallbacks_used"],
            "integration_target_count": len(targets),
            "checklist_item_count": len(data_contracts) + len(security_checks) + len(operational),
            "readiness_warning_count": len(warnings),
        },
        "integration_targets": targets,
        "data_contracts": data_contracts,
        "auth_and_security_checks": security_checks,
        "operational_readiness": operational,
        "partner_owner_matrix": owner_matrix,
        "sequencing": sequencing,
        "open_questions": questions,
        "evidence_references": evidence,
        "readiness_warnings": warnings,
        "source_ideas": source_ideas,
    }


def render_design_brief_partner_integration_checklist(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    """Render a partner integration checklist as JSON, CSV, or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_partner_integration_checklist_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported partner integration checklist format: {fmt}")

    brief = report.get("design_brief") or {}
    summary = report.get("summary") or {}
    title = _first_text(brief.get("title"), "Untitled design brief")
    brief_id = _first_text(brief.get("id"), "design-brief")
    lines = [
        f"# Partner Integration Checklist: {title}",
        "",
        f"Schema: `{report.get('schema_version') or SCHEMA_VERSION}`",
        f"Design brief: `{brief_id}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Integration Context",
        "",
        f"- Goal: {_first_text(summary.get('integration_goal'), f'Confirm partner and system readiness for {title}.')}",
        f"- Target user: {_first_text(summary.get('target_user'), 'TBD target user')}",
        f"- Buyer: {_first_text(summary.get('buyer'), 'TBD buyer owner')}",
        f"- Workflow: {_first_text(summary.get('workflow_context'), 'TBD integration workflow')}",
        f"- Primary scope: {_first_text(summary.get('primary_scope'), 'TBD integration scope')}",
        f"- Fallbacks used: {', '.join(_string_list(summary.get('fallbacks_used'))) or 'none'}",
        "",
        "## Integration Targets",
        "",
    ]

    targets = list(report.get("integration_targets") or [])
    if not targets:
        lines.extend(
            [
                "- No partner systems identified yet. Name the owned application and external system of record before implementation handoff.",
                "",
            ]
        )
    for target in targets:
        lines.extend(
            [
                f"### {_first_text(target.get('name'), target.get('id'), 'Unnamed system')}",
                "",
                f"- Type: {_first_text(target.get('type'), 'unspecified')}",
                f"- Owner: {_first_text(target.get('owner'), 'TBD owner')}",
                f"- Priority: {_first_text(target.get('priority'), 'medium')}",
                f"- Reason: {_first_text(target.get('reason'), 'Confirm why this partner system is in scope.')}",
                f"- Validation action: {_first_text(target.get('validation_action'), 'Validate one sample handoff end to end.')}",
                f"- Source references: {_inline_ids(_string_list(target.get('source_reference_ids')))}",
                "",
            ]
        )

    lines.extend(["## Data Contracts", ""])
    data_contracts = list(report.get("data_contracts") or [])
    if not data_contracts:
        lines.extend(
            [
                "- No data contracts defined yet. Capture producer, consumer, payload, required fields, and replay expectations.",
                "",
            ]
        )
    for contract in data_contracts:
        lines.extend(
            [
                f"### {_first_text(contract.get('id'), 'DC-TBD')}: {_first_text(contract.get('name'), 'Data-sharing contract')}",
                "",
                f"- Owner: {_first_text(contract.get('owner'), 'TBD owner')}",
                f"- Priority: {_first_text(contract.get('priority'), 'medium')}",
                f"- Producer: {_first_text(contract.get('producer'), title)}",
                f"- Consumer: {_first_text(contract.get('consumer'), 'Partner system')}",
                f"- Payload: {_first_text(contract.get('payload'), 'Workflow handoff payload')}",
                f"- Required fields: {_inline_list(_string_list(contract.get('required_fields')))}",
                f"- Validation action: {_first_text(contract.get('validation_action'), 'Replay success and failure responses.')}",
                f"- Source references: {_inline_ids(_string_list(contract.get('source_reference_ids')))}",
                "",
            ]
        )

    lines.extend(["## Auth and Security Checks", ""])
    security_checks = list(report.get("auth_and_security_checks") or [])
    if not security_checks:
        lines.extend(
            [
                "- Confirm credential ownership, auth mode, token rotation, least-privilege access, audit logging, and deletion paths.",
                "",
            ]
        )
    for check in security_checks:
        lines.extend(
            [
                f"### {_first_text(check.get('id'), 'SEC-TBD')}: {_first_text(check.get('check'), 'Credential and data-sharing review')}",
                "",
                f"- Owner: {_first_text(check.get('owner'), 'Security owner')}",
                f"- Priority: {_first_text(check.get('priority'), 'high')}",
                f"- Validation action: {_first_text(check.get('validation_action'), 'Approve auth, access, and audit expectations before build starts.')}",
                f"- Source references: {_inline_ids(_string_list(check.get('source_reference_ids')))}",
                "",
            ]
        )

    lines.extend(["## Operational Readiness", ""])
    operational_items = list(report.get("operational_readiness") or [])
    if not operational_items:
        lines.extend(
            [
                "- Prepare sandbox access, fixtures, monitoring, support routing, rollback notes, and validation ownership.",
                "",
            ]
        )
    for item in operational_items:
        lines.extend(
            [
                f"### {_first_text(item.get('id'), 'OPS-TBD')}: {_first_text(item.get('check'), 'Operational handoff readiness')}",
                "",
                f"- Owner: {_first_text(item.get('owner'), 'Operations owner')}",
                f"- Priority: {_first_text(item.get('priority'), 'medium')}",
                f"- Validation action: {_first_text(item.get('validation_action'), 'Run a dry run and document support escalation paths.')}",
                f"- Source references: {_inline_ids(_string_list(item.get('source_reference_ids')))}",
                "",
            ]
        )

    lines.extend(
        [
            "## Partner Owner Matrix",
            "",
            "| Partner/System | Owner | Priority | Handoff |",
            "| --- | --- | --- | --- |",
        ]
    )
    owner_rows = list(report.get("partner_owner_matrix") or [])
    if not owner_rows:
        lines.append("| TBD partner system | TBD owner | medium | Assign owner and confirm handoff criteria. |")
    for row in owner_rows:
        lines.append(
            "| "
            f"{_first_text(row.get('partner'), 'TBD partner system')} | "
            f"{_first_text(row.get('owner'), 'TBD owner')} | "
            f"{_first_text(row.get('priority'), 'medium')} | "
            f"{_first_text(row.get('handoff'), 'Assign owner and confirm handoff criteria.')} |"
        )

    lines.extend(["", "## Sequencing", ""])
    sequencing = list(report.get("sequencing") or [])
    if not sequencing:
        lines.extend(
            [
                "### 1. Confirm partner scope and owner",
                "",
                "- Target: TBD partner system",
                "- Owner: Product lead",
                "- Priority: high",
                "- Validation action: Name the partner owner, data contract, credential owner, dry-run path, and support handoff.",
                "- Source references: none",
                "",
            ]
        )
    for item in sequencing:
        lines.extend(
            [
                f"### {int(item.get('sequence') or 0)}. {_first_text(item.get('phase'), 'Integration validation step')}",
                "",
                f"- Target: {_first_text(item.get('target'), 'TBD partner system')}",
                f"- Owner: {_first_text(item.get('owner'), 'TBD owner')}",
                f"- Priority: {_first_text(item.get('priority'), 'medium')}",
                f"- Validation action: {_first_text(item.get('validation_action'), 'Validate the handoff before launch.')}",
                f"- Source references: {_inline_ids(_string_list(item.get('source_reference_ids')))}",
                "",
            ]
        )

    lines.extend(["## Open Questions", ""])
    if report.get("open_questions"):
        for question in report.get("open_questions") or []:
            lines.extend(
                [
                    f"- **{_first_text(question.get('id'), 'OQ-TBD')}** ({_first_text(question.get('owner'), 'TBD owner')}): {_first_text(question.get('question'), 'What partner decision must be resolved before handoff?')}",
                    f"  Validation action: {_first_text(question.get('validation_action'), 'Record the decision and owner.')}",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Evidence References", ""])
    if report.get("evidence_references"):
        for reference in report.get("evidence_references") or []:
            lines.append(
                f"- **{_first_text(reference.get('id'), 'evidence-tbd')}** ({_first_text(reference.get('type'), 'reference')}): {_first_text(reference.get('summary'), 'No summary provided.')}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Readiness Warnings", ""])
    if report.get("readiness_warnings"):
        for warning in report.get("readiness_warnings") or []:
            lines.append(
                f"- **{_first_text(warning.get('severity'), 'medium')}**: {_first_text(warning.get('warning'), 'Partner integration readiness needs review.')}"
            )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def partner_integration_checklist_filename(
    design_brief: dict[str, Any], *, fmt: str = "markdown"
) -> str:
    """Return a stable filename for a partner integration checklist export."""
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'partner-integration-checklist'))}-"
        f"partner-integration-checklist.{extension}"
    )


def render_design_brief_partner_integration_checklist_csv(report: dict[str, Any]) -> str:
    """Render partner integration checklist rows as deterministic CSV text."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for target in report.get("integration_targets") or []:
        rows.append(
            _csv_row(
                report,
                section="integration_targets",
                row_type="target",
                item_id=target.get("id"),
                item_name=target.get("name"),
                target_id=target.get("id"),
                target_name=target.get("name"),
                target_type=target.get("type"),
                owner=target.get("owner"),
                priority=target.get("priority"),
                validation_action=target.get("validation_action"),
                source_idea_ids=target.get("source_idea_ids"),
                source_reference_ids=target.get("source_reference_ids"),
                details={"reason": target.get("reason")},
            )
        )
    for contract in report.get("data_contracts") or []:
        rows.append(
            _csv_row(
                report,
                section="data_contracts",
                row_type="data_contract",
                item_id=contract.get("id"),
                item_name=contract.get("name"),
                owner=contract.get("owner"),
                priority=contract.get("priority"),
                producer=contract.get("producer"),
                consumer=contract.get("consumer"),
                payload=contract.get("payload"),
                required_fields=contract.get("required_fields"),
                validation_action=contract.get("validation_action"),
                source_idea_ids=contract.get("source_idea_ids"),
                source_reference_ids=contract.get("source_reference_ids"),
            )
        )
    for check in report.get("auth_and_security_checks") or []:
        rows.append(
            _csv_row(
                report,
                section="auth_and_security_checks",
                row_type="security_check",
                item_id=check.get("id"),
                item_name=check.get("check"),
                owner=check.get("owner"),
                priority=check.get("priority"),
                check=check.get("check"),
                validation_action=check.get("validation_action"),
                source_idea_ids=check.get("source_idea_ids"),
                source_reference_ids=check.get("source_reference_ids"),
            )
        )
    for item in report.get("operational_readiness") or []:
        rows.append(
            _csv_row(
                report,
                section="operational_readiness",
                row_type="operational_check",
                item_id=item.get("id"),
                item_name=item.get("check"),
                owner=item.get("owner"),
                priority=item.get("priority"),
                check=item.get("check"),
                validation_action=item.get("validation_action"),
                source_idea_ids=item.get("source_idea_ids"),
                source_reference_ids=item.get("source_reference_ids"),
            )
        )
    for row in report.get("partner_owner_matrix") or []:
        rows.append(
            _csv_row(
                report,
                section="partner_owner_matrix",
                row_type="owner_matrix_entry",
                item_id=row.get("target_id"),
                item_name=row.get("partner"),
                target_id=row.get("target_id"),
                target_name=row.get("partner"),
                owner=row.get("owner"),
                priority=row.get("priority"),
                handoff=row.get("handoff"),
                details={"checklist_item_ids": row.get("checklist_item_ids")},
            )
        )
    for item in report.get("sequencing") or []:
        rows.append(
            _csv_row(
                report,
                section="sequencing",
                row_type="sequence_item",
                item_id=item.get("id"),
                item_name=item.get("phase"),
                target_id=item.get("target_id"),
                target_name=item.get("target"),
                sequence=item.get("sequence"),
                owner=item.get("owner"),
                priority=item.get("priority"),
                validation_action=item.get("validation_action"),
                source_idea_ids=item.get("source_idea_ids"),
                source_reference_ids=item.get("source_reference_ids"),
            )
        )
    for question in report.get("open_questions") or []:
        rows.append(
            _csv_row(
                report,
                section="open_questions",
                row_type="open_question",
                item_id=question.get("id"),
                item_name=question.get("question"),
                owner=question.get("owner"),
                question=question.get("question"),
                validation_action=question.get("validation_action"),
                source_reference_ids=question.get("source_reference_ids"),
            )
        )
    for warning in report.get("readiness_warnings") or []:
        rows.append(
            _csv_row(
                report,
                section="readiness_warnings",
                row_type="readiness_warning",
                item_id=warning.get("id"),
                item_name=warning.get("warning"),
                severity=warning.get("severity"),
                warning=warning.get("warning"),
                recommended_action=warning.get("recommended_action"),
            )
        )
    return rows


def _csv_row(report: dict[str, Any], **values: Any) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    row = {
        "schema_version": report.get("schema_version"),
        "kind": report.get("kind"),
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "section": "",
        "row_type": "",
        "item_id": "",
        "item_name": "",
        "target_id": "",
        "target_name": "",
        "target_type": "",
        "sequence": "",
        "owner": "",
        "priority": "",
        "severity": "",
        "producer": "",
        "consumer": "",
        "payload": "",
        "required_fields": "",
        "check": "",
        "question": "",
        "warning": "",
        "validation_action": "",
        "handoff": "",
        "recommended_action": "",
        "source_idea_ids": "",
        "source_reference_ids": "",
        "details": "",
    }
    row.update(values)
    return {column: _csv_cell(row.get(column)) for column in CSV_COLUMNS}


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | tuple | set):
        return _stable_json(list(value))
    if isinstance(value, dict):
        return _stable_json(
            {key: item for key, item in value.items() if item not in (None, "", [])}
        )
    return str(value)


def _stable_json(value: Any) -> str:
    return json.dumps(_stable_value(value), sort_keys=True, separators=(",", ":"))


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list | tuple | set):
        return sorted(
            (_stable_value(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
    return value


def _integration_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    title = str(design_brief["title"])
    fallbacks: list[str] = []
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea"),
        (_field_values(source_ideas, "specific_user"), "source_ideas"),
        (f"{title} user", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea"),
        (_field_values(source_ideas, "buyer"), "source_ideas"),
        ("integration sponsor", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas"),
        (f"{title} workflow", "explicit_fallback"),
    )
    concept = _first_with_label(
        fallbacks,
        "merged_product_concept",
        (design_brief.get("merged_product_concept"), "design_brief"),
        (lead_idea and lead_idea.get("solution"), "lead_idea"),
        (_field_values(source_ideas, "solution"), "source_ideas"),
        (f"{title} integration workflow", "explicit_fallback"),
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))
    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
    )
    text_corpus = _dedupe_strings(
        [
            title,
            design_brief.get("domain", ""),
            design_brief.get("theme", ""),
            concept,
            workflow,
            *_string_list(design_brief.get("why_this_now")),
            *_string_list(design_brief.get("synthesis_rationale")),
            *_string_list(design_brief.get("validation_plan")),
            *scope,
            *milestones,
            *risks,
            *_field_values(source_ideas, "tech_approach"),
            *_field_values(source_ideas, "current_workaround"),
            *_field_values(source_ideas, "solution"),
            *_stack_values(source_ideas),
        ]
    )
    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "product_concept": concept,
        "primary_scope": scope[0] if scope else f"first usable {title} integration",
        "first_milestone": milestones[0] if milestones else "first partner integration dry run",
        "validation_plan": _first_text(
            design_brief.get("validation_plan"),
            lead_idea and lead_idea.get("validation_plan"),
            "Run a partner integration dry run with sample records and rollback notes.",
        ),
        "risks": risks,
        "text_corpus": text_corpus,
        "fallbacks_used": fallbacks,
    }


def _integration_targets(
    context: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    text = " ".join(context["text_corpus"]).lower()
    targets = [
        _target(
            "core_product",
            context["title"],
            "owned_application",
            "Product engineering",
            "high",
            f"Primary system serving {context['target_user']} in {context['workflow_context']}.",
            "Confirm the owned application can emit, receive, and reconcile integration events.",
            source_idea_ids,
            evidence_ids,
        )
    ]
    for target_id, name, target_type, owner, keyword in _KNOWN_SYSTEMS:
        if keyword in text:
            targets.append(
                _target(
                    target_id,
                    name,
                    target_type,
                    owner,
                    "high" if target_type in {"crm", "identity", "api"} else "medium",
                    f"Detected from design brief or source idea integration context containing `{keyword}`.",
                    f"Confirm {name} sandbox access, API limits, field mapping, and rollback behavior.",
                    source_idea_ids,
                    evidence_ids,
                )
            )
    if len(targets) == 1:
        targets.append(
            _target(
                "customer_workflow_system",
                "Customer workflow system",
                "external_partner",
                "Integration owner",
                "medium",
                f"Fallback partner target for {context['workflow_context']}.",
                "Name the external system of record and validate one sample handoff end to end.",
                source_idea_ids,
                evidence_ids,
            )
        )
    return _dedupe_targets(targets)


def _data_contracts(
    context: dict[str, Any],
    targets: list[dict[str, Any]],
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    partner = _first_partner(targets)
    return [
        _checklist_item(
            "DC1",
            "Workflow handoff payload",
            "Product engineering",
            "high",
            source_idea_ids,
            evidence_ids,
            producer=context["title"],
            consumer=partner["name"],
            payload=f"{context['primary_scope']} status and ownership handoff",
            required_fields=["record_id", "user_id", "workflow_state", "owner", "timestamp"],
            validation_action="Run a sample handoff and verify required fields, idempotency, and error handling.",
        ),
        _checklist_item(
            "DC2",
            "Partner status return path",
            partner["owner"],
            "medium",
            source_idea_ids,
            evidence_ids[-2:] if len(evidence_ids) > 1 else evidence_ids,
            producer=partner["name"],
            consumer=context["title"],
            payload="Partner processing status, external record link, and failure reason.",
            required_fields=["external_record_id", "status", "updated_at", "failure_reason"],
            validation_action="Replay success, pending, and failure responses against the product workflow.",
        ),
    ]


def _auth_and_security_checks(
    context: dict[str, Any],
    targets: list[dict[str, Any]],
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    partner_names = ", ".join(target["name"] for target in targets[1:]) or "partner systems"
    return [
        _security_item(
            "SEC1",
            "Authentication and token ownership",
            "Security owner",
            "high",
            f"Document auth mode, credential owner, rotation interval, and sandbox credentials for {partner_names}.",
            source_idea_ids,
            evidence_ids,
        ),
        _security_item(
            "SEC2",
            "Least-privilege data access",
            "Security owner",
            "high",
            f"Confirm only fields needed for {context['workflow_context']} are shared with partners.",
            source_idea_ids,
            evidence_ids,
        ),
        _security_item(
            "SEC3",
            "Audit trail and deletion path",
            "Compliance owner",
            "medium",
            "Validate audit logging, retention, customer deletion, and incident escalation paths.",
            source_idea_ids,
            evidence_ids,
        ),
    ]


def _operational_readiness(
    context: dict[str, Any],
    targets: list[dict[str, Any]],
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    partner = _first_partner(targets)
    risk = context["risks"][0] if context["risks"] else "partner downtime or workflow mismatch"
    return [
        _ops_item(
            "OPS1",
            "Sandbox and fixture readiness",
            "Engineering owner",
            "high",
            f"Create sandbox accounts, sample records, and test fixtures for {partner['name']}.",
            source_idea_ids,
            evidence_ids,
        ),
        _ops_item(
            "OPS2",
            "Monitoring and support routing",
            "Support lead",
            "medium",
            "Define alerts, dashboard checks, retry ownership, and customer support escalation notes.",
            source_idea_ids,
            evidence_ids,
        ),
        _ops_item(
            "OPS3",
            "Rollback and risk rehearsal",
            "Product lead",
            "medium",
            f"Rehearse rollback for {risk} before the first integration milestone.",
            source_idea_ids,
            evidence_ids,
        ),
    ]


def _partner_owner_matrix(
    targets: list[dict[str, Any]],
    data_contracts: list[dict[str, Any]],
    security_checks: list[dict[str, Any]],
    operational: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checklist_ids = [item["id"] for item in [*data_contracts, *security_checks, *operational]]
    return [
        {
            "target_id": target["id"],
            "partner": target["name"],
            "owner": target["owner"],
            "priority": target["priority"],
            "handoff": "Own target readiness and close related checklist items.",
            "checklist_item_ids": checklist_ids,
        }
        for target in targets
    ]


def _sequencing(
    context: dict[str, Any],
    targets: list[dict[str, Any]],
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    partner = _first_partner(targets)
    return [
        _sequence_item(
            1,
            "Confirm partner scope and owner",
            partner,
            "Product lead",
            "high",
            f"Name the owner for {partner['name']} and confirm it supports {context['primary_scope']}.",
            source_idea_ids,
            evidence_ids,
        ),
        _sequence_item(
            2,
            "Validate data and security contract",
            partner,
            "Security owner",
            "high",
            "Approve required fields, auth mode, token handling, and audit expectations.",
            source_idea_ids,
            evidence_ids,
        ),
        _sequence_item(
            3,
            "Run integration dry run",
            partner,
            "Engineering owner",
            "medium",
            context["validation_plan"],
            source_idea_ids,
            evidence_ids,
        ),
        _sequence_item(
            4,
            "Approve operational handoff",
            targets[0],
            "Support lead",
            "medium",
            "Confirm monitoring, retry, escalation, and rollback notes before customer use.",
            source_idea_ids,
            evidence_ids,
        ),
    ]


def _open_questions(
    context: dict[str, Any], targets: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    partner = _first_partner(targets)
    questions = [
        {
            "id": "OQ1",
            "owner": partner["owner"],
            "question": f"Which {partner['name']} environment and account should be used for the first dry run?",
            "validation_action": "Record sandbox, production, and access request owners before build starts.",
            "source_reference_ids": evidence_ids,
        },
        {
            "id": "OQ2",
            "owner": "Product lead",
            "question": f"What partner failure should block {context['first_milestone']}?",
            "validation_action": "Define launch-blocking errors, acceptable retries, and rollback criteria.",
            "source_reference_ids": evidence_ids,
        },
    ]
    if context["fallbacks_used"]:
        questions.append(
            {
                "id": "OQ3",
                "owner": "Integration owner",
                "question": "Which missing brief fields must be filled before partner commitments are made?",
                "validation_action": "Fill fallback fields or explicitly accept placeholder assumptions.",
                "source_reference_ids": evidence_ids,
            }
        )
    return questions


def _readiness_warnings(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    targets: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    readiness = float(design_brief.get("readiness_score") or 0.0)
    status = str(design_brief.get("design_status") or "")
    if readiness < 75:
        warnings.append(
            {
                "id": "RW1",
                "severity": "medium" if readiness >= 50 else "high",
                "warning": f"Readiness score is {readiness:.1f}/100; keep partner commitments provisional.",
                "recommended_action": "Use sandbox dry runs until design readiness improves.",
            }
        )
    if status not in {"approved", "published"}:
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "high",
                "warning": f"Design status is `{status or 'unknown'}`; partner integration should not be committed broadly.",
                "recommended_action": "Confirm design approval before external partner scheduling.",
            }
        )
    for fallback in context["fallbacks_used"]:
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "medium",
                "warning": f"Missing {fallback}; checklist uses explicit fallback integration context.",
                "recommended_action": f"Fill design_brief.{fallback} or source idea context before handoff.",
            }
        )
    if len(targets) <= 2 and targets[-1]["id"] == "customer_workflow_system":
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "medium",
                "warning": "No named partner system was detected; fallback integration target was generated.",
                "recommended_action": "Name the system of record, communication tool, API, or data store before build.",
            }
        )
    if not evidence:
        warnings.append(
            {
                "id": f"RW{len(warnings) + 1}",
                "severity": "medium",
                "warning": "No evidence references were found for integration assumptions.",
                "recommended_action": "Attach validation plan, rationale, evidence signals, or insights.",
            }
        )
    return warnings


def _target(
    id: str,
    name: str,
    type: str,
    owner: str,
    priority: str,
    reason: str,
    validation_action: str,
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "type": type,
        "owner": owner,
        "priority": priority,
        "reason": reason,
        "validation_action": validation_action,
        "source_idea_ids": source_idea_ids,
        "source_reference_ids": evidence_ids,
    }


def _checklist_item(
    id: str,
    name: str,
    owner: str,
    priority: str,
    source_idea_ids: list[str],
    evidence_ids: list[str],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "owner": owner,
        "priority": priority,
        "source_idea_ids": source_idea_ids,
        "source_reference_ids": evidence_ids,
        **extra,
    }


def _security_item(
    id: str,
    check: str,
    owner: str,
    priority: str,
    validation_action: str,
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": id,
        "check": check,
        "owner": owner,
        "priority": priority,
        "validation_action": validation_action,
        "source_idea_ids": source_idea_ids,
        "source_reference_ids": evidence_ids,
    }


def _ops_item(
    id: str,
    check: str,
    owner: str,
    priority: str,
    validation_action: str,
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return _security_item(id, check, owner, priority, validation_action, source_idea_ids, evidence_ids)


def _sequence_item(
    sequence: int,
    phase: str,
    target: dict[str, Any],
    owner: str,
    priority: str,
    validation_action: str,
    source_idea_ids: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": f"SEQ{sequence}",
        "sequence": sequence,
        "phase": phase,
        "target_id": target["id"],
        "target": target["name"],
        "owner": owner,
        "priority": priority,
        "validation_action": validation_action,
        "source_idea_ids": source_idea_ids,
        "source_reference_ids": evidence_ids,
    }


def _first_partner(targets: list[dict[str, Any]]) -> dict[str, Any]:
    return next((target for target in targets if target["id"] != "core_product"), targets[0])


def _dedupe_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for target in targets:
        deduped.setdefault(target["id"], target)
    return list(deduped.values())


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
            ideas.append(
                {
                    "id": idea_id,
                    "role": source.get("role", "source"),
                    "rank": source.get("rank", 0),
                    "missing": True,
                }
            )
            continue
        data = unit.model_dump(mode="json")
        data["role"] = source.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _evidence_references(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for field in ("why_this_now", "synthesis_rationale", "validation_plan"):
        text = _first_text(design_brief.get(field))
        if text:
            refs.append(
                {
                    "id": f"design_brief.{field}",
                    "type": "brief_field",
                    "summary": text,
                    "source_idea_ids": list(design_brief.get("source_idea_ids") or []),
                }
            )
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        for signal_id in _string_list(idea.get("evidence_signals")):
            refs.append(
                {
                    "id": signal_id,
                    "type": "evidence_signal",
                    "summary": f"Evidence signal linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "id": insight_id,
                    "type": "insight",
                    "summary": f"Inspiring insight linked to source idea {idea['id']}.",
                    "source_idea_ids": [idea["id"]],
                }
            )
    return _dedupe_refs(refs)


def _source_idea_ids(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    return ids or [str(idea_id) for idea_id in design_brief.get("source_idea_ids") or []]


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _stack_values(source_ideas: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        stack = idea.get("suggested_stack")
        if isinstance(stack, dict):
            for key, value in stack.items():
                values.extend(_string_list(key))
                values.extend(_string_list(value))
        else:
            values.extend(_string_list(stack))
    return _dedupe_strings(values)


def _first_with_label(
    fallbacks: list[str],
    field: str,
    *candidates: tuple[Any, str],
) -> str:
    for value, label in candidates:
        text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    if isinstance(value, dict):
        return [_compact(item) for pair in value.items() for item in pair if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _dedupe_strings(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for ref in refs:
        deduped.setdefault(ref["id"], ref)
    return list(deduped.values())


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _inline_list(values: list[str]) -> str:
    return "; ".join(values) if values else "none"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    parts = [part for part in cleaned.replace("_", "-").split("-") if part]
    return "-".join(parts) or "design-brief"
