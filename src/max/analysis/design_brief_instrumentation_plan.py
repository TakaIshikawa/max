"""Deterministic instrumentation plans for persisted design briefs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "max.design_brief.instrumentation_plan.v1"

_PRIVACY_TERMS = (
    "approval",
    "audit",
    "credential",
    "customer data",
    "employee",
    "legal",
    "message",
    "pii",
    "privacy",
    "regulated",
    "security",
    "sensitive",
    "slack",
    "soc2",
    "token",
)

_REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("id", "Design brief id is needed for stable event attribution."),
    ("title", "Title is needed to label the instrumentation plan."),
    ("workflow_context", "Workflow context is needed to name activation and retention triggers."),
    ("mvp_scope", "MVP scope is needed to derive first-value and progression events."),
    ("success_metric", "Success metric is needed to connect value events to product outcomes."),
    ("validation_plan", "Validation plan is needed to instrument validation decisions."),
    ("risks", "Risks are needed to define guardrail events and alerts."),
)


def build_design_brief_instrumentation_plan(design_brief: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-ready instrumentation plan from a persisted design brief payload."""
    brief_id = _clean(design_brief.get("id")) or "unknown-design-brief"
    title = _clean(design_brief.get("title")) or "Untitled Design Brief"
    workflow = _clean(design_brief.get("workflow_context")) or "target workflow"
    scope = _string_list(design_brief.get("mvp_scope"))
    risks = _string_list(design_brief.get("risks"))
    events = _events(design_brief, workflow=workflow, scope=scope, risks=risks)
    privacy_notes = _privacy_notes(design_brief, risks=risks, workflow=workflow)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.instrumentation_plan",
        "design_brief": {
            "id": brief_id,
            "title": title,
            "domain": _clean(design_brief.get("domain")),
            "theme": _clean(design_brief.get("theme")),
            "workflow_context": _clean(design_brief.get("workflow_context")),
            "success_metric": _clean(design_brief.get("success_metric")),
            "validation_plan": _clean(design_brief.get("validation_plan")),
        },
        "summary": {
            "event_count": len(events),
            "activation_event_count": _count_events(events, "activation"),
            "value_event_count": _count_events(events, "value"),
            "retention_event_count": _count_events(events, "retention"),
            "guardrail_event_count": _count_events(events, "guardrail"),
            "missing_input_count": len(_missing_inputs(design_brief)),
            "privacy_note_count": len(privacy_notes),
        },
        "events": events,
        "activation_funnel_steps": _activation_funnel_steps(
            design_brief, workflow=workflow, scope=scope
        ),
        "retention_checkpoints": _retention_checkpoints(design_brief, workflow=workflow),
        "guardrail_alerts": _guardrail_alerts(risks),
        "privacy_notes": privacy_notes,
        "missing_inputs": _missing_inputs(design_brief),
    }


def render_design_brief_instrumentation_plan(
    plan: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    """Render an instrumentation plan as Markdown or JSON."""
    if fmt == "json":
        return json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported instrumentation plan format: {fmt}")

    brief = plan["design_brief"]
    lines = [
        f"# Instrumentation Plan: {brief['title']}",
        "",
        f"Schema: `{plan['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        "",
        "## Events",
        "",
        "| Event | Category | Trigger | Required Properties | Privacy Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for event in plan["events"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{event['name']}`",
                    event["category"],
                    _escape_table(event["trigger"]),
                    _inline_code(event["required_properties"]),
                    _escape_table("; ".join(event["privacy_notes"]) or "None"),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Activation Funnel", ""])
    for step in plan["activation_funnel_steps"]:
        lines.extend(
            [
                f"- **{step['step']}**: {step['description']}",
                f"  Event: `{step['event_name']}`",
                f"  Properties: {_inline_code(step['required_properties'])}",
            ]
        )

    lines.extend(["", "## Retention Checkpoints", ""])
    for checkpoint in plan["retention_checkpoints"]:
        lines.extend(
            [
                f"- **{checkpoint['checkpoint']}**: {checkpoint['description']}",
                f"  Event: `{checkpoint['event_name']}`",
                f"  Window: {checkpoint['window']}",
            ]
        )

    lines.extend(["", "## Guardrail Alerts", ""])
    for alert in plan["guardrail_alerts"]:
        lines.extend(
            [
                f"- **{alert['name']}** (`{alert['severity']}`): {alert['condition']}",
                f"  Event: `{alert['event_name']}`",
                f"  Response: {alert['response']}",
            ]
        )

    lines.extend(["", "## Privacy Notes", ""])
    if plan["privacy_notes"]:
        lines.extend(f"- {note}" for note in plan["privacy_notes"])
    else:
        lines.append("- None")

    lines.extend(["", "## Missing Inputs", ""])
    if plan["missing_inputs"]:
        lines.extend(f"- **{item['field']}**: {item['reason']}" for item in plan["missing_inputs"])
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def write_design_brief_instrumentation_plan(
    path: Path,
    plan: dict[str, Any],
    *,
    fmt: str = "markdown",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_design_brief_instrumentation_plan(plan, fmt=fmt), encoding="utf-8")


def instrumentation_plan_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(_clean(design_brief.get("id")) or "design-brief")
    return f"{brief_id}-instrumentation-plan.{extension}"


def _events(
    design_brief: dict[str, Any],
    *,
    workflow: str,
    scope: list[str],
    risks: list[str],
) -> list[dict[str, Any]]:
    first_scope = scope[0] if scope else "primary MVP action"
    second_scope = scope[1] if len(scope) > 1 else "next MVP action"
    success_metric = _clean(design_brief.get("success_metric")) or "the target success metric"
    validation_plan = _clean(design_brief.get("validation_plan")) or "the validation plan"
    common_properties = ["brief_id", "account_id", "actor_role", "occurred_at"]
    privacy_notes = _event_privacy_notes(design_brief, risks=risks, workflow=workflow)
    events = [
        _event(
            "E1",
            "activation_started",
            "activation",
            f"A qualified actor starts {workflow}.",
            common_properties + ["workflow_context", "entry_point"],
            ["workflow_context", "specific_user"],
            privacy_notes,
        ),
        _event(
            "E2",
            "mvp_scope_item_completed",
            "activation",
            f"A qualified actor completes {first_scope}.",
            common_properties + ["mvp_scope_item", "time_from_start_minutes"],
            ["mvp_scope"],
            privacy_notes,
        ),
        _event(
            "E3",
            "first_value_reached",
            "value",
            f"The actor reaches a useful output tied to {success_metric}.",
            common_properties + ["mvp_scope_item", "value_claim", "time_to_value_minutes"],
            ["success_metric", "mvp_scope", "value_proposition"],
            privacy_notes,
        ),
        _event(
            "E4",
            "validation_decision_recorded",
            "value",
            f"A validation result is recorded from {validation_plan}.",
            common_properties + ["decision", "sample_size", "success_metric_result"],
            ["validation_plan", "success_metric"],
            privacy_notes,
        ),
        _event(
            "E5",
            "core_workflow_repeated",
            "retention",
            f"An activated account repeats {workflow} after first value.",
            common_properties + ["days_since_activation", "workflow_run_count"],
            ["workflow_context"],
            privacy_notes,
        ),
        _event(
            "E6",
            "retention_checkpoint_met",
            "retention",
            "An activated account meets a scheduled retention checkpoint.",
            common_properties + ["checkpoint_window", "qualified_repeat_count"],
            ["workflow_context", "success_metric"],
            privacy_notes,
        ),
        _event(
            "E7",
            "guardrail_alert_triggered",
            "guardrail",
            "A risk guardrail threshold is crossed during validation or pilot usage.",
            common_properties + ["guardrail_id", "severity", "risk_source", "mitigation_owner"],
            ["risks"],
            privacy_notes,
        ),
    ]
    if len(scope) > 1:
        events.append(
            _event(
                "E8",
                "mvp_scope_progressed",
                "value",
                f"An activated account progresses from {first_scope} to {second_scope}.",
                common_properties + ["from_scope_item", "to_scope_item", "progression_minutes"],
                ["mvp_scope"],
                privacy_notes,
            )
        )
    return events


def _activation_funnel_steps(
    design_brief: dict[str, Any],
    *,
    workflow: str,
    scope: list[str],
) -> list[dict[str, Any]]:
    first_scope = scope[0] if scope else "primary MVP action"
    return [
        {
            "step": "Qualified entry",
            "event_name": "activation_started",
            "description": f"Target users enter {workflow} from a known entry point.",
            "required_properties": ["brief_id", "account_id", "actor_role", "entry_point"],
            "source_fields": ["workflow_context", "specific_user"],
        },
        {
            "step": "MVP action completed",
            "event_name": "mvp_scope_item_completed",
            "description": f"Target users complete {first_scope}.",
            "required_properties": ["brief_id", "account_id", "mvp_scope_item"],
            "source_fields": ["mvp_scope"],
        },
        {
            "step": "First value",
            "event_name": "first_value_reached",
            "description": _clean(design_brief.get("success_metric"))
            or "Target users reach the first measurable value outcome.",
            "required_properties": ["brief_id", "account_id", "value_claim", "time_to_value_minutes"],
            "source_fields": ["success_metric", "value_proposition"],
        },
    ]


def _retention_checkpoints(
    design_brief: dict[str, Any],
    *,
    workflow: str,
) -> list[dict[str, Any]]:
    success_metric = _clean(design_brief.get("success_metric")) or "success metric"
    return [
        {
            "checkpoint": "Day 7 repeat",
            "event_name": "core_workflow_repeated",
            "window": "7 days after first value",
            "description": f"Activated accounts repeat {workflow} without implementation support.",
            "source_fields": ["workflow_context"],
        },
        {
            "checkpoint": "Day 30 qualified retention",
            "event_name": "retention_checkpoint_met",
            "window": "30 days after first value",
            "description": f"Activated accounts still satisfy {success_metric}.",
            "source_fields": ["success_metric"],
        },
    ]


def _guardrail_alerts(risks: list[str]) -> list[dict[str, Any]]:
    if not risks:
        return [
            {
                "id": "G1",
                "name": "uncaptured_risk_discovered",
                "event_name": "guardrail_alert_triggered",
                "condition": "A severe adoption, data, security, or workflow risk appears during validation.",
                "severity": "medium",
                "response": "Log the risk, add an owner, and rerun the instrumentation plan.",
                "source_fields": ["risks"],
            }
        ]
    alerts: list[dict[str, Any]] = []
    for index, risk in enumerate(risks[:4], start=1):
        severity = "high" if _contains_privacy_term(risk) else "medium"
        alerts.append(
            {
                "id": f"G{index}",
                "name": f"risk_threshold_crossed_{index}",
                "event_name": "guardrail_alert_triggered",
                "condition": f"Risk needs mitigation before expansion: {risk}.",
                "severity": severity,
                "response": "Pause affected rollout, assign mitigation owner, and record the next decision.",
                "source_fields": ["risks"],
            }
        )
    return alerts


def _privacy_notes(
    design_brief: dict[str, Any],
    *,
    risks: list[str],
    workflow: str,
) -> list[str]:
    notes = [
        "Use stable account and actor identifiers; do not store names, emails, chat transcripts, or raw customer content in event properties.",
        "Keep event payloads limited to ids, enums, timestamps, counters, and derived durations.",
    ]
    sensitive_hits = _sensitive_hits([workflow, *risks])
    if sensitive_hits:
        notes.append(
            "Privacy-sensitive terms detected in workflow or risks: "
            + ", ".join(sensitive_hits)
            + ". Review property names before implementation and redact free-text values."
        )
    if _clean(design_brief.get("validation_plan")):
        notes.append(
            "Validation notes should be linked by evidence id rather than copied into analytics events."
        )
    return notes


def _event_privacy_notes(
    design_brief: dict[str, Any],
    *,
    risks: list[str],
    workflow: str,
) -> list[str]:
    notes = ["No raw user content or customer text."]
    if _sensitive_hits([workflow, *risks]):
        notes.append("Hash or tokenize actor and account identifiers before export.")
    if _clean(design_brief.get("validation_plan")):
        notes.append("Store validation evidence references, not interview notes.")
    return notes


def _missing_inputs(design_brief: dict[str, Any]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for field, reason in _REQUIRED_FIELDS:
        value = design_brief.get(field)
        if field == "mvp_scope" or field == "risks":
            is_missing = not _string_list(value)
        else:
            is_missing = not _clean(value)
        if is_missing:
            missing.append({"field": field, "reason": reason})
    return missing


def _event(
    event_id: str,
    name: str,
    category: str,
    trigger: str,
    required_properties: list[str],
    source_fields: list[str],
    privacy_notes: list[str],
) -> dict[str, Any]:
    return {
        "id": event_id,
        "name": name,
        "category": category,
        "trigger": trigger,
        "required_properties": required_properties,
        "source_fields": source_fields,
        "privacy_notes": privacy_notes,
    }


def _count_events(events: list[dict[str, Any]], category: str) -> int:
    return sum(1 for event in events if event["category"] == category)


def _sensitive_hits(values: list[str]) -> list[str]:
    text = " ".join(values).lower()
    return [term for term in _PRIVACY_TERMS if term in text]


def _contains_privacy_term(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in _PRIVACY_TERMS)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_clean(value)] if _clean(value) else []
    if isinstance(value, dict):
        return [_clean(key) for key in value if _clean(key)]
    if isinstance(value, list | tuple | set):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _inline_code(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")
