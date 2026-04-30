"""Deterministic analytics event dictionaries for persisted design briefs."""

from __future__ import annotations

import json
from typing import Any

from max.store.db import Store

KIND = "max.design_brief.event_dictionary"
SCHEMA_VERSION = "max.design_brief.event_dictionary.v1"

CATEGORIES: tuple[str, ...] = (
    "activation",
    "engagement",
    "retention",
    "conversion",
    "guardrail",
)

PROPERTY_LIMIT = 8

_PROPERTY_PRIVACY_NOTES: tuple[tuple[str, str], ...] = (
    ("user", "Use an opaque stable user id; do not send names, emails, or profile text."),
    ("account", "Use an opaque stable account id; do not send customer names or billing details."),
    ("workflow", "Use controlled workflow labels; do not send raw task descriptions or customer content."),
    ("evidence", "Send evidence ids only; keep interviews, notes, transcripts, and files out of events."),
)


def build_design_brief_event_dictionary(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build event definitions and property contracts from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _event_context(design_brief, source_ideas)
    metrics = _linked_metrics(context)
    event_groups = _event_groups(context, metrics, source_idea_ids)
    events = [event for group in event_groups for event in group["events"]]
    property_contracts = _property_contracts(events)

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
            "event_count": len(events),
            "event_group_count": len(event_groups),
            "property_contract_count": len(property_contracts),
            "linked_metric_count": len(metrics),
            "max_properties_per_event": max(len(event["properties"]) for event in events),
            "fallbacks_used": context["fallbacks_used"],
        },
        "event_context": context,
        "linked_metrics": metrics,
        "event_groups": event_groups,
        "events": events,
        "property_contracts": property_contracts,
        "source_ideas": source_ideas,
    }


def render_design_brief_event_dictionary(report: dict[str, Any], fmt: str = "json") -> str:
    """Render the event dictionary as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported event dictionary format: {fmt}")

    brief = report["design_brief"]
    lines = [
        f"# Analytics Event Dictionary: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Linked Metrics",
        "",
        "| Metric | Definition | Source |",
        "| --- | --- | --- |",
    ]
    for metric in report["linked_metrics"]:
        lines.append(
            "| "
            f"`{metric['id']}` | {_escape_table(metric['definition'])} | "
            f"{_escape_table(', '.join(metric['source_fields']))} |"
        )

    for group in report["event_groups"]:
        lines.extend(
            [
                "",
                f"## {group['title']}",
                "",
                group["description"],
                "",
                "| Event | Trigger | Actor | Linked Metric | Priority | Properties |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for event in group["events"]:
            lines.append(
                "| "
                f"`{event['event_name']}` | {_escape_table(event['trigger'])} | "
                f"{_escape_table(event['actor'])} | `{event['linked_metric']}` | "
                f"{event['implementation_priority']} | {_inline_code(event['properties'])} |"
            )

    lines.extend(["", "## Property Contracts", ""])
    for contract in report["property_contracts"]:
        lines.extend(
            [
                f"### `{contract['name']}`",
                "",
                f"- Type: {contract['type']}",
                f"- Allowed values: {_inline_text(contract['allowed_values'])}",
                f"- Privacy: {contract['privacy_note']}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def event_dictionary_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for an analytics event dictionary export."""
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    title = _filename_part(str(design_brief.get("title") or "event-dictionary"))
    return f"{brief_id}-{title}-event-dictionary.{extension}"


def _event_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("account sponsor", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    scope = _string_list(design_brief.get("mvp_scope"))
    risks = _string_list(design_brief.get("risks"))
    evidence_ids = _evidence_ids(source_ideas)
    success_metric = _first_text(
        design_brief.get("success_metric"),
        design_brief.get("validation_plan"),
        "target success metric",
    )

    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "product_concept": _first_text(
            design_brief.get("merged_product_concept"),
            f"{title} for {workflow}",
        ),
        "success_metric": success_metric,
        "primary_scope": scope[0] if scope else f"first usable {title} workflow",
        "secondary_scope": scope[1] if len(scope) > 1 else "next MVP action",
        "validation_plan": _first_text(
            design_brief.get("validation_plan"),
            "Review telemetry against validation evidence.",
        ),
        "primary_risk": risks[0] if risks else "Uncaptured adoption, privacy, or workflow risk.",
        "evidence_ids": evidence_ids,
        "fallbacks_used": fallbacks,
    }


def _linked_metrics(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": "activation_rate",
            "definition": f"Share of qualified {context['target_user']} accounts that start {context['workflow_context']}.",
            "source_fields": ["specific_user", "workflow_context"],
        },
        {
            "id": "time_to_first_value",
            "definition": f"Median minutes from workflow start to completion of {context['primary_scope']}.",
            "source_fields": ["mvp_scope", "success_metric"],
        },
        {
            "id": "engagement_depth",
            "definition": "Number of meaningful MVP actions completed per activated account.",
            "source_fields": ["mvp_scope"],
        },
        {
            "id": "evidence_review_rate",
            "definition": "Share of validation or implementation sessions with at least one linked evidence reference.",
            "source_fields": ["validation_plan", "source_idea_ids"],
        },
        {
            "id": "qualified_retention_rate",
            "definition": "Share of activated accounts repeating the core workflow in the target retention window.",
            "source_fields": ["workflow_context", "success_metric"],
        },
        {
            "id": "conversion_rate",
            "definition": f"Share of qualified accounts that accept the pilot or satisfy {context['success_metric']}.",
            "source_fields": ["success_metric", "validation_plan"],
        },
        {
            "id": "guardrail_breach_rate",
            "definition": "Rate of risk, privacy, or data-quality guardrail events per activated account.",
            "source_fields": ["risks"],
        },
    ]


def _event_groups(
    context: dict[str, Any],
    metrics: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    metric_ids = {metric["id"] for metric in metrics}
    groups = [
        (
            "activation",
            "Activation Events",
            "Events that prove a qualified actor entered the target workflow and reached first value.",
            [
                _event(
                    "design_brief_workflow_started",
                    "activation",
                    f"{context['target_user']} starts {context['workflow_context']} from a qualified entry point.",
                    context["target_user"],
                    ["brief_id", "account_id", "user_id", "workflow_context", "entry_point", "occurred_at"],
                    "activation_rate",
                    source_idea_ids,
                    "P0",
                ),
                _event(
                    "design_brief_first_value_reached",
                    "activation",
                    f"An account completes {context['primary_scope']} and can evaluate {context['success_metric']}.",
                    context["target_user"],
                    ["brief_id", "account_id", "user_id", "workflow_context", "scope_item", "duration_minutes", "occurred_at"],
                    "time_to_first_value",
                    source_idea_ids,
                    "P0",
                ),
            ],
        ),
        (
            "engagement",
            "Engagement Events",
            "Events that describe meaningful use of MVP scope and validation evidence.",
            [
                _event(
                    "design_brief_scope_item_completed",
                    "engagement",
                    f"An activated account completes an MVP scope item such as {context['primary_scope']}.",
                    context["target_user"],
                    ["brief_id", "account_id", "user_id", "workflow_context", "scope_item", "scope_sequence", "occurred_at"],
                    "engagement_depth",
                    source_idea_ids,
                    "P0",
                ),
                _event(
                    "design_brief_evidence_referenced",
                    "engagement",
                    f"An actor links evidence while executing {context['validation_plan']}.",
                    context["target_user"],
                    ["brief_id", "account_id", "user_id", "evidence_id", "evidence_type", "workflow_context", "occurred_at"],
                    "evidence_review_rate",
                    source_idea_ids,
                    "P1",
                ),
            ],
        ),
        (
            "retention",
            "Retention Events",
            "Events that show repeated workflow use after first value.",
            [
                _event(
                    "design_brief_workflow_repeated",
                    "retention",
                    f"An activated account repeats {context['workflow_context']} after first value.",
                    context["target_user"],
                    ["brief_id", "account_id", "user_id", "workflow_context", "days_since_first_value", "repeat_count", "occurred_at"],
                    "qualified_retention_rate",
                    source_idea_ids,
                    "P0",
                ),
                _event(
                    "design_brief_retention_checkpoint_met",
                    "retention",
                    "An account meets the configured retention checkpoint for the success metric.",
                    context["buyer"],
                    ["brief_id", "account_id", "workflow_context", "checkpoint_window", "success_metric_state", "occurred_at"],
                    "qualified_retention_rate",
                    source_idea_ids,
                    "P1",
                ),
            ],
        ),
        (
            "conversion",
            "Conversion Events",
            "Events that capture pilot acceptance and success metric confirmation.",
            [
                _event(
                    "design_brief_pilot_accepted",
                    "conversion",
                    f"{context['buyer']} accepts a pilot or rollout decision for {context['product_concept']}.",
                    context["buyer"],
                    ["brief_id", "account_id", "user_id", "workflow_context", "conversion_stage", "occurred_at"],
                    "conversion_rate",
                    source_idea_ids,
                    "P0",
                ),
                _event(
                    "design_brief_success_metric_confirmed",
                    "conversion",
                    f"Validation confirms {context['success_metric']} for a qualified account or cohort.",
                    context["buyer"],
                    ["brief_id", "account_id", "workflow_context", "metric_result", "evidence_id", "occurred_at"],
                    "conversion_rate",
                    source_idea_ids,
                    "P0",
                ),
            ],
        ),
        (
            "guardrail",
            "Guardrail Events",
            "Events that prevent expansion when risk, privacy, or payload quality thresholds are crossed.",
            [
                _event(
                    "design_brief_risk_guardrail_triggered",
                    "guardrail",
                    f"A configured guardrail is crossed for risk: {context['primary_risk']}",
                    "system or product owner",
                    ["brief_id", "account_id", "workflow_context", "guardrail_type", "severity", "risk_id", "occurred_at"],
                    "guardrail_breach_rate",
                    source_idea_ids,
                    "P0",
                ),
                _event(
                    "design_brief_privacy_payload_rejected",
                    "guardrail",
                    "Instrumentation rejects a payload containing disallowed user, account, workflow, or evidence values.",
                    "analytics pipeline",
                    ["brief_id", "account_id", "workflow_context", "rejected_property", "rejection_reason", "occurred_at"],
                    "guardrail_breach_rate",
                    source_idea_ids,
                    "P0",
                ),
            ],
        ),
    ]
    result = [
        {
            "category": category,
            "title": title,
            "description": description,
            "linked_metrics": sorted(
                {event["linked_metric"] for event in events if event["linked_metric"] in metric_ids}
            ),
            "events": events,
        }
        for category, title, description, events in groups
    ]
    return result


def _event(
    event_name: str,
    category: str,
    trigger: str,
    actor: str,
    properties: list[str],
    linked_metric: str,
    source_idea_ids: list[str],
    implementation_priority: str,
) -> dict[str, Any]:
    bounded_properties = properties[:PROPERTY_LIMIT]
    return {
        "event_name": event_name,
        "category": category,
        "trigger": trigger,
        "actor": actor,
        "properties": bounded_properties,
        "privacy_notes": _event_privacy_notes(bounded_properties),
        "linked_metric": linked_metric,
        "source_idea_ids": source_idea_ids,
        "implementation_priority": implementation_priority,
    }


def _property_contracts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = sorted({property_name for event in events for property_name in event["properties"]})
    return [_property_contract(name) for name in names]


def _property_contract(name: str) -> dict[str, Any]:
    type_name = "string"
    allowed_values: list[str] = []
    if name.endswith("_at"):
        type_name = "timestamp"
    elif name.endswith("_minutes") or name.endswith("_count") or name == "scope_sequence":
        type_name = "number"
    elif name in {"severity"}:
        allowed_values = ["low", "medium", "high", "critical"]
    elif name == "guardrail_type":
        allowed_values = ["adoption", "privacy", "security", "workflow", "data_quality"]
    elif name == "conversion_stage":
        allowed_values = ["pilot_invited", "pilot_accepted", "pilot_expanded", "paid_converted"]
    elif name == "evidence_type":
        allowed_values = ["signal", "insight", "interview", "experiment", "brief_field"]
    return {
        "name": name,
        "type": type_name,
        "required": True,
        "allowed_values": allowed_values,
        "privacy_note": _property_privacy_note(name),
    }


def _event_privacy_notes(properties: list[str]) -> list[str]:
    notes = list(dict.fromkeys(_property_privacy_note(name) for name in properties))
    return [note for note in notes if note != "No special handling beyond standard event minimization."]


def _property_privacy_note(name: str) -> str:
    lowered = name.lower()
    for token, note in _PROPERTY_PRIVACY_NOTES:
        if token in lowered:
            return note
    if name in {"entry_point", "scope_item", "metric_result", "rejection_reason"}:
        return "Use bounded enums or derived values; do not send free-text customer content."
    return "No special handling beyond standard event minimization."


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


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if item.get("missing"):
            continue
        values.extend(_string_list(item.get(field)))
    return _dedupe_strings(values)


def _evidence_ids(source_ideas: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        ids.extend(_string_list(idea.get("evidence_signals")))
        ids.extend(_string_list(idea.get("inspiring_insights")))
    return _dedupe_strings(ids)


def _first_with_label(
    fallbacks: list[str], field: str, *candidates: tuple[Any, str]
) -> str:
    for value, label in candidates:
        text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list | tuple | set):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _inline_code(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def _inline_text(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "any bounded string"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
