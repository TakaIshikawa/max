"""Generate deterministic operational runbooks for TactSpec previews."""

from __future__ import annotations

import re
from typing import Any


OPERATIONAL_RUNBOOK_SCHEMA_VERSION = "max-operational-runbook/v1"

_INTEGRATION_TERMS = {
    "github": ("github",),
    "jira": ("jira", "atlassian"),
    "slack": ("slack",),
    "teams": ("teams", "microsoft teams"),
    "salesforce": ("salesforce",),
    "stripe": ("stripe",),
    "openai": ("openai", "llm", "embedding", "model"),
    "datadog": ("datadog",),
    "sentry": ("sentry",),
    "postgres": ("postgres", "postgresql"),
    "redis": ("redis",),
}


def generate_operational_runbook(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic post-launch operating guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"
    workflow = _workflow(project)
    stack = solution.get("suggested_stack")
    risks = _risks(spec, execution, evaluation)
    acceptance_criteria = _acceptance_criteria(spec)
    integrations = _integrations(spec, stack)

    return {
        "schema_version": OPERATIONAL_RUNBOOK_SCHEMA_VERSION,
        "kind": "max.operational_runbook",
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
        "service_overview": _service_overview(title, workflow, project, solution),
        "deploy_prerequisites": _deploy_prerequisites(execution, acceptance_criteria, risks),
        "configuration_env_vars": _configuration_env_vars(title, stack, integrations),
        "health_checks": _health_checks(workflow, integrations, acceptance_criteria),
        "rollback_triggers": _rollback_triggers(workflow, risks, evaluation),
        "incident_triage_steps": _incident_triage_steps(workflow, risks),
        "observability_checks": _observability_checks(workflow, integrations),
        "support_escalation": _support_escalation(project, solution),
        "post_incident_follow_up": _post_incident_follow_up(acceptance_criteria, risks),
    }


def render_operational_runbook_markdown(runbook: dict[str, Any]) -> str:
    """Render a generated operational runbook as a stable markdown handoff document."""
    overview = runbook.get("service_overview", {})
    source = runbook.get("source", {})
    title = _compact(overview.get("title")) or "TactSpec"

    lines = [
        f"# {title} Operational Runbook",
        "",
        f"- Schema version: {_text(runbook.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(overview.get('workflow_context'))}",
        f"- Target user: {_text(overview.get('target_user'))}",
        f"- Buyer: {_text(overview.get('buyer'))}",
        f"- Stack: {_text(overview.get('stack'))}",
        "",
    ]

    lines.extend(_section("Service Overview", _overview_lines(overview)))
    _extend_section(lines, "Deploy Prerequisites", runbook.get("deploy_prerequisites") or [], _render_task)
    _extend_section(
        lines,
        "Configuration and Environment Variables",
        runbook.get("configuration_env_vars") or [],
        _render_env_var,
    )
    _extend_section(lines, "Health Checks", runbook.get("health_checks") or [], _render_check)
    _extend_section(
        lines, "Rollback Triggers", runbook.get("rollback_triggers") or [], _render_trigger
    )
    _extend_section(
        lines, "Incident Triage Steps", runbook.get("incident_triage_steps") or [], _render_task
    )
    _extend_section(
        lines,
        "Observability Checks",
        runbook.get("observability_checks") or [],
        _render_check,
    )
    _extend_section(
        lines, "Support Escalation", runbook.get("support_escalation") or [], _render_escalation
    )
    _extend_section(
        lines,
        "Post-Incident Follow-Up",
        runbook.get("post_incident_follow_up") or [],
        _render_task,
    )
    return "\n".join(lines).rstrip() + "\n"


def _service_overview(
    title: str,
    workflow: str,
    project: dict[str, Any],
    solution: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": title,
        "summary": _compact(project.get("summary")) or "Operational guidance for the generated TactSpec.",
        "workflow_context": workflow,
        "target_user": _compact(project.get("specific_user") or project.get("target_users"))
        or "primary user",
        "buyer": _compact(project.get("buyer")) or "launch sponsor",
        "value_proposition": _compact(project.get("value_proposition")) or "validated MVP value path",
        "approach": _compact(solution.get("approach") or solution.get("technical_approach"))
        or "implementation approach is not specified",
        "stack": _stack_label(solution.get("suggested_stack")),
    }


def _deploy_prerequisites(
    execution: dict[str, Any],
    acceptance_criteria: list[dict[str, Any]],
    risks: list[str],
) -> list[dict[str, Any]]:
    items = [
        _task(
            "DEP1",
            "Release candidate is built from reviewed source and can be redeployed.",
            "release_owner",
            ["source_control", "deployment_pipeline"],
        ),
        _task(
            "DEP2",
            _compact(execution.get("validation_plan"))
            or "Representative validation run has passed for the primary workflow.",
            "qa_owner",
            ["execution.validation_plan"],
        ),
        _task(
            "DEP3",
            "Configuration baseline, secrets, and rollback command are recorded before launch.",
            "technical_owner",
            ["configuration_env_vars", "rollback_triggers"],
        ),
    ]
    if acceptance_criteria:
        items.append(
            _task(
                "DEP4",
                "Release-critical acceptance criteria are passing or explicitly waived.",
                "product_owner",
                ["acceptance_criteria"],
            )
        )
    if risks:
        items.append(
            _task(
                "DEP5",
                "Known launch risks have mitigations, monitors, and named owners.",
                "launch_owner",
                ["execution.risks", "evaluation.weaknesses"],
            )
        )
    return items


def _configuration_env_vars(
    title: str,
    stack: Any,
    integrations: list[str],
) -> list[dict[str, Any]]:
    service_prefix = _env_prefix(title)
    vars_ = [
        _env_var(
            "ENV1",
            "SERVICE_ENV",
            "Deployment environment name such as staging or production.",
            "required",
            "production",
            ["service_overview"],
        ),
        _env_var(
            "ENV2",
            "LOG_LEVEL",
            "Structured log verbosity for normal operation and incidents.",
            "optional",
            "INFO",
            ["observability_checks"],
        ),
        _env_var(
            "ENV3",
            f"{service_prefix}_FEATURE_ENABLED",
            "Feature flag or rollout switch used to pause new exposure quickly.",
            "required",
            "false until launch approval",
            ["rollback_triggers"],
        ),
    ]
    if isinstance(stack, dict):
        for key, value in sorted(stack.items()):
            if _compact(value):
                vars_.append(
                    _env_var(
                        f"ENV{len(vars_) + 1}",
                        f"{_env_prefix(key)}_COMPONENT",
                        f"Configured runtime component for {key}: {_compact(value)}.",
                        "optional",
                        _compact(value),
                        ["solution.suggested_stack"],
                    )
                )
    for integration in integrations:
        vars_.append(
            _env_var(
                f"ENV{len(vars_) + 1}",
                f"{_env_prefix(integration)}_API_TOKEN",
                f"Secret used by the {integration} integration if the implementation calls it.",
                "conditional",
                "managed secret",
                ["solution.technical_approach", "execution.risks"],
                secret=True,
            )
        )
    return _dedupe_env_vars(vars_)


def _health_checks(
    workflow: str,
    integrations: list[str],
    acceptance_criteria: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checks = [
        _check(
            "HC1",
            "Service liveness",
            "Runtime responds to a lightweight liveness check.",
            "HTTP 200, successful command exit, or equivalent runtime heartbeat.",
            "on_call_owner",
            ["SERVICE_ENV"],
        ),
        _check(
            "HC2",
            "Primary workflow readiness",
            f"A synthetic or fixture-backed check completes the {workflow} path.",
            "Expected output is produced without user-visible errors.",
            "qa_owner",
            ["acceptance_criteria"],
        ),
        _check(
            "HC3",
            "Error budget check",
            "Recent failure rate, timeout rate, and retry exhaustion stay inside rollout tolerance.",
            "<= 2% user-visible failure rate during staffed rollout windows.",
            "on_call_owner",
            ["workflow_failed", "primary_workflow_error_rate"],
        ),
    ]
    for index, integration in enumerate(integrations[:3], start=4):
        checks.append(
            _check(
                f"HC{index}",
                f"{integration.title()} dependency check",
                f"Confirm the {integration} dependency is reachable and credentials are valid.",
                "Dependency probe succeeds without using production customer data.",
                "technical_owner",
                [f"{_env_prefix(integration)}_API_TOKEN"],
            )
        )
    if acceptance_criteria:
        checks.append(
            _check(
                f"HC{len(checks) + 1}",
                "Acceptance criteria smoke check",
                "Run the smallest automated check that proves release-critical criteria still pass.",
                "All release-critical criteria pass or have a signed waiver.",
                "product_owner",
                ["acceptance_criteria_pass_rate"],
            )
        )
    return checks


def _rollback_triggers(
    workflow: str,
    risks: list[str],
    evaluation: dict[str, Any],
) -> list[dict[str, Any]]:
    triggers = [
        _trigger(
            "RB1",
            "Primary workflow failure",
            f"Users cannot complete the {workflow} path after deploy.",
            "critical",
            "Disable rollout flag and restore last known-good release.",
            ["HC2", "HC3"],
        ),
        _trigger(
            "RB2",
            "Data integrity concern",
            "Generated, stored, routed, or published data is corrupted, duplicated, or exposed to the wrong audience.",
            "critical",
            "Freeze writes, quarantine affected records, and restore from the pre-release baseline.",
            ["configuration_baseline", "audit_log"],
        ),
        _trigger(
            "RB3",
            "Operational SLO breach",
            "Error rate, latency, or dependency failures exceed the staffed rollout threshold.",
            "high",
            "Pause exposure and route incident owner to triage before retrying rollout.",
            ["HC1", "HC3"],
        ),
    ]
    if evaluation.get("recommendation") in {"no", "strong_no"}:
        triggers.append(
            _trigger(
                "RB4",
                "Evaluation recommendation blocks launch",
                "The attached utility evaluation recommends against proceeding.",
                "critical",
                "Stop launch until the recommendation changes or is explicitly waived.",
                ["evaluation.recommendation"],
            )
        )
    for index, risk in enumerate(risks[:3], start=len(triggers) + 1):
        triggers.append(
            _trigger(
                f"RB{index}",
                "Known risk materialized",
                risk,
                "high",
                "Apply the recorded mitigation or roll back if customer impact is confirmed.",
                ["execution.risks", "evaluation.weaknesses"],
            )
        )
    return triggers


def _incident_triage_steps(workflow: str, risks: list[str]) -> list[dict[str, Any]]:
    steps = [
        _task(
            "TRI1",
            f"Confirm whether the incident blocks the {workflow} path or only a secondary path.",
            "incident_commander",
            ["health_checks", "support_escalation"],
        ),
        _task(
            "TRI2",
            "Check recent deploys, configuration changes, feature flag changes, and dependency incidents.",
            "technical_owner",
            ["configuration_env_vars", "observability_checks"],
        ),
        _task(
            "TRI3",
            "Classify impact by affected users, records, integrations, and customer-visible symptoms.",
            "support_owner",
            ["service_overview", "health_checks"],
        ),
        _task(
            "TRI4",
            "Decide mitigation, rollback, or monitored recovery using the rollback triggers.",
            "incident_commander",
            ["rollback_triggers"],
        ),
    ]
    if risks:
        steps.append(
            _task(
                "TRI5",
                "Compare symptoms with known launch risks before opening new root-cause hypotheses.",
                "launch_owner",
                ["execution.risks", "evaluation.weaknesses"],
            )
        )
    return steps


def _observability_checks(workflow: str, integrations: list[str]) -> list[dict[str, Any]]:
    checks = [
        _check(
            "OBS1",
            "Workflow metrics",
            f"Dashboard shows starts, completions, failures, and latency for the {workflow} path.",
            "Metrics update during a staging or pilot run.",
            "engineering_owner",
            ["workflow_started", "workflow_completed", "workflow_failed"],
        ),
        _check(
            "OBS2",
            "Failure logs",
            "Structured failure logs include request id, failure stage, retryability, and sanitized error code.",
            "Every failed workflow attempt can be searched without exposing secrets or raw customer content.",
            "on_call_owner",
            ["workflow_failure_log"],
        ),
        _check(
            "OBS3",
            "Alert routing",
            "Rollback-level alerts route to the on-call owner and launch owner.",
            "Alert notification includes runbook link, last deploy, and current rollout state.",
            "launch_owner",
            ["rollback_triggers", "support_escalation"],
        ),
    ]
    if integrations:
        checks.append(
            _check(
                "OBS4",
                "Dependency visibility",
                f"Dashboards separate dependency errors for: {', '.join(integrations)}.",
                "Dependency failures are distinguishable from user validation errors.",
                "technical_owner",
                ["external_dependency_trace"],
            )
        )
    return checks


def _support_escalation(
    project: dict[str, Any],
    solution: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        _escalation(
            "ESC1",
            "product_owner",
            _compact(project.get("buyer")) or "launch sponsor",
            "Owns customer impact, value-path decisions, and acceptance waivers.",
            "Escalate when target users cannot complete the expected workflow.",
        ),
        _escalation(
            "ESC2",
            "technical_owner",
            _engineering_owner(solution),
            "Owns deploy, configuration, dependencies, and rollback execution.",
            "Escalate for runtime errors, dependency failures, or data integrity concerns.",
        ),
        _escalation(
            "ESC3",
            "support_owner",
            _compact(project.get("specific_user") or project.get("target_users")) or "customer support",
            "Owns user-facing updates, ticket correlation, and workaround communication.",
            "Escalate when customer reports indicate repeated or widening impact.",
        ),
        _escalation(
            "ESC4",
            "incident_commander",
            "release owner",
            "Coordinates severity, mitigation decision, rollback timing, and incident notes.",
            "Escalate when a rollback trigger is met or severity is unclear.",
        ),
    ]


def _post_incident_follow_up(
    acceptance_criteria: list[dict[str, Any]],
    risks: list[str],
) -> list[dict[str, Any]]:
    items = [
        _task(
            "PIR1",
            "Capture timeline, customer impact, root cause, mitigation, and rollback decision.",
            "incident_commander",
            ["incident_notes"],
        ),
        _task(
            "PIR2",
            "Add or update automated health checks, alerts, and runbook gaps found during response.",
            "technical_owner",
            ["health_checks", "observability_checks"],
        ),
        _task(
            "PIR3",
            "Review whether deploy prerequisites and rollback triggers need tighter thresholds.",
            "launch_owner",
            ["deploy_prerequisites", "rollback_triggers"],
        ),
    ]
    if acceptance_criteria:
        items.append(
            _task(
                "PIR4",
                "Update acceptance criteria or smoke coverage to prevent recurrence.",
                "product_owner",
                ["acceptance_criteria"],
            )
        )
    if risks:
        items.append(
            _task(
                "PIR5",
                "Promote any materialized risk into the risk register with owner and mitigation status.",
                "launch_owner",
                ["execution.risks", "risk_register"],
            )
        )
    return items


def _task(task_id: str, task: str, owner: str, derived_from: list[str]) -> dict[str, Any]:
    return {
        "id": task_id,
        "task": _compact(task),
        "owner": owner,
        "status": "pending",
        "derived_from": [item for item in derived_from if _compact(item)],
    }


def _env_var(
    var_id: str,
    name: str,
    description: str,
    required: str,
    example: str,
    derived_from: list[str],
    *,
    secret: bool = False,
) -> dict[str, Any]:
    return {
        "id": var_id,
        "name": name,
        "description": _compact(description),
        "required": required,
        "secret": secret,
        "example": _compact(example),
        "derived_from": [item for item in derived_from if _compact(item)],
    }


def _check(
    check_id: str,
    name: str,
    description: str,
    success_criteria: str,
    owner: str,
    signals: list[str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "description": _compact(description),
        "success_criteria": _compact(success_criteria),
        "owner": owner,
        "signals": [item for item in signals if _compact(item)],
    }


def _trigger(
    trigger_id: str,
    name: str,
    condition: str,
    severity: str,
    action: str,
    signals: list[str],
) -> dict[str, Any]:
    return {
        "id": trigger_id,
        "name": name,
        "condition": _compact(condition),
        "severity": severity,
        "action": _compact(action),
        "signals": [item for item in signals if _compact(item)],
    }


def _escalation(
    escalation_id: str,
    role: str,
    suggested_owner: str,
    responsibility: str,
    escalation_condition: str,
) -> dict[str, Any]:
    return {
        "id": escalation_id,
        "role": role,
        "suggested_owner": _compact(suggested_owner),
        "responsibility": _compact(responsibility),
        "escalation_condition": _compact(escalation_condition),
    }


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


def _integrations(spec: dict[str, Any], stack: Any) -> list[str]:
    text = _haystack(spec)
    values = []
    if isinstance(stack, dict):
        values.extend(_compact(value).lower() for _, value in sorted(stack.items()))
    joined = " ".join([text, *values])
    found = [
        name
        for name, terms in sorted(_INTEGRATION_TERMS.items())
        if any(term in joined for term in terms)
    ]
    return found


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


def _env_prefix(value: Any) -> str:
    compact = _compact(value).upper()
    compact = re.sub(r"[^A-Z0-9]+", "_", compact).strip("_")
    return compact or "SERVICE"


def _dedupe_env_vars(vars_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in vars_:
        deduped.setdefault(item["name"], item)
    return [
        {**item, "id": f"ENV{index}"}
        for index, item in enumerate(deduped.values(), start=1)
    ]


def _haystack(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_haystack(value[key]) for key in sorted(value))
    if isinstance(value, list | tuple):
        return " ".join(_haystack(item) for item in value)
    return _compact(value).lower()


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _section(title: str, body: list[str]) -> list[str]:
    return [f"## {title}", "", *body, ""]


def _overview_lines(overview: dict[str, Any]) -> list[str]:
    return [
        f"- Summary: {_text(overview.get('summary'))}",
        f"- Value proposition: {_text(overview.get('value_proposition'))}",
        f"- Approach: {_text(overview.get('approach'))}",
    ]


def _render_task(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Task: {_text(item.get('task'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_env_var(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Required: {_text(item.get('required'))}",
        f"- Secret: {_text(item.get('secret'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Example: {_text(item.get('example'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
    ]


def _render_check(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Success criteria: {_text(item.get('success_criteria'))}",
        f"- Signals: {_join_code(item.get('signals'))}",
    ]


def _render_trigger(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Condition: {_text(item.get('condition'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- Signals: {_join_code(item.get('signals'))}",
    ]


def _render_escalation(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        f"- Suggested owner: {_text(item.get('suggested_owner'))}",
        f"- Responsibility: {_text(item.get('responsibility'))}",
        f"- Escalation condition: {_text(item.get('escalation_condition'))}",
    ]


def _join_code(values: Any) -> str:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


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
