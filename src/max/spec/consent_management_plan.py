"""Generate deterministic consent management plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


SCHEMA_VERSION = "max.spec.consent_management_plan.v1"
CONSENT_MANAGEMENT_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.consent_management_plan"

CSV_COLUMNS = (
    "schema_version",
    "kind",
    "source_idea_id",
    "title",
    "workflow_context",
    "consent_gate",
    "section",
    "item_id",
    "name",
    "owner",
    "description",
    "evidence_references",
)

_SURFACE_DEFINITIONS = (
    (
        "account_profile",
        "Account and profile collection",
        ("account", "profile", "signup", "register", "email", "contact", "customer", "user"),
        "Capture consent when collecting account, user, customer, or profile details.",
        "product_owner",
        "project.target_users",
    ),
    (
        "data_import",
        "Data import or upload",
        ("csv", "document", "file", "import", "spreadsheet", "upload"),
        "Show purpose, source, retention, and sharing terms before users import or upload data.",
        "data_owner",
        "execution.mvp_scope",
    ),
    (
        "integration_authorization",
        "Third-party integration authorization",
        (
            "api",
            "github",
            "hubspot",
            "integration",
            "oauth",
            "salesforce",
            "slack",
            "stripe",
            "teams",
            "twilio",
            "webhook",
        ),
        "Record consent and scopes before connecting external systems or sending workflow payloads.",
        "integration_owner",
        "solution.suggested_stack",
    ),
    (
        "ai_processing",
        "AI processing notice",
        ("ai", "embedding", "generated", "llm", "model", "openai", "prompt", "summary"),
        "Disclose AI processing, model inputs, generated outputs, provider handling, and opt-out expectations.",
        "policy_owner",
        "solution.technical_approach",
    ),
    (
        "analytics_tracking",
        "Analytics and telemetry consent",
        ("analytics", "event", "log", "metric", "monitor", "telemetry", "trace", "usage"),
        "Separate product usage measurement from operational logs and honor opt-out where applicable.",
        "analytics_owner",
        "evaluation",
    ),
    (
        "communications",
        "Notifications and communication preferences",
        ("alert", "email", "message", "notification", "reminder", "slack", "sms"),
        "Let users choose required workflow notifications separately from optional communications.",
        "lifecycle_owner",
        "execution.validation_plan",
    ),
    (
        "exports_and_sharing",
        "Exports and report sharing",
        ("download", "export", "report", "share", "sharing"),
        "Explain recipient, expiration, and downstream responsibility before exports leave product controls.",
        "data_owner",
        "solution.approach",
    ),
    (
        "regulated_data_notice",
        "Regulated or sensitive data consent",
        (
            "children",
            "consent",
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
        "Require explicit owner-approved notice and consent before processing regulated or sensitive data.",
        "privacy_owner",
        "source.domain",
    ),
)

_SURFACE_ORDER = {surface_id: index for index, (surface_id, *_rest) in enumerate(_SURFACE_DEFINITIONS)}


def generate_consent_management_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic consent-management guidance."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}

    context = _context(spec, source, project, solution, execution, evaluation, evidence)
    consent_surfaces = _consent_surfaces(context)
    user_controls = _user_controls(consent_surfaces, context)
    audit_events = _audit_events(consent_surfaces, user_controls, context)
    retention_notes = _retention_notes(consent_surfaces, context)
    owner_actions = _owner_actions(consent_surfaces, user_controls, retention_notes, context)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "domain": source.get("domain"),
            "category": source.get("category"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(context["evidence_ids"]),
        },
        "summary": {
            "title": context["title"],
            "workflow_context": context["workflow_context"],
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "consent_gate": _consent_gate(context, consent_surfaces),
            "consent_surface_count": len(consent_surfaces),
            "user_control_count": len(user_controls),
            "audit_event_count": len(audit_events),
            "retention_note_count": len(retention_notes),
            "owner_action_count": len(owner_actions),
        },
        "consent_surfaces": consent_surfaces,
        "user_controls": user_controls,
        "audit_events": audit_events,
        "retention_notes": retention_notes,
        "owner_actions": owner_actions,
        "evidence_references": context["evidence_references"],
    }


def render_consent_management_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a consent management plan as stable Markdown."""
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    title = _text(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Consent Management Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Consent gate: {_text(summary.get('consent_gate'))}",
        f"- Evidence references: {_text(source.get('evidence_reference_count'))}",
        "",
    ]

    _extend_section(lines, "Consent Surfaces", plan.get("consent_surfaces") or [], _render_surface)
    _extend_section(lines, "User Controls", plan.get("user_controls") or [], _render_control)
    _extend_section(lines, "Audit Events", plan.get("audit_events") or [], _render_audit_event)
    _extend_section(lines, "Retention Notes", plan.get("retention_notes") or [], _render_retention_note)
    _extend_section(lines, "Owner Actions", plan.get("owner_actions") or [], _render_owner_action)
    _extend_section(
        lines,
        "Evidence References",
        plan.get("evidence_references") or [],
        _render_evidence_reference,
        empty="No explicit evidence references were attached to the TactSpec preview.",
    )

    return "\n".join(lines).rstrip() + "\n"


def render_consent_management_plan_csv(plan: dict[str, Any]) -> str:
    """Render plan sections as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(plan if isinstance(plan, dict) else {}):
        writer.writerow(row)
    return output.getvalue()


def _context(
    spec: dict[str, Any],
    source: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
    evaluation: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    text = _haystack(
        {
            "source_context": {
                "status": source.get("status"),
                "domain": source.get("domain"),
                "category": source.get("category"),
            },
            "project": project,
            "solution": solution,
            "execution": execution,
            "evaluation": evaluation,
        }
    )
    evidence_references = _evidence_references(evidence, source, evaluation)
    return {
        "title": _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec",
        "workflow_context": _compact(project.get("workflow_context") or project.get("summary")) or "primary workflow",
        "target_user": _compact(project.get("specific_user") or project.get("target_users")) or "primary user",
        "buyer": _compact(project.get("buyer")) or "launch sponsor",
        "text": text,
        "mentions_consent": _contains_any(text, ("consent", "permission", "notice", "opt-in", "opt out", "opt-out")),
        "mentions_retention": _contains_any(text, ("retention", "retain", "delete", "deletion", "expire", "ttl")),
        "mentions_external_transfer": _contains_any(
            text,
            ("api", "github", "hubspot", "integration", "oauth", "salesforce", "slack", "stripe", "third-party", "webhook"),
        ),
        "mentions_sensitive": _contains_any(
            text,
            ("children", "financial", "gdpr", "health", "healthcare", "hipaa", "medical", "patient", "payment", "student"),
        ),
        "surface_terms": _detected_surface_terms(text),
        "execution_risks": [_compact(risk) for risk in _list(execution.get("risks")) if _compact(risk)],
        "evidence_references": evidence_references,
        "evidence_ids": [item["id"] for item in evidence_references],
    }


def _consent_surfaces(context: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces = []
    for surface_id, label, _terms, description, owner, fallback_evidence in _SURFACE_DEFINITIONS:
        terms = context["surface_terms"].get(surface_id, [])
        if not terms:
            continue
        surfaces.append(
            {
                "id": f"CS{len(surfaces) + 1:02d}",
                "surface_id": surface_id,
                "name": label,
                "owner": owner,
                "description": description,
                "consent_type": _consent_type(surface_id),
                "trigger": _surface_trigger(surface_id, context),
                "evidence_references": _evidence([fallback_evidence, *terms, *context["evidence_ids"]]),
            }
        )

    if not surfaces:
        surfaces.append(
            {
                "id": "CS01",
                "surface_id": "core_workflow_consent",
                "name": "Core workflow consent",
                "owner": "product_owner",
                "description": "Sparse previews still need a baseline notice for user-visible collection, processing, and sharing.",
                "consent_type": "notice_and_acknowledgement",
                "trigger": f"Before users enter or approve data for {context['workflow_context']}.",
                "evidence_references": _evidence(["project", "solution", *context["evidence_ids"]]),
            }
        )

    return sorted(surfaces, key=lambda item: (_SURFACE_ORDER.get(item["surface_id"], 99), item["id"]))


def _user_controls(
    consent_surfaces: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    controls = [
        _control(
            "UC01",
            "Consent preference center",
            "product_owner",
            "Give users a single place to view active consent choices, required notices, and optional preferences.",
            [surface["id"] for surface in consent_surfaces],
        ),
        _control(
            "UC02",
            "Consent withdrawal request",
            "privacy_owner",
            "Allow users or account owners to withdraw optional consent and route required-processing exceptions for review.",
            [surface["id"] for surface in consent_surfaces],
        ),
        _control(
            "UC03",
            "Data export and deletion request",
            "data_owner",
            "Connect consent withdrawal to export, deletion, and downstream cleanup workflows.",
            ["retention_notes", *context["evidence_ids"]],
        ),
    ]
    if any(surface["surface_id"] == "integration_authorization" for surface in consent_surfaces):
        controls.append(
            _control(
                "UC04",
                "Integration disconnect control",
                "integration_owner",
                "Let account owners revoke integration consent, disconnect scopes, and request downstream deletion evidence.",
                ["integration_authorization", "solution.suggested_stack"],
            )
        )
    if any(surface["surface_id"] == "analytics_tracking" for surface in consent_surfaces):
        controls.append(
            _control(
                f"UC{len(controls) + 1:02d}",
                "Optional analytics opt-out",
                "analytics_owner",
                "Separate required operational logging from optional product analytics and record opt-out decisions.",
                ["analytics_tracking", "evaluation"],
            )
        )
    if any(surface["surface_id"] == "ai_processing" for surface in consent_surfaces):
        controls.append(
            _control(
                f"UC{len(controls) + 1:02d}",
                "AI processing preference",
                "policy_owner",
                "Expose whether user content is sent to AI providers and provide the approved opt-out or manual-review path.",
                ["ai_processing", "solution.technical_approach"],
            )
        )
    return controls


def _audit_events(
    consent_surfaces: list[dict[str, Any]],
    user_controls: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    events = [
        _audit_event(
            "AE01",
            "consent_notice_presented",
            "product_owner",
            "Record notice version, surface, actor, timestamp, locale, and account boundary when consent text is shown.",
            [surface["id"] for surface in consent_surfaces],
        ),
        _audit_event(
            "AE02",
            "consent_granted",
            "product_owner",
            "Record consent grant, source surface, purpose, required/optional status, and evidence version.",
            [surface["id"] for surface in consent_surfaces],
        ),
        _audit_event(
            "AE03",
            "consent_withdrawn",
            "privacy_owner",
            "Record withdrawal, downstream tasks opened, affected purposes, and customer-visible confirmation.",
            [control["id"] for control in user_controls],
        ),
        _audit_event(
            "AE04",
            "consent_policy_changed",
            "privacy_owner",
            "Record policy version changes and identify users or accounts needing renewed notice.",
            ["owner_actions", *context["evidence_ids"]],
        ),
    ]
    if context["mentions_external_transfer"]:
        events.append(
            _audit_event(
                f"AE{len(events) + 1:02d}",
                "external_consent_scope_changed",
                "integration_owner",
                "Record connected vendor, scopes, actor, payload class, revocation, and deletion handoff status.",
                ["integration_authorization", "solution.suggested_stack"],
            )
        )
    if context["mentions_retention"] or context["mentions_sensitive"]:
        events.append(
            _audit_event(
                f"AE{len(events) + 1:02d}",
                "retention_or_rights_request_applied",
                "data_owner",
                "Record retention, deletion, export, or rights-request action linked to consent state.",
                ["retention_notes", "execution.validation_plan"],
            )
        )
    return events


def _retention_notes(
    consent_surfaces: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    notes = [
        {
            "id": "RN01",
            "topic": "Consent ledger retention",
            "owner": "privacy_owner",
            "description": "Retain consent grant, notice version, withdrawal, and policy-change events long enough to prove user choice and customer instructions.",
            "implication": "Consent evidence may need to outlive the associated product record while storing only minimal actor and purpose metadata.",
            "evidence_references": _evidence(["audit_events", *context["evidence_ids"]]),
        },
        {
            "id": "RN02",
            "topic": "Withdrawal cleanup",
            "owner": "data_owner",
            "description": "Tie withdrawal to deletion, suppression, integration disconnect, export expiry, and derived-output cleanup.",
            "implication": "Every optional consent surface needs an owner-approved retention and deletion path.",
            "evidence_references": _evidence([surface["id"] for surface in consent_surfaces]),
        },
    ]
    if context["mentions_external_transfer"]:
        notes.append(
            {
                "id": f"RN{len(notes) + 1:02d}",
                "topic": "Downstream vendor copies",
                "owner": "integration_owner",
                "description": "Track consent state, revocation, retry payloads, and deletion handoffs for connected vendors and webhooks.",
                "implication": "Vendor copies need contract, region, retry, and deletion evidence linked to the consent ledger.",
                "evidence_references": _evidence(["solution.suggested_stack", "integration_authorization", *context["evidence_ids"]]),
            }
        )
    if any(surface["surface_id"] == "ai_processing" for surface in consent_surfaces):
        notes.append(
            {
                "id": f"RN{len(notes) + 1:02d}",
                "topic": "AI input and output retention",
                "owner": "policy_owner",
                "description": "Align prompts, provider logs, generated outputs, embeddings, and review artifacts with consent state.",
                "implication": "AI-derived data can preserve source content and must be covered by withdrawal and deletion behavior.",
                "evidence_references": _evidence(["ai_processing", "solution.technical_approach", *context["evidence_ids"]]),
            }
        )
    if not context["mentions_retention"]:
        notes.append(
            {
                "id": f"RN{len(notes) + 1:02d}",
                "topic": "Missing explicit retention terms",
                "owner": "data_owner",
                "description": "The TactSpec preview does not name consent-ledger retention, deletion, or evidence expiry behavior.",
                "implication": "Use a conservative default and require retention owner approval before production consent capture.",
                "evidence_references": ["execution.validation_plan", "execution.risks"],
            }
        )
    return notes


def _owner_actions(
    consent_surfaces: list[dict[str, Any]],
    user_controls: list[dict[str, Any]],
    retention_notes: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    actions = [
        _owner_action(
            "OA01",
            "product_owner",
            "Approve consent copy and required-vs-optional purpose map before pilot launch.",
            [surface["id"] for surface in consent_surfaces],
        ),
        _owner_action(
            "OA02",
            "engineering_owner",
            "Implement consent ledger events, idempotent updates, and test fixtures for grant, withdrawal, and policy-change paths.",
            [control["id"] for control in user_controls],
        ),
        _owner_action(
            "OA03",
            "privacy_owner",
            "Review legal basis, notice versioning, withdrawal exceptions, and evidence retention.",
            [note["id"] for note in retention_notes],
        ),
    ]
    if context["mentions_external_transfer"]:
        actions.append(
            _owner_action(
                f"OA{len(actions) + 1:02d}",
                "integration_owner",
                "Map vendor scopes, downstream deletion behavior, and revocation evidence for every connected system.",
                ["integration_authorization", "solution.suggested_stack"],
            )
        )
    if context["mentions_sensitive"]:
        actions.append(
            _owner_action(
                f"OA{len(actions) + 1:02d}",
                "privacy_owner",
                "Require explicit approval before processing regulated or sensitive data under the consent plan.",
                ["regulated_data_notice", "source.domain"],
            )
        )
    if not context["mentions_consent"]:
        actions.append(
            _owner_action(
                f"OA{len(actions) + 1:02d}",
                "product_owner",
                "Add explicit consent, notice, and withdrawal requirements to the TactSpec before implementation starts.",
                ["project", "solution", "execution"],
            )
        )
    return actions


def _consent_gate(context: dict[str, Any], consent_surfaces: list[dict[str, Any]]) -> str:
    if context["mentions_sensitive"]:
        return "privacy_review_required"
    if context["mentions_external_transfer"] or any(
        surface["surface_id"] in {"integration_authorization", "ai_processing"} for surface in consent_surfaces
    ):
        return "owner_review_required"
    if not context["mentions_consent"]:
        return "consent_requirements_needed"
    return "ready_with_controls"


def _control(
    control_id: str,
    name: str,
    owner: str,
    description: str,
    evidence_references: list[str],
) -> dict[str, Any]:
    return {
        "id": control_id,
        "name": name,
        "owner": owner,
        "description": description,
        "evidence_references": _evidence(evidence_references),
    }


def _audit_event(
    event_id: str,
    event_name: str,
    owner: str,
    description: str,
    evidence_references: list[str],
) -> dict[str, Any]:
    return {
        "id": event_id,
        "event_name": event_name,
        "owner": owner,
        "description": description,
        "required_fields": ["actor_id", "account_id", "surface_id", "purpose", "timestamp", "notice_version"],
        "evidence_references": _evidence(evidence_references),
    }


def _owner_action(
    action_id: str,
    owner: str,
    action: str,
    evidence_references: list[str],
) -> dict[str, Any]:
    return {
        "id": action_id,
        "owner": owner,
        "action": action,
        "evidence_references": _evidence(evidence_references),
    }


def _consent_type(surface_id: str) -> str:
    if surface_id in {"regulated_data_notice", "ai_processing", "integration_authorization"}:
        return "explicit_consent"
    if surface_id in {"analytics_tracking", "communications"}:
        return "preference_opt_in"
    return "notice_and_acknowledgement"


def _surface_trigger(surface_id: str, context: dict[str, Any]) -> str:
    triggers = {
        "account_profile": "Before account, profile, contact, or customer fields are saved.",
        "data_import": "Before files, spreadsheets, records, or documents are imported.",
        "integration_authorization": "Before OAuth, API, webhook, or third-party scopes are connected.",
        "ai_processing": "Before user content is sent to AI processing or stored as derived output.",
        "analytics_tracking": "Before optional analytics or usage tracking starts.",
        "communications": "Before optional reminders, alerts, messages, or notifications are sent.",
        "exports_and_sharing": "Before generated exports, reports, or shared files leave product access controls.",
        "regulated_data_notice": "Before regulated or sensitive data is collected, processed, or transferred.",
    }
    return triggers.get(surface_id, f"Before users approve data handling for {context['workflow_context']}.")


def _render_surface(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Surface ID: {_text(item.get('surface_id'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Consent type: {_text(item.get('consent_type'))}",
        f"- Trigger: {_text(item.get('trigger'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Evidence: {_inline_list(item.get('evidence_references') or [])}",
    ]


def _render_control(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Evidence: {_inline_list(item.get('evidence_references') or [])}",
    ]


def _render_audit_event(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('event_name'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Required fields: {_inline_list(item.get('required_fields') or [])}",
        f"- Evidence: {_inline_list(item.get('evidence_references') or [])}",
    ]


def _render_retention_note(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('topic'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Implication: {_text(item.get('implication'))}",
        f"- Evidence: {_inline_list(item.get('evidence_references') or [])}",
    ]


def _render_owner_action(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('owner'))}",
        "",
        f"- Action: {_text(item.get('action'))}",
        f"- Evidence: {_inline_list(item.get('evidence_references') or [])}",
    ]


def _render_evidence_reference(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        "",
        f"- Type: {_text(item.get('type'))}",
        f"- Source: {_text(item.get('source'))}",
        f"- Summary: {_text(item.get('summary'))}",
    ]


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    renderer: Any,
    *,
    empty: str = "None.",
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend([empty, ""])
        return
    for item in items:
        lines.extend([*renderer(item), ""])


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section, items, name_key, description_key in (
        ("consent_surfaces", plan.get("consent_surfaces"), "name", "description"),
        ("user_controls", plan.get("user_controls"), "name", "description"),
        ("audit_events", plan.get("audit_events"), "event_name", "description"),
        ("retention_notes", plan.get("retention_notes"), "topic", "implication"),
        ("owner_actions", plan.get("owner_actions"), "owner", "action"),
        ("evidence_references", plan.get("evidence_references"), "id", "summary"),
    ):
        for item in _dict_items(items):
            rows.append(_csv_row(plan, section, item, name_key, description_key))
    return rows


def _csv_row(
    plan: dict[str, Any],
    section: str,
    item: dict[str, Any],
    name_key: str,
    description_key: str,
) -> dict[str, str]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    return {
        "schema_version": _text(plan.get("schema_version")),
        "kind": _text(plan.get("kind")),
        "source_idea_id": _text(source.get("idea_id")),
        "title": _text(summary.get("title")),
        "workflow_context": _text(summary.get("workflow_context")),
        "consent_gate": _text(summary.get("consent_gate")),
        "section": section,
        "item_id": _text(item.get("id")),
        "name": _text(item.get(name_key)),
        "owner": _text(item.get("owner")),
        "description": _text(item.get(description_key)),
        "evidence_references": _inline_list(item.get("evidence_references") or []),
    }


def _detected_surface_terms(text: str) -> dict[str, list[str]]:
    return {
        surface_id: [_term_label(term) for term in terms if term in text]
        for surface_id, _label, terms, *_rest in _SURFACE_DEFINITIONS
    }


def _evidence_references(
    evidence: dict[str, Any], source: dict[str, Any], evaluation: dict[str, Any]
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    refs.extend(
        {
            "id": f"signal:{item}",
            "type": "signal",
            "source": "evidence.signal_ids",
            "summary": "Evidence signal attached to the TactSpec preview.",
        }
        for item in _list(evidence.get("signal_ids"))
        if _compact(item)
    )
    refs.extend(
        {
            "id": f"insight:{item}",
            "type": "insight",
            "source": "evidence.insight_ids",
            "summary": "Source insight attached to the TactSpec preview.",
        }
        for item in _list(evidence.get("insight_ids"))
        if _compact(item)
    )
    refs.extend(
        {
            "id": f"source_idea:{item}",
            "type": "source_idea",
            "source": "evidence.source_idea_ids",
            "summary": "Source idea linked to the TactSpec preview.",
        }
        for item in _list(evidence.get("source_idea_ids"))
        if _compact(item)
    )
    if _compact(evidence.get("rationale")):
        refs.append(
            {
                "id": "evidence.rationale",
                "type": "rationale",
                "source": "evidence.rationale",
                "summary": _compact(evidence.get("rationale")),
            }
        )
    if _compact(source.get("idea_id")) and not any(ref["id"] == f"source_idea:{source.get('idea_id')}" for ref in refs):
        refs.append(
            {
                "id": f"source_idea:{source.get('idea_id')}",
                "type": "source_idea",
                "source": "source.idea_id",
                "summary": "TactSpec source idea identifier.",
            }
        )
    if evaluation:
        refs.append(
            {
                "id": "evaluation",
                "type": "evaluation",
                "source": "evaluation",
                "summary": "Utility evaluation attached to the TactSpec preview.",
            }
        )
    return _dedupe_reference_dicts(refs)


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


def _evidence(values: list[str]) -> list[str]:
    return _dedupe([_compact(value) for value in values if _compact(value)])


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _dedupe(values: list[Any]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = _compact(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _dedupe_reference_dicts(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for item in items:
        ref_id = _compact(item.get("id"))
        if not ref_id or ref_id in seen:
            continue
        seen.add(ref_id)
        result.append(
            {
                "id": ref_id,
                "type": _compact(item.get("type")),
                "source": _compact(item.get("source")),
                "summary": _compact(item.get("summary")),
            }
        )
    return result


def _inline_list(values: Any) -> str:
    return "; ".join(_text(value) for value in _list(values) if _text(value))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _compact(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _term_label(term: str) -> str:
    labels = {
        "ai": "AI",
        "api": "API",
        "csv": "CSV",
        "gdpr": "GDPR",
        "hipaa": "HIPAA",
        "llm": "LLM",
        "oauth": "OAuth",
        "sms": "SMS",
    }
    return labels.get(term, term)
