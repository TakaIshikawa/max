"""Generate deterministic service deprecation plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


SERVICE_DEPRECATION_PLAN_SCHEMA_VERSION = "max-service-deprecation-plan/v1"
KIND = "max.service_deprecation_plan"
SERVICE_DEPRECATION_PLAN_CSV_COLUMNS = (
    "section",
    "type",
    "source_idea_id",
    "source_status",
    "tact_spec_schema_version",
    "title",
    "workflow_context",
    "target_user",
    "buyer",
    "risk_level",
    "timeline",
    "item_id",
    "name",
    "owner",
    "phase",
    "severity",
    "description",
    "action",
    "promise",
    "trigger",
    "threshold",
    "derived_from",
    "evidence_reference_ids",
    "evidence_type",
    "evidence_summary",
)

_RISK_KEYWORDS = (
    "critical",
    "outage",
    "downtime",
    "data loss",
    "security",
    "privacy",
    "compliance",
    "migration",
    "breaking",
    "block",
)


def generate_service_deprecation_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into a deterministic deprecation plan."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    source = _dict(spec.get("source"))
    project = _dict(spec.get("project"))
    solution = _dict(spec.get("solution"))
    execution = _dict(spec.get("execution"))
    evaluation = _dict(spec.get("evaluation"))

    evidence_references = _evidence_references(spec)
    evidence_ids = [reference["id"] for reference in evidence_references]
    risks = _risks(spec, execution, evaluation)
    risk_level = _risk_level(risks, evaluation)
    timeline = _timeline(risk_level)
    workflow = _workflow(project, execution)
    stack = _stack_label(solution.get("suggested_stack"))
    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"

    context = {
        "title": title,
        "workflow_context": workflow,
        "target_user": _compact(project.get("specific_user") or project.get("target_users"))
        or "primary user",
        "buyer": _compact(project.get("buyer")) or "launch sponsor",
        "stack": stack,
        "approach": _compact(solution.get("approach")) or "planned solution",
        "technical_approach": _compact(solution.get("technical_approach"))
        or "primary service implementation",
        "validation_plan": _compact(execution.get("validation_plan"))
        or f"Validate replacement path for {workflow}.",
        "mvp_scope": [_compact(item) for item in _list(execution.get("mvp_scope")) if _compact(item)],
        "risks": risks,
        "risk_level": risk_level,
        "timeline": timeline,
        "recommendation": evaluation.get("recommendation") if evaluation else None,
        "overall_score": evaluation.get("overall_score") if evaluation else None,
        "evidence_ids": evidence_ids,
    }

    deprecation_candidates = _deprecation_candidates(context)
    user_impact = _user_impact(context)
    compatibility_promises = _compatibility_promises(context)
    migration_steps = _migration_steps(context)
    communications = _communications(context)
    kill_switches = _kill_switches(context)
    rollback_criteria = _rollback_criteria(context)

    return {
        "schema_version": SERVICE_DEPRECATION_PLAN_SCHEMA_VERSION,
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
            "evidence_reference_count": len(evidence_references),
        },
        "summary": {
            "title": title,
            "workflow_context": workflow,
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "stack": stack,
            "risk_level": risk_level,
            "recommended_timeline": timeline,
            "candidate_count": len(deprecation_candidates),
            "migration_step_count": len(migration_steps),
            "rollback_criterion_count": len(rollback_criteria),
            "recommendation": context["recommendation"],
            "overall_score": context["overall_score"],
        },
        "deprecation_candidates": deprecation_candidates,
        "user_impact": user_impact,
        "compatibility_promises": compatibility_promises,
        "migration_steps": migration_steps,
        "communications": communications,
        "kill_switches": kill_switches,
        "rollback_criteria": rollback_criteria,
        "evidence_references": evidence_references,
    }


def render_service_deprecation_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a service deprecation plan as deterministic Markdown."""
    summary = _dict(plan.get("summary"))
    source = _dict(plan.get("source"))
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Service Deprecation Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Kind: {_text(plan.get('kind'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Risk level: {_text(summary.get('risk_level'))}",
        f"- Recommended timeline: {_text(summary.get('recommended_timeline'))}",
        "",
    ]

    _extend_section(
        lines, "Deprecation Candidates", plan.get("deprecation_candidates") or [], _render_candidate
    )
    _extend_section(lines, "User Impact", plan.get("user_impact") or [], _render_impact)
    _extend_section(
        lines,
        "Compatibility Promises",
        plan.get("compatibility_promises") or [],
        _render_promise,
    )
    _extend_section(lines, "Migration Steps", plan.get("migration_steps") or [], _render_step)
    _extend_section(lines, "Communications", plan.get("communications") or [], _render_comm)
    _extend_section(lines, "Kill Switches", plan.get("kill_switches") or [], _render_switch)
    _extend_section(
        lines,
        "Rollback Criteria",
        plan.get("rollback_criteria") or [],
        _render_rollback,
    )
    _extend_section(
        lines,
        "Evidence References",
        plan.get("evidence_references") or [],
        _render_evidence,
    )

    return "\n".join(lines).rstrip() + "\n"


def render_service_deprecation_plan_csv(plan: dict[str, Any]) -> str:
    """Render a service deprecation plan as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=SERVICE_DEPRECATION_PLAN_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(plan or {}):
        writer.writerow(row)
    return output.getvalue()


def _deprecation_candidates(context: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        _candidate(
            "DEP1",
            "incumbent_workflow",
            f"Retire the existing {context['workflow_context']} path after the replacement proves stable.",
            "product_owner",
            "medium" if context["risk_level"] == "standard" else "high",
            ["project.workflow_context", "execution.validation_plan"],
            context,
        ),
        _candidate(
            "DEP2",
            "legacy_service_surface",
            f"Deprecate service behavior replaced by {context['technical_approach']}.",
            "engineering_owner",
            "high" if context["risk_level"] == "high" else "medium",
            ["solution.technical_approach", "solution.suggested_stack"],
            context,
        ),
    ]
    for index, scope_item in enumerate(context["mvp_scope"][:2], start=1):
        candidates.append(
            _candidate(
                f"DEP{index + 2}",
                f"mvp_scope_{index}",
                f"Mark legacy support for MVP scope item '{scope_item}' as deprecated once the migration step is complete.",
                "engineering_owner",
                "high" if context["risk_level"] == "high" else "medium",
                ["execution.mvp_scope"],
                context,
            )
        )
    return candidates


def _user_impact(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _item(
            "IMP1",
            "primary_user_transition",
            "user_impact",
            f"{context['target_user']} must move from the old path to the replacement path for {context['workflow_context']}.",
            "product_owner",
            severity="high" if context["risk_level"] == "high" else "medium",
            action=f"Provide guided migration, validation evidence, and support coverage through the {context['timeline']} window.",
            derived_from=["project.specific_user", "project.workflow_context"],
            context=context,
        ),
        _item(
            "IMP2",
            "buyer_expectations",
            "user_impact",
            f"{context['buyer']} needs clear timing, compatibility limits, and fallback options before removal.",
            "customer_owner",
            severity="medium",
            action="Confirm account-level readiness and exception handling before final shutdown.",
            derived_from=["project.buyer", "execution.risks"],
            context=context,
        ),
    ]


def _compatibility_promises(context: dict[str, Any]) -> list[dict[str, Any]]:
    support_window = "90 days" if context["risk_level"] == "standard" else "180 days"
    return [
        _promise(
            "COMP1",
            "versioned_transition_window",
            f"Maintain existing contracts, redirects, or adapters for {support_window} after notice.",
            "engineering_owner",
            ["solution.technical_approach", "execution.risks"],
            context,
        ),
        _promise(
            "COMP2",
            "data_and_output_continuity",
            f"Preserve user-visible outputs for {context['workflow_context']} during migration validation.",
            "qa_owner",
            ["execution.validation_plan", "project.workflow_context"],
            context,
        ),
        _promise(
            "COMP3",
            "exception_review",
            "Document approved exceptions with owner, expiration date, and rollback path before removing legacy support.",
            "product_owner",
            ["execution.risks"],
            context,
        ),
    ]


def _migration_steps(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _step(
            "MIG1",
            "inventory_consumers",
            "discovery",
            "Identify active users, integrations, dashboards, jobs, and data paths that still depend on the deprecated surface.",
            "engineering_owner",
            "Consumer inventory is complete and reviewed with support and product owners.",
            ["project.workflow_context", "solution.suggested_stack"],
            context,
        ),
        _step(
            "MIG2",
            "ship_replacement_path",
            "migration",
            f"Ship and document the replacement path using {context['technical_approach']}.",
            "engineering_owner",
            context["validation_plan"],
            ["solution.technical_approach", "execution.validation_plan"],
            context,
        ),
        _step(
            "MIG3",
            "parallel_run",
            "validation",
            f"Run legacy and replacement paths in parallel through the {context['timeline']} timeline.",
            "qa_owner",
            "Replacement output matches expected user-visible behavior without support escalation.",
            ["execution.validation_plan", "evaluation.overall_score"],
            context,
        ),
        _step(
            "MIG4",
            "remove_legacy_surface",
            "shutdown",
            "Disable the deprecated surface only after communications, compatibility promises, and rollback criteria are satisfied.",
            "release_owner",
            "Final removal is approved by product, engineering, and support owners.",
            ["communications", "rollback_criteria"],
            context,
        ),
    ]


def _communications(context: dict[str, Any]) -> list[dict[str, Any]]:
    cadence = "monthly" if context["risk_level"] == "standard" else "biweekly"
    return [
        _item(
            "COM1",
            "initial_notice",
            "communication",
            f"Announce planned deprecation for {context['workflow_context']} with timeline, reason, and migration owner.",
            "product_owner",
            action=f"Send notice at the start of the {context['timeline']} window.",
            derived_from=["project.workflow_context", "solution.approach"],
            context=context,
        ),
        _item(
            "COM2",
            "migration_reminders",
            "communication",
            f"Send {cadence} reminders with migration status, unresolved exceptions, and support route.",
            "customer_owner",
            action="Track acknowledged users and at-risk accounts until shutdown.",
            derived_from=["execution.risks", "project.buyer"],
            context=context,
        ),
        _item(
            "COM3",
            "final_shutdown_notice",
            "communication",
            "Send final notice only after replacement validation, kill switches, and rollback criteria are ready.",
            "release_owner",
            action="Include exact removal date, fallback instructions, and escalation contact.",
            derived_from=["execution.validation_plan", "rollback_criteria"],
            context=context,
        ),
    ]


def _kill_switches(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _switch(
            "KS1",
            "legacy_restore_flag",
            "Re-enable the deprecated path for impacted cohorts without redeploying.",
            "release_owner",
            "Unexpected migration defect affects active users.",
            ["execution.risks", "solution.technical_approach"],
            context,
        ),
        _switch(
            "KS2",
            "replacement_disable_flag",
            "Disable replacement-only behavior while preserving the current stable workflow.",
            "engineering_owner",
            "Replacement path violates validation expectations or creates support-impacting errors.",
            ["execution.validation_plan", "project.workflow_context"],
            context,
        ),
    ]


def _rollback_criteria(context: dict[str, Any]) -> list[dict[str, Any]]:
    high_risk = context["risk_level"] == "high"
    error_threshold = "any severity-1 incident or two severity-2 incidents" if high_risk else "one severity-1 incident"
    adoption_threshold = "95% acknowledged migration readiness" if high_risk else "80% acknowledged migration readiness"
    return [
        _criterion(
            "RB1",
            "incident_threshold",
            error_threshold,
            "Rollback to the legacy path and pause deprecation communications.",
            "release_owner",
            ["execution.risks", "evaluation.overall_score"],
            context,
        ),
        _criterion(
            "RB2",
            "readiness_threshold",
            f"Do not remove legacy support until {adoption_threshold} is confirmed for active users.",
            "Extend compatibility window and keep parallel run active.",
            "product_owner",
            ["project.specific_user", "communications"],
            context,
        ),
        _criterion(
            "RB3",
            "validation_regression",
            f"Rollback if replacement validation no longer satisfies: {context['validation_plan']}",
            "Restore previous service behavior and open a corrective action before resuming.",
            "qa_owner",
            ["execution.validation_plan"],
            context,
        ),
    ]


def _candidate(
    item_id: str,
    name: str,
    description: str,
    owner: str,
    severity: str,
    derived_from: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "severity": severity,
        "description": _compact(description),
        "recommended_timeline": context["timeline"],
        "derived_from": derived_from,
        "evidence_reference_ids": context["evidence_ids"],
    }


def _item(
    item_id: str,
    name: str,
    category: str,
    description: str,
    owner: str,
    *,
    severity: str = "medium",
    action: str,
    derived_from: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "category": category,
        "owner": owner,
        "severity": severity,
        "description": _compact(description),
        "action": _compact(action),
        "derived_from": derived_from,
        "evidence_reference_ids": context["evidence_ids"],
    }


def _promise(
    item_id: str,
    name: str,
    promise: str,
    owner: str,
    derived_from: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "promise": _compact(promise),
        "duration": context["timeline"],
        "derived_from": derived_from,
        "evidence_reference_ids": context["evidence_ids"],
    }


def _step(
    item_id: str,
    name: str,
    phase: str,
    action: str,
    owner: str,
    validation: str,
    derived_from: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "phase": phase,
        "owner": owner,
        "action": _compact(action),
        "validation": _compact(validation),
        "derived_from": derived_from,
        "evidence_reference_ids": context["evidence_ids"],
    }


def _switch(
    item_id: str,
    name: str,
    action: str,
    owner: str,
    trigger: str,
    derived_from: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "action": _compact(action),
        "trigger": _compact(trigger),
        "required_before_phase": "parallel_run" if context["risk_level"] == "standard" else "customer_notice",
        "derived_from": derived_from,
        "evidence_reference_ids": context["evidence_ids"],
    }


def _criterion(
    item_id: str,
    name: str,
    threshold: str,
    action: str,
    owner: str,
    derived_from: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "threshold": _compact(threshold),
        "action": _compact(action),
        "timeline": context["timeline"],
        "derived_from": derived_from,
        "evidence_reference_ids": context["evidence_ids"],
    }


def _evidence_references(spec: dict[str, Any]) -> list[dict[str, str]]:
    evidence = _dict(spec.get("evidence"))
    references: list[dict[str, str]] = []
    for insight_id in _list(evidence.get("insight_ids")):
        if _compact(insight_id):
            references.append(
                {
                    "id": f"insight:{insight_id}",
                    "type": "insight",
                    "summary": "Source insight attached to the TactSpec preview.",
                }
            )
    for signal_id in _list(evidence.get("signal_ids")):
        if _compact(signal_id):
            references.append(
                {
                    "id": f"signal:{signal_id}",
                    "type": "signal",
                    "summary": "Evidence signal attached to the TactSpec preview.",
                }
            )
    for idea_id in _list(evidence.get("source_idea_ids")):
        if _compact(idea_id):
            references.append(
                {
                    "id": f"idea:{idea_id}",
                    "type": "source_idea",
                    "summary": "Source idea linked to the TactSpec preview.",
                }
            )
    if _compact(evidence.get("rationale")):
        references.append(
            {
                "id": "spec:evidence_rationale",
                "type": "rationale",
                "summary": _compact(evidence.get("rationale")),
            }
        )
    if not references:
        references.append(
            {
                "id": "spec:fallback",
                "type": "fallback",
                "summary": "No evidence references were provided; service deprecation uses conservative planning defaults.",
            }
        )
    return _dedupe_by_id(references)


def _risks(spec: dict[str, Any], execution: dict[str, Any], evaluation: dict[str, Any]) -> list[str]:
    values = [
        *[_compact(item) for item in _list(execution.get("risks"))],
        *[_compact(item) for item in _list(spec.get("risks"))],
        *[_compact(item) for item in _list(evaluation.get("weaknesses"))],
    ]
    return [item for item in values if item]


def _risk_level(risks: list[str], evaluation: dict[str, Any]) -> str:
    score = _number(evaluation.get("overall_score"))
    risk_text = " ".join(risks).lower()
    keyword_hits = sum(1 for keyword in _RISK_KEYWORDS if keyword in risk_text)
    if score is not None and score < 60:
        return "high"
    if keyword_hits >= 2:
        return "high"
    if len(risks) >= 3:
        return "high"
    return "standard"


def _timeline(risk_level: str) -> str:
    if risk_level == "high":
        return "180-day notice, 60-day parallel run, executive rollback review"
    return "90-day notice, 30-day parallel run, product rollback review"


def _workflow(project: dict[str, Any], execution: dict[str, Any]) -> str:
    return (
        _compact(project.get("workflow_context"))
        or _first_string(execution.get("mvp_scope"))
        or _compact(project.get("summary"))
        or "primary workflow"
    )


def _stack_label(stack: Any) -> str:
    if isinstance(stack, dict) and stack:
        values = [f"{key}={stack[key]}" for key in sorted(stack) if _compact(stack[key])]
        if values:
            return ", ".join(values)
    return "unspecified"


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_candidate(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Timeline: {_text(item.get('recommended_timeline'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_impact(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Impact: {_text(item.get('description'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_promise(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Promise: {_text(item.get('promise'))}",
        f"- Duration: {_text(item.get('duration'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_step(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Phase: {_text(item.get('phase'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Validation: {_text(item.get('validation'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_comm(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Message: {_text(item.get('description'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_switch(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Required before phase: {_text(item.get('required_before_phase'))}",
        f"- Trigger: {_text(item.get('trigger'))}",
        f"- Action: {_text(item.get('action'))}",
    ]


def _render_rollback(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Threshold: {_text(item.get('threshold'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Timeline: {_text(item.get('timeline'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Type: {_text(item.get('type'))}",
        f"- Summary: {_text(item.get('summary'))}",
    ]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    summary = _dict(plan.get("summary"))
    evidence_ids = [item.get("id") for item in _dict_items(plan.get("evidence_references"))]
    rows = [
        _csv_row(
            plan,
            section="summary",
            type_="summary",
            item_id="summary",
            name=summary.get("title"),
            description=summary.get("recommended_timeline"),
            evidence_reference_ids=evidence_ids,
        )
    ]

    for section in (
        "deprecation_candidates",
        "user_impact",
        "compatibility_promises",
        "migration_steps",
        "communications",
        "kill_switches",
        "rollback_criteria",
    ):
        for item in _dict_items(plan.get(section)):
            rows.append(_csv_row_for_item(plan, section, item))

    for item in _dict_items(plan.get("evidence_references")):
        rows.append(
            _csv_row(
                plan,
                section="evidence_references",
                type_="evidence",
                item_id=item.get("id"),
                name=item.get("id"),
                evidence_reference_ids=[item.get("id")],
                evidence_type=item.get("type"),
                evidence_summary=item.get("summary"),
            )
        )
    return rows


def _csv_row_for_item(
    plan: dict[str, Any], section: str, item: dict[str, Any]
) -> dict[str, str]:
    type_by_section = {
        "deprecation_candidates": "candidate",
        "user_impact": "impact",
        "compatibility_promises": "promise",
        "migration_steps": "step",
        "communications": "communication",
        "kill_switches": "kill_switch",
        "rollback_criteria": "rollback",
    }
    return _csv_row(
        plan,
        section=section,
        type_=type_by_section.get(section, "item"),
        item_id=item.get("id"),
        name=item.get("name"),
        owner=item.get("owner"),
        phase=item.get("phase") or item.get("required_before_phase"),
        severity=item.get("severity"),
        description=item.get("description") or item.get("validation"),
        action=item.get("action"),
        promise=item.get("promise") or item.get("duration"),
        trigger=item.get("trigger"),
        threshold=item.get("threshold"),
        derived_from=item.get("derived_from"),
        evidence_reference_ids=item.get("evidence_reference_ids"),
    )


def _csv_row(
    plan: dict[str, Any],
    *,
    section: str,
    type_: str,
    item_id: Any = None,
    name: Any = None,
    owner: Any = None,
    phase: Any = None,
    severity: Any = None,
    description: Any = None,
    action: Any = None,
    promise: Any = None,
    trigger: Any = None,
    threshold: Any = None,
    derived_from: Any = None,
    evidence_reference_ids: Any = None,
    evidence_type: Any = None,
    evidence_summary: Any = None,
) -> dict[str, str]:
    source = _dict(plan.get("source"))
    summary = _dict(plan.get("summary"))
    values = {
        "section": section,
        "type": type_,
        "source_idea_id": source.get("idea_id"),
        "source_status": source.get("status"),
        "tact_spec_schema_version": source.get("tact_spec_schema_version"),
        "title": summary.get("title"),
        "workflow_context": summary.get("workflow_context"),
        "target_user": summary.get("target_user"),
        "buyer": summary.get("buyer"),
        "risk_level": summary.get("risk_level"),
        "timeline": summary.get("recommended_timeline"),
        "item_id": item_id,
        "name": name,
        "owner": owner,
        "phase": phase,
        "severity": severity,
        "description": description,
        "action": action,
        "promise": promise,
        "trigger": trigger,
        "threshold": threshold,
        "derived_from": derived_from,
        "evidence_reference_ids": evidence_reference_ids,
        "evidence_type": evidence_type,
        "evidence_summary": evidence_summary,
    }
    return {
        column: _csv_text(values.get(column))
        for column in SERVICE_DEPRECATION_PLAN_CSV_COLUMNS
    }


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _dedupe_by_id(references: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for reference in references:
        deduped.setdefault(reference["id"], reference)
    return list(deduped.values())


def _first_string(value: Any) -> str:
    for item in _list(value):
        text = _compact(item)
        if text:
            return text
    return ""


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _join_code(values: Any) -> str:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


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


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
