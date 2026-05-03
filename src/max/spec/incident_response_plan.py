"""Generate deterministic incident response plans for TactSpec previews."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any


INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION = "max-incident-response-plan/v1"
INCIDENT_RESPONSE_PLAN_CSV_COLUMNS = (
    "section",
    "type",
    "source_idea_id",
    "title",
    "item_id",
    "name",
    "category",
    "severity",
    "response_target",
    "owner",
    "escalation_condition",
    "trigger",
    "detection_signals",
    "response_steps",
    "response_refs",
    "incident_class_refs",
    "communication_timing",
    "message_guidance",
    "recovery_criteria",
    "status",
    "description",
    "recommendation",
)

_SECURITY_TERMS = (
    "authentication",
    "authorization",
    "credential",
    "customer data",
    "data leak",
    "exposure",
    "oauth",
    "permission",
    "pii",
    "privacy",
    "rbac",
    "secret",
    "sso",
    "token",
    "webhook signature",
)

_OPERATIONAL_TERMS = (
    "api outage",
    "availability",
    "dependency",
    "error",
    "failure",
    "latency",
    "outage",
    "rate limit",
    "reliability",
    "rollback",
    "slo",
    "timeout",
)

_INTEGRATION_TERMS = {
    "GitHub": ("github",),
    "GitLab": ("gitlab",),
    "Salesforce": ("salesforce",),
    "Slack": ("slack",),
    "Stripe": ("stripe",),
    "OpenAI": ("openai", "llm", "model"),
    "Datadog": ("datadog",),
    "Sentry": ("sentry",),
    "Postgres": ("postgres", "postgresql"),
    "Redis": ("redis",),
}


def generate_incident_response_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic production incident guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"
    workflow = _workflow(project)
    context = _incident_context(spec, project, solution, execution, evaluation)
    severity_levels = _severity_levels()
    incident_classes = _incident_classes(context)
    escalation_roles = _escalation_roles(project, solution, context)
    triage_steps = _triage_steps(workflow, context)
    containment_actions = _containment_actions(context)
    communication_checkpoints = _communication_checkpoints(context)
    postmortem_requirements = _postmortem_requirements(context)
    gaps = _gaps(context)

    return {
        "schema_version": INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION,
        "kind": "max.incident_response_plan",
        "source": {
            "system": source.get("system") or "max",
            "type": source.get("type") or "tact_spec_preview",
            "idea_id": source.get("idea_id"),
            "status": source.get("status"),
            "domain": source.get("domain"),
            "category": source.get("category"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(context["evidence_references"]),
        },
        "summary": {
            "title": title,
            "workflow_context": workflow,
            "target_user": _compact(project.get("specific_user") or project.get("target_users"))
            or "primary user",
            "buyer": _compact(project.get("buyer")) or "launch sponsor",
            "stack": _stack_label(solution.get("suggested_stack")),
            "risk_count": len(context["risks"]),
            "security_risk_count": len(context["security_risks"]),
            "operational_risk_count": len(context["operational_risks"]),
            "incident_class_count": len(incident_classes),
            "gap_count": len(gaps),
        },
        "incident_context": context,
        "severity_levels": severity_levels,
        "incident_classes": incident_classes,
        "escalation_roles": escalation_roles,
        "triage_steps": triage_steps,
        "containment_actions": containment_actions,
        "communication_checkpoints": communication_checkpoints,
        "postmortem_requirements": postmortem_requirements,
        "evidence_references": context["evidence_references"],
        "gaps": gaps,
    }


def render_incident_response_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a generated incident response plan as a stable markdown handoff document."""
    summary = plan.get("summary", {})
    source = plan.get("source", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Incident Response Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Evidence references: {_text(source.get('evidence_reference_count'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Incident classes: {_text(summary.get('incident_class_count'))}",
        f"- Gaps: {_text(summary.get('gap_count'))}",
        "",
    ]

    _extend_section(lines, "Severity Levels", plan.get("severity_levels") or [], _render_severity)
    _extend_section(lines, "Incident Classes", plan.get("incident_classes") or [], _render_class)
    _extend_section(lines, "Escalation Roles", plan.get("escalation_roles") or [], _render_role)
    _extend_section(lines, "Triage Steps", plan.get("triage_steps") or [], _render_task)
    _extend_section(
        lines, "Containment Actions", plan.get("containment_actions") or [], _render_action
    )
    _extend_section(
        lines,
        "Customer Communication Checkpoints",
        plan.get("communication_checkpoints") or [],
        _render_checkpoint,
    )
    _extend_section(
        lines,
        "Postmortem Requirements",
        plan.get("postmortem_requirements") or [],
        _render_requirement,
    )
    _extend_section(
        lines, "Evidence References", _reference_items(plan.get("evidence_references") or []), _render_ref
    )
    _extend_section(lines, "Gaps", plan.get("gaps") or [], _render_gap)

    return "\n".join(lines).rstrip() + "\n"


def render_incident_response_plan_csv(plan: dict[str, Any]) -> str:
    """Render a generated incident response plan as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output, fieldnames=INCIDENT_RESPONSE_PLAN_CSV_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in _csv_rows(plan):
        writer.writerow(row)
    return output.getvalue()


def render_incident_response_plan_json(plan: dict[str, Any]) -> str:
    """Render a generated incident response plan as deterministic JSON."""
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def _incident_context(
    spec: dict[str, Any],
    project: dict[str, Any],
    solution: dict[str, Any],
    execution: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    text = _haystack(spec)
    risks = _risks(spec, execution, evaluation)
    security_risks = [risk for risk in risks if _contains_any(risk.lower(), _SECURITY_TERMS)]
    operational_risks = [risk for risk in risks if _contains_any(risk.lower(), _OPERATIONAL_TERMS)]
    integrations = _integrations(spec, solution.get("suggested_stack"))
    evidence_references = _evidence_refs(spec)

    return {
        "workflow_context": _workflow(project),
        "risks": risks,
        "security_risks": security_risks,
        "operational_risks": operational_risks,
        "integrations": integrations,
        "evidence_references": evidence_references,
        "mentions_security": bool(security_risks) or _contains_any(text, _SECURITY_TERMS),
        "mentions_operations": bool(operational_risks) or _contains_any(text, _OPERATIONAL_TERMS),
        "mentions_customer_data": _contains_any(
            text, ("customer", "user data", "personal data", "pii", "email", "export")
        ),
        "mentions_communication": _contains_any(text, ("slack", "email", "ticket", "support")),
        "mentions_observability": _contains_any(
            text, ("alert", "audit", "datadog", "dashboard", "log", "metric", "monitor", "sentry")
        ),
        "has_validation_plan": bool(_compact(execution.get("validation_plan"))),
        "has_acceptance_criteria": bool(_acceptance_criteria(spec)),
    }


def _severity_levels() -> list[dict[str, Any]]:
    return [
        _severity("SEV1", "critical", "Customer data exposure, unauthorized access, or complete workflow outage.", "15 minutes", "incident_commander"),
        _severity("SEV2", "high", "Major degradation, repeated failed workflow runs, or dependency outage with customer impact.", "30 minutes", "incident_commander"),
        _severity("SEV3", "medium", "Limited incident with workaround, non-critical integration failure, or contained data integrity concern.", "1 business hour", "technical_owner"),
        _severity("SEV4", "low", "Internal-only issue, cosmetic defect, or monitored anomaly without customer impact.", "1 business day", "technical_owner"),
    ]


def _incident_classes(context: dict[str, Any]) -> list[dict[str, Any]]:
    classes = [
        _incident_class(
            "INC1",
            "workflow_outage",
            "Primary workflow outage",
            "SEV1",
            f"Users cannot complete the {context['workflow_context']} path.",
            ["triage_steps", "containment_actions", "execution.validation_plan"],
            ["TRI1", "TRI2", "CON1"],
        ),
        _incident_class(
            "INC2",
            "data_integrity",
            "Data integrity or misrouting",
            "SEV1",
            "Generated, stored, routed, or published data is corrupted, duplicated, stale, or sent to the wrong destination.",
            ["project.workflow_context", "acceptance_criteria"],
            ["TRI3", "CON2"],
        ),
        _incident_class(
            "INC3",
            "dependency_failure",
            "External dependency failure",
            "SEV2",
            _dependency_description(context),
            ["solution.suggested_stack", "execution.risks"],
            ["TRI2", "CON3"],
        ),
    ]
    if context["mentions_security"]:
        classes.append(
            _incident_class(
                "INC4",
                "security_incident",
                "Security, credential, or access incident",
                "SEV1",
                _risk_description(
                    context["security_risks"],
                    "Authentication, authorization, secrets, webhook, or customer data controls may be compromised.",
                ),
                ["execution.risks", "evaluation.weaknesses", "security_review"],
                ["TRI4", "CON4", "COM2"],
            )
        )
    if context["mentions_operations"]:
        classes.append(
            _incident_class(
                "INC5",
                "operational_degradation",
                "Operational reliability degradation",
                "SEV2",
                _risk_description(
                    context["operational_risks"],
                    "Latency, errors, dependency instability, or SLO drift threatens the launch workflow.",
                ),
                ["execution.risks", "evaluation.weaknesses", "slo_plan", "observability_plan"],
                ["TRI1", "TRI2", "CON1", "COM1"],
            )
        )
    return classes


def _escalation_roles(
    project: dict[str, Any],
    solution: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    roles = [
        _role("ROL1", "incident_commander", "release owner", "Own severity, timeline, mitigation decisions, and handoff notes.", "SEV1 or unclear impact"),
        _role("ROL2", "technical_owner", _engineering_owner(solution), "Own deploy state, logs, dependency status, rollback, and containment execution.", "Runtime, deploy, data, or integration symptoms"),
        _role("ROL3", "product_owner", _compact(project.get("buyer")) or "launch sponsor", "Own customer impact decisions, acceptance waivers, and priority tradeoffs.", "Customer-visible workflow impact"),
        _role("ROL4", "support_owner", _compact(project.get("specific_user") or project.get("target_users")) or "customer support", "Own customer reports, ticket correlation, and approved user-facing updates.", "Incoming customer reports or external communication"),
    ]
    if context["mentions_security"]:
        roles.append(
            _role("ROL5", "security_owner", "security reviewer", "Own credential rotation, access review, data exposure assessment, and security signoff.", "Security, privacy, credential, or authorization concern")
        )
    return roles


def _triage_steps(workflow: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    steps = [
        _task("TRI1", f"Confirm whether the incident blocks the {workflow} path or only a secondary path.", "incident_commander", ["project.workflow_context", "severity_levels"]),
        _task("TRI2", "Check recent deploys, feature flags, configuration changes, dependency status, alerts, and logs.", "technical_owner", ["solution.suggested_stack", "observability_plan"]),
        _task("TRI3", "Classify affected users, records, integrations, requests, and customer-visible symptoms.", "support_owner", ["project.target_users", "acceptance_criteria"]),
        _task("TRI4", "Decide whether security, privacy, credential, or authorization handling is required before normal recovery.", "security_owner", ["execution.risks", "security_review"]),
        _task("TRI5", "Record timeline, current severity, customer impact, owner, and next update time in the incident notes.", "incident_commander", ["communication_checkpoints"]),
    ]
    if context["risks"]:
        steps.append(
            _task("TRI6", "Compare symptoms with known unit, evaluation, and spec risks before opening new root-cause hypotheses.", "incident_commander", ["execution.risks", "evaluation.weaknesses"])
        )
    return steps


def _containment_actions(context: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        _action("CON1", "pause_exposure", "Disable rollout flag, pause scheduled jobs, or route traffic away from the affected path.", "technical_owner", "SEV1 or SEV2 workflow impact", ["INC1", "INC5"]),
        _action("CON2", "protect_data_integrity", "Freeze writes, quarantine suspect records, preserve audit logs, and prevent downstream publication until scope is known.", "technical_owner", "Incorrect, duplicated, exposed, or misrouted data", ["INC2"]),
        _action("CON3", "degrade_dependency", "Switch to retry-safe degraded mode, queue work, or disable the failing integration until the dependency recovers.", "technical_owner", "External service errors or timeouts", ["INC3"]),
    ]
    if context["mentions_security"]:
        actions.append(
            _action("CON4", "secure_access", "Rotate affected credentials, revoke suspicious sessions, disable compromised webhooks, and restrict privileged access.", "security_owner", "Credential, authorization, webhook, or data exposure concern", ["INC4"])
        )
    return actions


def _communication_checkpoints(context: dict[str, Any]) -> list[dict[str, Any]]:
    checkpoints = [
        _checkpoint("COM1", "initial_internal_update", "Within severity response target", "incident_commander", "Post severity, impact, owner, mitigation, and next update time to the internal incident channel.", ["severity_levels", "triage_steps"]),
        _checkpoint("COM2", "customer_impact_decision", "After impact and containment are known", "product_owner", "Decide whether customer-facing communication is required and approve wording before sending.", ["project.buyer", "support_owner"]),
        _checkpoint("COM3", "customer_update", "Every 60 minutes for SEV1/SEV2 until stable", "support_owner", "Send concise status, workaround, next update time, and resolution notice through the approved support path.", ["project.target_users", "incident_classes"]),
        _checkpoint("COM4", "resolution_notice", "After monitoring confirms recovery", "incident_commander", "Record final customer impact, mitigation, residual risk, and postmortem owner.", ["postmortem_requirements"]),
    ]
    if context["mentions_security"]:
        checkpoints.append(
            _checkpoint("COM5", "security_notification_review", "Before external security or privacy statements", "security_owner", "Review exposure scope, notification obligations, credential rotation status, and evidence preservation.", ["INC4", "CON4"])
        )
    return checkpoints


def _postmortem_requirements(context: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = [
        _requirement("PM1", "timeline", "Document detection time, severity changes, key decisions, containment, recovery, and resolution time.", "incident_commander", "SEV1, SEV2, or repeated SEV3"),
        _requirement("PM2", "customer_impact", "Quantify affected users, records, integrations, requests, duration, and customer communications.", "product_owner", "Any customer-visible impact"),
        _requirement("PM3", "root_cause", "Identify root cause, contributing factors, missing alerts, missing tests, and why existing controls did not prevent the incident.", "technical_owner", "Every incident class"),
        _requirement("PM4", "follow_up_actions", "Create owned corrective actions for tests, monitors, runbook updates, acceptance criteria, and risk register changes.", "incident_commander", "Every postmortem"),
    ]
    if context["mentions_security"]:
        requirements.append(
            _requirement("PM5", "security_evidence", "Attach access logs, audit events, credential rotation evidence, exposure assessment, and security signoff.", "security_owner", "Security, privacy, credential, or authorization incident")
        )
    return requirements


def _gaps(context: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = []
    if not context["has_validation_plan"]:
        gaps.append(_gap("GAP1", "missing_validation_plan", "No validation plan is attached, so incident responders lack a known-good workflow check.", "qa_owner", "Add a minimal validation runbook for the primary workflow."))
    if not context["has_acceptance_criteria"]:
        gaps.append(_gap("GAP2", "missing_acceptance_criteria", "No acceptance criteria are attached for post-incident recovery validation.", "product_owner", "Define recovery-critical functional and non-functional acceptance criteria."))
    if not context["mentions_observability"]:
        gaps.append(_gap("GAP3", "missing_observability", "The spec does not name alerts, logs, metrics, dashboards, or audit events.", "technical_owner", "Add observability signals for detection, triage, and recovery confirmation."))
    if not context["evidence_references"]:
        gaps.append(_gap("GAP4", "missing_evidence_references", "No source evidence references are attached for incident assumptions and customer impact review.", "product_owner", "Attach signal, insight, or source idea identifiers to the spec."))
    if context["mentions_security"] and not context["mentions_customer_data"]:
        gaps.append(_gap("GAP5", "missing_data_exposure_scope", "Security risk is present but customer data exposure scope is not explicit.", "security_owner", "Define affected data classes, audit logs, notification threshold, and credential rotation evidence."))
    return gaps


def _severity(
    severity_id: str,
    level: str,
    definition: str,
    response_target: str,
    owner: str,
) -> dict[str, Any]:
    return {
        "id": severity_id,
        "level": level,
        "definition": _compact(definition),
        "response_target": response_target,
        "default_owner": owner,
    }


def _incident_class(
    class_id: str,
    category: str,
    title: str,
    default_severity: str,
    trigger: str,
    evidence: list[str],
    response_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": class_id,
        "category": category,
        "title": title,
        "default_severity": default_severity,
        "trigger": _compact(trigger),
        "evidence": [item for item in evidence if _compact(item)],
        "response_refs": [item for item in response_refs if _compact(item)],
    }


def _role(
    role_id: str,
    role: str,
    suggested_owner: str,
    responsibility: str,
    escalation_condition: str,
) -> dict[str, Any]:
    return {
        "id": role_id,
        "role": role,
        "suggested_owner": _compact(suggested_owner),
        "responsibility": _compact(responsibility),
        "escalation_condition": _compact(escalation_condition),
    }


def _task(task_id: str, task: str, owner: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "id": task_id,
        "task": _compact(task),
        "owner": owner,
        "status": "pending",
        "evidence": [item for item in evidence if _compact(item)],
    }


def _action(
    action_id: str,
    category: str,
    action: str,
    owner: str,
    trigger: str,
    incident_class_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": action_id,
        "category": category,
        "action": _compact(action),
        "owner": owner,
        "trigger": _compact(trigger),
        "incident_class_refs": incident_class_refs,
    }


def _checkpoint(
    checkpoint_id: str,
    name: str,
    timing: str,
    owner: str,
    message_guidance: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "id": checkpoint_id,
        "name": name,
        "timing": _compact(timing),
        "owner": owner,
        "message_guidance": _compact(message_guidance),
        "evidence": [item for item in evidence if _compact(item)],
    }


def _requirement(
    requirement_id: str,
    category: str,
    requirement: str,
    owner: str,
    applies_when: str,
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "category": category,
        "requirement": _compact(requirement),
        "owner": owner,
        "applies_when": _compact(applies_when),
    }


def _gap(
    gap_id: str,
    category: str,
    description: str,
    owner: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "id": gap_id,
        "category": category,
        "description": _compact(description),
        "owner": owner,
        "recommendation": _compact(recommendation),
    }


def _risks(
    spec: dict[str, Any],
    execution: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    risks = [_compact(item) for item in _list(execution.get("risks")) if _compact(item)]
    risk_register = spec.get("risk_register") if isinstance(spec.get("risk_register"), dict) else {}
    for risk in _list(risk_register.get("risks")):
        if isinstance(risk, dict):
            text = _compact(risk.get("description") or risk.get("title"))
            if text:
                risks.append(text)
    risks.extend(_compact(item) for item in _list(evaluation.get("weaknesses")) if _compact(item))
    return list(dict.fromkeys(risks))


def _acceptance_criteria(spec: dict[str, Any]) -> list[dict[str, Any]]:
    criteria = (
        spec.get("acceptance_criteria") if isinstance(spec.get("acceptance_criteria"), dict) else {}
    )
    items: list[dict[str, Any]] = []
    for key in ("functional_criteria", "non_functional_criteria"):
        for item in _list(criteria.get(key)):
            if isinstance(item, dict):
                items.append(item)
    return items


def _integrations(spec: dict[str, Any], stack: Any) -> list[str]:
    text = _haystack(spec)
    if isinstance(stack, dict):
        text = " ".join([text, *[_compact(value).lower() for value in stack.values()]])
    return [
        name
        for name, terms in sorted(_INTEGRATION_TERMS.items())
        if any(term in text for term in terms)
    ]


def _evidence_refs(spec: dict[str, Any]) -> list[str]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    refs: list[str] = []
    refs.extend(f"insight:{item}" for item in _list(evidence.get("insight_ids")) if _compact(item))
    refs.extend(f"signal:{item}" for item in _list(evidence.get("signal_ids")) if _compact(item))
    refs.extend(
        f"source_idea:{item}" for item in _list(evidence.get("source_idea_ids")) if _compact(item)
    )
    refs.extend(_compact(item) for item in _list(evidence.get("links")) if _compact(item))
    return list(dict.fromkeys(refs))


def _dependency_description(context: dict[str, Any]) -> str:
    if context["integrations"]:
        return f"External service failure affects: {', '.join(context['integrations'])}."
    return "A required API, vendor, queue, database, or infrastructure dependency blocks the workflow."


def _risk_description(risks: list[str], fallback: str) -> str:
    if not risks:
        return fallback
    return "Known risks: " + "; ".join(risks[:3])


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


def _engineering_owner(solution: dict[str, Any]) -> str:
    stack = solution.get("suggested_stack")
    if isinstance(stack, dict) and stack:
        language = _compact(stack.get("language"))
        framework = _compact(stack.get("framework"))
        label = " / ".join(item for item in (language, framework) if item)
        if label:
            return f"{label} service owner"
    return "service owner"


def _reference_items(refs: list[Any]) -> list[dict[str, Any]]:
    return [{"id": f"REF{index}", "reference": _compact(ref)} for index, ref in enumerate(refs, start=1)]


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_severity(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('level'))}",
        f"- Definition: {_text(item.get('definition'))}",
        f"- Response target: {_text(item.get('response_target'))}",
        f"- Default owner: {_text(item.get('default_owner'))}",
    ]


def _render_class(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        f"- Category: {_text(item.get('category'))}",
        f"- Default severity: {_text(item.get('default_severity'))}",
        f"- Trigger: {_text(item.get('trigger'))}",
        f"- Evidence: {_join_code(item.get('evidence'))}",
        f"- Response refs: {_join_code(item.get('response_refs'))}",
    ]


def _render_role(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        f"- Suggested owner: {_text(item.get('suggested_owner'))}",
        f"- Responsibility: {_text(item.get('responsibility'))}",
        f"- Escalation condition: {_text(item.get('escalation_condition'))}",
    ]


def _render_task(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Task: {_text(item.get('task'))}",
        f"- Evidence: {_join_code(item.get('evidence'))}",
    ]


def _render_action(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Trigger: {_text(item.get('trigger'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Incident classes: {_join_code(item.get('incident_class_refs'))}",
    ]


def _render_checkpoint(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Timing: {_text(item.get('timing'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Message guidance: {_text(item.get('message_guidance'))}",
        f"- Evidence: {_join_code(item.get('evidence'))}",
    ]


def _render_requirement(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Applies when: {_text(item.get('applies_when'))}",
        f"- Requirement: {_text(item.get('requirement'))}",
    ]


def _render_ref(item: dict[str, Any]) -> list[str]:
    return [f"### {_text(item.get('id'))}", f"- Reference: `{_text(item.get('reference'))}`"]


def _render_gap(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('category'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Recommendation: {_text(item.get('recommendation'))}",
    ]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for item in _dict_items(plan.get("severity_levels")):
        rows.append(
            _csv_row(
                plan,
                section="severity_levels",
                type_="severity",
                item_id=item.get("id"),
                name=item.get("level"),
                severity=item.get("id"),
                response_target=item.get("response_target"),
                owner=item.get("default_owner"),
                description=item.get("definition"),
            )
        )

    for item in _dict_items(plan.get("incident_classes")):
        rows.append(
            _csv_row(
                plan,
                section="incident_classes",
                type_="scenario",
                item_id=item.get("id"),
                name=item.get("title"),
                category=item.get("category"),
                severity=item.get("default_severity"),
                trigger=item.get("trigger"),
                detection_signals=item.get("evidence"),
                response_refs=item.get("response_refs"),
            )
        )

    for item in _dict_items(plan.get("escalation_roles")):
        rows.append(
            _csv_row(
                plan,
                section="escalation_roles",
                type_="owner",
                item_id=item.get("id"),
                name=item.get("role"),
                owner=item.get("suggested_owner"),
                escalation_condition=item.get("escalation_condition"),
                response_steps=item.get("responsibility"),
            )
        )

    for item in _dict_items(plan.get("triage_steps")):
        rows.append(
            _csv_row(
                plan,
                section="triage_steps",
                type_="response_step",
                item_id=item.get("id"),
                owner=item.get("owner"),
                detection_signals=item.get("evidence"),
                response_steps=item.get("task"),
                status=item.get("status"),
            )
        )

    for item in _dict_items(plan.get("containment_actions")):
        rows.append(
            _csv_row(
                plan,
                section="containment_actions",
                type_="response_step",
                item_id=item.get("id"),
                name=item.get("category"),
                category=item.get("category"),
                owner=item.get("owner"),
                trigger=item.get("trigger"),
                response_steps=item.get("action"),
                incident_class_refs=item.get("incident_class_refs"),
            )
        )

    for item in _dict_items(plan.get("communication_checkpoints")):
        rows.append(
            _csv_row(
                plan,
                section="communication_checkpoints",
                type_="communication",
                item_id=item.get("id"),
                name=item.get("name"),
                owner=item.get("owner"),
                detection_signals=item.get("evidence"),
                communication_timing=item.get("timing"),
                message_guidance=item.get("message_guidance"),
            )
        )

    for item in _dict_items(plan.get("postmortem_requirements")):
        rows.append(
            _csv_row(
                plan,
                section="postmortem_requirements",
                type_="recovery_criterion",
                item_id=item.get("id"),
                name=item.get("category"),
                category=item.get("category"),
                owner=item.get("owner"),
                recovery_criteria=item.get("requirement"),
                trigger=item.get("applies_when"),
            )
        )

    for item in _dict_items(plan.get("gaps")):
        rows.append(
            _csv_row(
                plan,
                section="gaps",
                type_="gap",
                item_id=item.get("id"),
                name=item.get("category"),
                category=item.get("category"),
                owner=item.get("owner"),
                description=item.get("description"),
                recommendation=item.get("recommendation"),
            )
        )

    return rows


def _csv_row(
    plan: dict[str, Any],
    *,
    section: str,
    type_: str,
    item_id: Any = None,
    name: Any = None,
    category: Any = None,
    severity: Any = None,
    response_target: Any = None,
    owner: Any = None,
    escalation_condition: Any = None,
    trigger: Any = None,
    detection_signals: Any = None,
    response_steps: Any = None,
    response_refs: Any = None,
    incident_class_refs: Any = None,
    communication_timing: Any = None,
    message_guidance: Any = None,
    recovery_criteria: Any = None,
    status: Any = None,
    description: Any = None,
    recommendation: Any = None,
) -> dict[str, str]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    values = {
        "section": section,
        "type": type_,
        "source_idea_id": source.get("idea_id"),
        "title": summary.get("title"),
        "item_id": item_id,
        "name": name,
        "category": category,
        "severity": severity,
        "response_target": response_target,
        "owner": owner,
        "escalation_condition": escalation_condition,
        "trigger": trigger,
        "detection_signals": detection_signals,
        "response_steps": response_steps,
        "response_refs": response_refs,
        "incident_class_refs": incident_class_refs,
        "communication_timing": communication_timing,
        "message_guidance": message_guidance,
        "recovery_criteria": recovery_criteria,
        "status": status,
        "description": description,
        "recommendation": recommendation,
    }
    return {column: _csv_text(values.get(column)) for column in INCIDENT_RESPONSE_PLAN_CSV_COLUMNS}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_text(key)}: {_csv_text(item)}"
            for key, item in sorted(value.items())
            if _csv_text(item)
        )
    if isinstance(value, list | tuple | set):
        return "; ".join(_csv_text(item) for item in value if _csv_text(item))
    return _compact(value)


def _join_code(values: Any) -> str:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _haystack(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_haystack(value[key]) for key in sorted(value))
    if isinstance(value, list | tuple):
        return " ".join(_haystack(item) for item in value)
    return _compact(value).lower()


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
    return str(value).strip()
