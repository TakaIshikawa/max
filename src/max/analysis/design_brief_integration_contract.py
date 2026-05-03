"""Deterministic integration contracts for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.integration_contract"
SCHEMA_VERSION = "max.design_brief.integration_contract.v1"

CONTRACT_SECTION_IDS: tuple[str, ...] = (
    "external_systems",
    "data_contracts",
    "auth_assumptions",
    "api_webhook_contracts",
    "failure_handling",
    "observability_hooks",
    "open_questions",
)

INTEGRATION_CONTRACT_CSV_COLUMNS: tuple[str, ...] = (
    "integration_name",
    "provider",
    "data_exchanged",
    "auth_assumptions",
    "failure_modes",
    "sla_expectations",
    "owner",
    "evidence",
)

_EXTERNAL_SYSTEM_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("Salesforce", "salesforce"),
    ("Slack", "slack"),
    ("Stripe", "stripe"),
    ("GitHub", "github"),
    ("Linear", "linear"),
    ("Jira", "jira"),
    ("HubSpot", "hubspot"),
    ("Zendesk", "zendesk"),
    ("Google Workspace", "google"),
    ("Microsoft 365", "microsoft"),
    ("Notion", "notion"),
    ("Confluence", "confluence"),
    ("Trello", "trello"),
    ("Webex", "webex"),
    ("Opsgenie", "opsgenie"),
)


def build_design_brief_integration_contract(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build implementation-facing integration requirements from a design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    evidence_references = _evidence_references(design_brief, source_ideas)
    evidence_by_id = {reference["id"]: reference for reference in evidence_references}
    context = _contract_context(design_brief, source_ideas)

    external_systems = _external_systems(context, source_idea_ids, evidence_by_id)
    data_contracts = _data_contracts(context, source_idea_ids, evidence_by_id)
    auth_assumptions = _auth_assumptions(context, source_idea_ids, evidence_by_id)
    api_webhook_contracts = _api_webhook_contracts(context, source_idea_ids, evidence_by_id)
    failure_handling = _failure_handling(context, source_idea_ids, evidence_by_id)
    observability_hooks = _observability_hooks(context, source_idea_ids, evidence_by_id)
    open_questions = _open_questions(context, source_idea_ids, evidence_by_id)
    contract_sections = [
        {
            "id": "external_systems",
            "title": "External Systems",
            "items": external_systems,
        },
        {
            "id": "data_contracts",
            "title": "Data Contracts",
            "items": data_contracts,
        },
        {
            "id": "auth_assumptions",
            "title": "Authentication and Authorization",
            "items": auth_assumptions,
        },
        {
            "id": "api_webhook_contracts",
            "title": "API or Webhook Contracts",
            "items": api_webhook_contracts,
        },
        {
            "id": "failure_handling",
            "title": "Failure Handling",
            "items": failure_handling,
        },
        {
            "id": "observability_hooks",
            "title": "Observability Hooks",
            "items": observability_hooks,
        },
        {
            "id": "open_questions",
            "title": "Open Contract Questions",
            "items": open_questions,
        },
    ]

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
            "section_count": len(contract_sections),
            "external_system_count": len(external_systems),
            "data_contract_count": len(data_contracts),
            "auth_assumption_count": len(auth_assumptions),
            "api_webhook_contract_count": len(api_webhook_contracts),
            "failure_handling_count": len(failure_handling),
            "observability_hook_count": len(observability_hooks),
            "open_question_count": len(open_questions),
            "evidence_reference_count": len(evidence_references),
            "fallbacks_used": context["fallbacks_used"],
        },
        "integration_context": context,
        "contract_sections": contract_sections,
        "external_systems": external_systems,
        "data_contracts": data_contracts,
        "auth_assumptions": auth_assumptions,
        "api_webhook_contracts": api_webhook_contracts,
        "failure_handling": failure_handling,
        "observability_hooks": observability_hooks,
        "open_questions": open_questions,
        "evidence_references": evidence_references,
        "source_ideas": source_ideas,
    }


def render_design_brief_integration_contract(
    report: dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render an integration contract as Markdown, deterministic JSON, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_integration_contract_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported integration contract format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Integration Contract: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {_inline_list(brief.get('source_idea_ids') or [])}",
        f"Open questions: {summary['open_question_count']}",
        "",
        "## Contract Summary",
        "",
        f"- Product concept: {report['integration_context']['product_concept']}",
        f"- Primary workflow: {report['integration_context']['workflow_context']}",
        f"- Target user: {report['integration_context']['target_user']}",
        f"- Fallbacks used: {_inline_list(summary['fallbacks_used'])}",
        "",
    ]

    for section in report["contract_sections"]:
        lines.extend([f"## {section['title']}", ""])
        for item in section["items"]:
            lines.extend(_render_contract_item(item))
        if not section["items"]:
            lines.append("- No items generated; confirm whether this integration surface is intentionally out of scope.")
            lines.append("")

    lines.extend(["## Evidence References", ""])
    for reference in report["evidence_references"]:
        lines.append(f"- **{reference['id']}** ({reference['type']}): {reference['summary']}")

    return "\n".join(lines).rstrip() + "\n"


def render_integration_contract_csv(report: dict[str, Any]) -> str:
    """Render integration contracts as one deterministic CSV row per integration."""
    output = StringIO()
    writer = csv.DictWriter(
        output, fieldnames=INTEGRATION_CONTRACT_CSV_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in _integration_contract_csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _external_systems(
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    systems = context["detected_external_systems"] or ["External API or workflow tool"]
    return [
        {
            "id": f"ES{index}",
            "system": system,
            "integration_role": _system_role(system, context),
            "owner": "Engineering owner",
            "environment_need": "Confirm sandbox, staging, and production access before implementation starts.",
            **_evidence(evidence_by_id, ["design_brief.merged_product_concept", "design_brief.mvp_scope"]),
            "source_idea_ids": source_idea_ids,
        }
        for index, system in enumerate(systems[:5], start=1)
    ]


def _data_contracts(
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "DC1",
            "data_object": context["primary_data_object"],
            "direction": "read/write",
            "required_fields": [
                "external_id",
                "status",
                "updated_at",
                "owner_or_actor",
                "source_system",
            ],
            "validation_rules": [
                "Reject records without a stable external identifier.",
                "Persist source timestamps for reconciliation and replay.",
                "Document nullable fields, enum values, and retention needs before build handoff.",
            ],
            **_evidence(evidence_by_id, ["design_brief.mvp_scope", "design_brief.synthesis_rationale"]),
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "DC2",
            "data_object": "Contract fixture and sample payloads",
            "direction": "test fixture",
            "required_fields": [
                "happy_path_payload",
                "missing_required_field_payload",
                "duplicate_event_payload",
            ],
            "validation_rules": [
                "Fixtures cover sparse, duplicate, stale, and malformed external records.",
                "Sample payloads are scrubbed of production secrets and personal data.",
            ],
            **_evidence(evidence_by_id, ["design_brief.validation_plan", "design_brief.risks"]),
            "source_idea_ids": source_idea_ids,
        },
    ]


def _auth_assumptions(
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    auth_model = "OAuth or SSO delegated access" if context["mentions_auth"] else "Least-privilege service credential"
    return [
        {
            "id": "AA1",
            "assumption": auth_model,
            "scope_requirement": "List exact scopes, roles, token lifetime, refresh behavior, and secret storage owner.",
            "authorization_check": f"Confirm {context['target_user']} can only access records needed for {context['workflow_context']}.",
            "approval_owner": "Security owner",
            **_evidence(evidence_by_id, ["design_brief.risks", "design_brief.validation_plan"]),
            "source_idea_ids": source_idea_ids,
        }
    ]


def _api_webhook_contracts(
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "AWC1",
            "contract": "Inbound or outbound integration endpoint",
            "trigger": context["first_milestone"] or f"{context['workflow_context']} state change",
            "payload_expectation": "Define request method, URL, headers, schema, idempotency key, pagination, and rate limits.",
            "response_expectation": "Document success codes, retryable errors, terminal errors, and duplicate-event behavior.",
            **_evidence(evidence_by_id, ["design_brief.first_milestones", "design_brief.mvp_scope"]),
            "source_idea_ids": source_idea_ids,
        }
    ]


def _failure_handling(
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "FH1",
            "failure_mode": "External system unavailable or rate limited",
            "handling_requirement": "Use bounded retries, dead-letter capture, operator-visible status, and documented replay steps.",
            "user_impact": f"{context['target_user']} sees delayed or partial {context['primary_data_object']} updates instead of silent loss.",
            **_evidence(evidence_by_id, ["design_brief.risks", "design_brief.validation_plan"]),
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "FH2",
            "failure_mode": "Payload validation or authorization failure",
            "handling_requirement": "Reject unsafe writes, preserve raw error context without secrets, and route owner action items.",
            "user_impact": "Invalid records are blocked with a recoverable support path.",
            **_evidence(evidence_by_id, ["design_brief.risks", "design_brief.synthesis_rationale"]),
            "source_idea_ids": source_idea_ids,
        },
    ]


def _observability_hooks(
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "OH1",
            "signal": "Integration health and latency",
            "hook": "Emit counters for request count, success rate, retry count, terminal failures, and p95 latency by external system.",
            "alert_threshold": "Alert when failures exceed the launch threshold or when no events arrive during expected workflow windows.",
            **_evidence(evidence_by_id, ["design_brief.validation_plan", "design_brief.first_milestones"]),
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OH2",
            "signal": "Data reconciliation",
            "hook": f"Track source-to-local record counts and last successful sync for {context['primary_data_object']}.",
            "alert_threshold": "Alert on stale syncs, duplicate records, missing required fields, or replay backlog growth.",
            **_evidence(evidence_by_id, ["design_brief.mvp_scope", "design_brief.risks"]),
            "source_idea_ids": source_idea_ids,
        },
    ]


def _open_questions(
    context: dict[str, Any],
    source_idea_ids: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    questions = [
        (
            "OQ1",
            "Which external systems are authoritative for each field in the first release?",
            "Engineering owner",
            "Block implementation until source of truth and reconciliation owner are explicit.",
            ["design_brief.mvp_scope", "design_brief.merged_product_concept"],
        ),
        (
            "OQ2",
            "What auth scopes, approval process, and secret rotation policy are acceptable?",
            "Security owner",
            "Block production access until scopes and credential handling are approved.",
            ["design_brief.risks", "design_brief.validation_plan"],
        ),
        (
            "OQ3",
            "What payload examples, webhook retries, and rate limits must be tested before launch?",
            "QA owner",
            "Block launch until happy path, malformed, duplicate, and retry fixtures exist.",
            ["design_brief.validation_plan", "design_brief.first_milestones"],
        ),
    ]
    if context["fallbacks_used"]:
        questions.append(
            (
                "OQ4",
                "Which sparse brief assumptions should be replaced with owner-approved contract details?",
                "Product owner",
                f"Resolve fallback fields before build handoff: {_inline_list(context['fallbacks_used'])}.",
                ["design_brief"],
            )
        )
    return [
        {
            "id": question_id,
            "question": question,
            "owner": owner,
            "decision_needed": decision_needed,
            **_evidence(evidence_by_id, preferred_ids),
            "source_idea_ids": source_idea_ids,
        }
        for question_id, question, owner, decision_needed, preferred_ids in questions
    ]


def _contract_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = _first_text(design_brief.get("title"), "Untitled design brief")
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    target_user = _first_with_fallback(
        fallbacks,
        "specific_user",
        design_brief.get("specific_user"),
        lead_idea and lead_idea.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
        f"{title} user",
    )
    workflow = _first_with_fallback(
        fallbacks,
        "workflow_context",
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        f"{title} workflow",
    )
    product_concept = _first_with_fallback(
        fallbacks,
        "merged_product_concept",
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("solution"),
        _field_values(source_ideas, "solution"),
        f"{title} product concept",
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    if not scope:
        fallbacks.append("mvp_scope")
    risks = _dedupe_strings(
        [
            *_string_list(design_brief.get("risks")),
            *_field_values(source_ideas, "domain_risks"),
        ]
    )
    if not risks:
        risks = ["Integration failure modes are under-specified; validate with conservative retry and reconciliation requirements."]
        fallbacks.append("risks")
    milestones = _string_list(design_brief.get("first_milestones"))
    if not milestones:
        fallbacks.append("first_milestones")
    corpus = _dedupe_strings(
        [
            title,
            design_brief.get("domain", ""),
            design_brief.get("theme", ""),
            design_brief.get("why_this_now", ""),
            design_brief.get("synthesis_rationale", ""),
            design_brief.get("validation_plan", ""),
            product_concept,
            target_user,
            workflow,
            *scope,
            *milestones,
            *risks,
            *_field_values(source_ideas, "problem"),
            *_field_values(source_ideas, "solution"),
            *_field_values(source_ideas, "current_workaround"),
            *_field_values(source_ideas, "tech_approach"),
            *_stack_values(source_ideas),
        ]
    )
    return {
        "title": title,
        "target_user": target_user,
        "workflow_context": workflow,
        "product_concept": product_concept,
        "primary_scope": scope[0] if scope else f"first usable {title} workflow",
        "first_milestone": milestones[0] if milestones else "",
        "risks": risks,
        "primary_data_object": _primary_data_object(corpus, title),
        "detected_external_systems": _detected_external_systems(corpus),
        "mentions_auth": _has_any(corpus, ("oauth", "sso", "auth", "permission", "scope")),
        "mentions_webhook_or_api": _has_any(corpus, ("api", "webhook", "callback", "endpoint")),
        "fallbacks_used": _dedupe_strings(fallbacks),
        "text_corpus": corpus,
    }


def _evidence_references(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    for field in (
        "why_this_now",
        "merged_product_concept",
        "synthesis_rationale",
        "mvp_scope",
        "first_milestones",
        "validation_plan",
        "risks",
    ):
        values = _string_list(design_brief.get(field))
        if values:
            refs.append(
                {
                    "id": f"design_brief.{field}",
                    "type": "brief_field",
                    "summary": "; ".join(values),
                    "source_idea_ids": source_idea_ids,
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
                    "summary": _first_text(idea.get("one_liner"), idea.get("problem"), idea["id"]),
                    "source_idea_ids": [idea["id"]],
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            refs.append(
                {
                    "id": insight_id,
                    "type": "inspiring_insight",
                    "summary": _first_text(idea.get("value_proposition"), idea.get("solution"), idea["id"]),
                    "source_idea_ids": [idea["id"]],
                }
            )
    if not refs:
        refs.append(
            {
                "id": "design_brief",
                "type": "brief",
                "summary": "Sparse design brief with no explicit integration evidence fields.",
                "source_idea_ids": source_idea_ids,
            }
        )
    return list({reference["id"]: reference for reference in refs}.values())


def _evidence(
    evidence_by_id: dict[str, dict[str, Any]],
    preferred_ids: list[str],
) -> dict[str, str]:
    for reference_id in preferred_ids:
        reference = evidence_by_id.get(reference_id)
        if reference:
            return {
                "evidence_reference_id": reference_id,
                "evidence_reference_summary": str(reference["summary"]),
            }
    reference_id, reference = next(iter(evidence_by_id.items()))
    return {
        "evidence_reference_id": reference_id,
        "evidence_reference_summary": str(reference["summary"]),
    }


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
        stack = idea.get("suggested_stack")
        if isinstance(stack, dict):
            values.extend(str(value) for value in stack.values() if value)
    return _dedupe_strings(values)


def _detected_external_systems(values: list[str]) -> list[str]:
    text = " ".join(values).lower()
    return [name for name, keyword in _EXTERNAL_SYSTEM_KEYWORDS if keyword in text]


def _primary_data_object(values: list[str], title: str) -> str:
    text = " ".join(values).lower()
    if "customer" in text or "account" in text:
        return "Customer or account record"
    if "ticket" in text or "support" in text:
        return "Support ticket or case record"
    if "payment" in text or "invoice" in text or "subscription" in text:
        return "Payment or subscription record"
    if "issue" in text or "repository" in text or "pull request" in text:
        return "Repository issue or change record"
    return f"{title} workflow record"


def _system_role(system: str, context: dict[str, Any]) -> str:
    lowered = system.lower()
    if lowered in {"slack", "webex"}:
        return f"Notification and collaboration surface for {context['workflow_context']}."
    if lowered in {"salesforce", "hubspot", "zendesk"}:
        return f"Source or destination for {context['primary_data_object']}."
    if lowered in {"github", "linear", "jira", "trello"}:
        return "Workflow task, issue, or implementation handoff system."
    if lowered in {"stripe"}:
        return "Payment, billing, or subscription system of record."
    return "External dependency that needs owner, environment, and contract confirmation."


def _render_contract_item(item: dict[str, Any]) -> list[str]:
    title = (
        item.get("system")
        or item.get("data_object")
        or item.get("assumption")
        or item.get("contract")
        or item.get("failure_mode")
        or item.get("signal")
        or item.get("question")
        or "Contract item"
    )
    lines = [f"### {item['id']}: {title}", ""]
    for key, value in item.items():
        if key in {"id", "source_idea_ids"}:
            continue
        label = key.replace("_", " ").capitalize()
        if isinstance(value, list):
            lines.append(f"- {label}: {_inline_list([str(item) for item in value])}")
        else:
            lines.append(f"- {label}: {value}")
    lines.append(f"- Source ideas: {_inline_list(item.get('source_idea_ids') or [])}")
    lines.append("")
    return lines


def _integration_contract_csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    systems = [item for item in report.get("external_systems") or [] if isinstance(item, dict)]
    return [_integration_contract_csv_row(report, system) for system in systems]


def _integration_contract_csv_row(
    report: dict[str, Any],
    system: dict[str, Any],
) -> dict[str, str]:
    row = {
        "integration_name": _csv_text(
            system.get("integration_name") or system.get("name") or system.get("system")
        ),
        "provider": _csv_text(system.get("provider") or system.get("system")),
        "data_exchanged": _csv_text(_data_exchanged_for_csv(report)),
        "auth_assumptions": _csv_text(_auth_assumptions_for_csv(report)),
        "failure_modes": _csv_text(_failure_modes_for_csv(report)),
        "sla_expectations": _csv_text(_sla_expectations_for_csv(report)),
        "owner": _csv_text(system.get("owner")),
        "evidence": _csv_text(_evidence_for_csv(report, system)),
    }
    return {column: row.get(column, "") for column in INTEGRATION_CONTRACT_CSV_COLUMNS}


def _data_exchanged_for_csv(report: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for contract in _dict_items(report.get("data_contracts")):
        values.extend(
            [
                contract.get("data_object"),
                _csv_label("direction", contract.get("direction")),
                _csv_label("required_fields", contract.get("required_fields")),
                _csv_label("validation_rules", contract.get("validation_rules")),
            ]
        )
    return values


def _auth_assumptions_for_csv(report: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for assumption in _dict_items(report.get("auth_assumptions")):
        values.extend(
            [
                assumption.get("assumption"),
                assumption.get("scope_requirement"),
                assumption.get("authorization_check"),
                _csv_label("approval_owner", assumption.get("approval_owner")),
            ]
        )
    return values


def _failure_modes_for_csv(report: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for failure in _dict_items(report.get("failure_handling")):
        values.extend(
            [
                failure.get("failure_mode"),
                failure.get("handling_requirement"),
                _csv_label("user_impact", failure.get("user_impact")),
            ]
        )
    return values


def _sla_expectations_for_csv(report: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for hook in _dict_items(report.get("observability_hooks")):
        values.extend(
            [
                hook.get("signal"),
                hook.get("hook"),
                _csv_label("alert_threshold", hook.get("alert_threshold")),
            ]
        )
    return values


def _evidence_for_csv(report: dict[str, Any], system: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in [
        system,
        *_dict_items(report.get("data_contracts")),
        *_dict_items(report.get("auth_assumptions")),
        *_dict_items(report.get("failure_handling")),
        *_dict_items(report.get("observability_hooks")),
    ]:
        values.extend(_string_list(item.get("evidence_reference_id")))
        values.extend(_string_list(item.get("source_reference_ids")))
    return _dedupe_strings(values)


def _csv_label(label: str, value: Any) -> str:
    text = _csv_text(value)
    return f"{label}: {text}" if text else ""


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list_items(value) if isinstance(item, dict)]


def _list_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value, key=lambda item: _csv_text(item))
    return [value]


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}: {_csv_text(item)}"
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if _csv_text(item)
        )
    if isinstance(value, (list, tuple, set)):
        return "; ".join(text for item in _list_items(value) if (text := _csv_text(item)))
    return str(value)


def _first_with_fallback(
    fallbacks: list[str],
    label: str,
    *values: Any,
) -> str:
    for value in values[:-1]:
        text = _first_text(value)
        if text:
            return text
    fallbacks.append(label)
    return str(values[-1])


def _first_text(*values: Any) -> str:
    for value in values:
        for item in _string_list(value):
            if item:
                return item
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = " ".join(value.split())
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return values
    text = " ".join(str(value).split())
    return [text] if text else []


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value).split())
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _has_any(values: list[str], terms: tuple[str, ...]) -> bool:
    text = " ".join(values).lower()
    return any(term in text for term in terms)


def _inline_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"
