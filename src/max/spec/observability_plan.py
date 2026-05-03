"""Generate deterministic observability plans for TactSpec previews."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any


OBSERVABILITY_PLAN_SCHEMA_VERSION = "max-observability-plan/v1"

OBSERVABILITY_PLAN_CSV_COLUMNS = [
    "section",
    "type",
    "source_idea_id",
    "title",
    "workflow_context",
    "item_id",
    "name",
    "category",
    "severity",
    "owner",
    "suggested_owner",
    "cadence",
    "field",
    "description",
    "definition",
    "target",
    "threshold",
    "response",
    "panels",
    "signals",
    "derived_from",
    "evidence_references",
    "status",
]


def generate_observability_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into deterministic instrumentation guidance."""
    spec = tact_spec or {}
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}
    evidence_references = _evidence_references(spec)
    evidence_ids = [reference["id"] for reference in evidence_references]
    acceptance_criteria = _acceptance_criteria(spec)
    risks = _risks(execution, spec)

    workflow = _workflow(project)
    title = _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec"
    summary = {
        "title": title,
        "target_user": _compact(project.get("specific_user") or project.get("target_users"))
        or "primary user",
        "buyer": _compact(project.get("buyer")) or "launch sponsor",
        "workflow_context": workflow,
        "stack": _stack_label(solution.get("suggested_stack")),
        "recommendation": evaluation.get("recommendation") if evaluation else None,
        "overall_score": evaluation.get("overall_score") if evaluation else None,
        "acceptance_criteria_count": len(acceptance_criteria),
        "risk_count": len(risks),
        "evidence_reference_count": len(evidence_references),
    }

    return {
        "schema_version": OBSERVABILITY_PLAN_SCHEMA_VERSION,
        "kind": "max.observability_plan",
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
        "summary": summary,
        "metrics": _metrics(
            workflow, project, evaluation, acceptance_criteria, risks, evidence_ids
        ),
        "events": _events(workflow, execution, evidence_ids),
        "logs": _logs(workflow, risks, evidence_ids),
        "traces": _traces(workflow, solution, evidence_ids),
        "slos": _slos(workflow, evidence_ids),
        "alerts": _alerts(workflow, risks, evidence_ids),
        "dashboards": _dashboards(workflow, evidence_ids),
        "owners": _owners(project, solution),
        "rollout_validation_checks": _rollout_validation_checks(
            workflow, acceptance_criteria, risks, evidence_ids
        ),
        "evidence_references": evidence_references,
    }


def render_observability_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a generated observability plan as a stable markdown handoff document."""
    summary = plan.get("summary", {})
    source = plan.get("source", {})
    title = _compact(summary.get("title")) or "TactSpec"

    lines = [
        f"# {title} Observability Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Stack: {_text(summary.get('stack'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
    ]

    _extend_section(lines, "Metrics", plan.get("metrics") or [], _render_signal)
    _extend_section(lines, "Events", plan.get("events") or [], _render_signal)
    _extend_section(lines, "Logs", plan.get("logs") or [], _render_signal)
    _extend_section(lines, "Traces", plan.get("traces") or [], _render_signal)
    _extend_section(lines, "SLOs", plan.get("slos") or [], _render_signal)
    _extend_section(lines, "Alerts", plan.get("alerts") or [], _render_alert)
    _extend_section(lines, "Dashboards", plan.get("dashboards") or [], _render_dashboard)
    _extend_section(lines, "Owners", plan.get("owners") or [], _render_owner)
    _extend_section(
        lines,
        "Rollout Validation Checks",
        plan.get("rollout_validation_checks") or [],
        _render_check,
    )
    _extend_section(
        lines, "Evidence References", plan.get("evidence_references") or [], _render_evidence
    )

    return "\n".join(lines).rstrip() + "\n"


def render_observability_plan_csv(plan: dict[str, Any]) -> str:
    """Render a generated observability plan as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output, fieldnames=OBSERVABILITY_PLAN_CSV_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for row in _csv_rows(plan or {}):
        writer.writerow(row)
    return output.getvalue()


def _metrics(
    workflow: str,
    project: dict[str, Any],
    evaluation: dict[str, Any],
    acceptance_criteria: list[dict[str, Any]],
    risks: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    metrics = [
        _signal(
            "MET1",
            "primary_workflow_success_rate",
            "service_health",
            f"Percentage of {workflow} attempts that finish with the expected user-visible result.",
            "count(workflow_completed) / count(workflow_started)",
            ">= 95% during pilot cohorts",
            "engineering_owner",
            ["workflow_context", "project.value_proposition"],
            evidence_ids,
        ),
        _signal(
            "MET2",
            "primary_workflow_latency_p95_ms",
            "service_health",
            f"95th percentile latency for the {workflow} path.",
            "p95(workflow_duration_ms)",
            "<= 2000 ms until a product-specific target is set",
            "engineering_owner",
            ["solution.suggested_stack"],
            evidence_ids,
        ),
        _signal(
            "MET3",
            "primary_workflow_error_rate",
            "service_health",
            "User-visible failures, validation failures, and unhandled exceptions divided by workflow starts.",
            "count(workflow_failed) / count(workflow_started)",
            "<= 2% during rollout",
            "on_call_owner",
            ["execution.risks"],
            evidence_ids,
        ),
        _signal(
            "MET4",
            "qualified_activation_count",
            "product_analytics",
            "Number of target users who complete the MVP value path at least once.",
            "count_distinct(user_id where workflow_completed and qualified_user=true)",
            ">= 1 qualified pilot user before widening rollout",
            "product_owner",
            ["project.specific_user", "project.target_users"],
            evidence_ids,
        ),
    ]
    if project.get("value_proposition"):
        metrics.append(
            _signal(
                "MET5",
                "value_proposition_realization_rate",
                "product_analytics",
                f"Share of completed workflows with evidence of value: {_compact(project.get('value_proposition'))}.",
                "count(value_confirmed) / count(workflow_completed)",
                "Reviewed weekly during validation",
                "product_owner",
                ["project.value_proposition", "execution.validation_plan"],
                evidence_ids,
            )
        )
    if evaluation.get("weaknesses"):
        metrics.append(
            _signal(
                "MET6",
                "evaluation_weakness_resolution_rate",
                "validation",
                "Share of evaluation weaknesses with a passing test, accepted non-goal, or captured follow-up.",
                "count(resolved_weaknesses) / count(evaluation_weaknesses)",
                "100% before broad launch",
                "product_owner",
                ["evaluation.weaknesses"],
                evidence_ids,
            )
        )
    if acceptance_criteria:
        metrics.append(
            _signal(
                "MET7",
                "acceptance_criteria_pass_rate",
                "quality",
                "Share of functional and non-functional acceptance criteria passing in the release candidate.",
                "count(passing_acceptance_criteria) / count(all_acceptance_criteria)",
                "100% for release-critical criteria",
                "qa_owner",
                ["acceptance_criteria"],
                evidence_ids,
            )
        )
    if risks:
        metrics.append(
            _signal(
                "MET8",
                "open_launch_risk_count",
                "risk",
                "Count of launch-critical risks without mitigation, acceptance, or rollback handling.",
                "count(open_risks where launch_critical=true)",
                "0 before widening rollout",
                "launch_owner",
                ["execution.risks", "risk_register"],
                evidence_ids,
            )
        )
    return metrics


def _events(
    workflow: str, execution: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    events = [
        _signal(
            "EV1",
            "workflow_started",
            "product_analytics",
            f"Emitted when a target user starts the {workflow} path.",
            "Properties: user_id, account_id, source, workflow_context, spec_idea_id.",
            "Every public entry point emits this once per attempt.",
            "product_analytics_owner",
            ["project.workflow_context"],
            evidence_ids,
        ),
        _signal(
            "EV2",
            "workflow_completed",
            "product_analytics",
            "Emitted when the MVP produces the expected user-visible output.",
            "Properties: user_id, duration_ms, output_type, acceptance_criterion_ids.",
            "Completion semantics match acceptance criteria.",
            "product_analytics_owner",
            ["acceptance_criteria"],
            evidence_ids,
        ),
        _signal(
            "EV3",
            "workflow_failed",
            "product_analytics",
            "Emitted when the workflow cannot complete or returns a user-visible error.",
            "Properties: user_id, error_code, failure_stage, retryable.",
            "Every failed attempt has a stable failure_stage and error_code.",
            "engineering_owner",
            ["execution.risks"],
            evidence_ids,
        ),
        _signal(
            "EV4",
            "validation_feedback_submitted",
            "validation",
            "Emitted when pilot feedback or validation evidence is captured.",
            "Properties: user_id, evidence_type, outcome, source_reference_id.",
            _compact(execution.get("validation_plan"))
            or "Capture validation outcome for the primary workflow.",
            "research_owner",
            ["execution.validation_plan", "evidence"],
            evidence_ids,
        ),
    ]
    for index, scope_item in enumerate(_list(execution.get("mvp_scope"))[:3], start=1):
        events.append(
            _signal(
                f"EV{index + 4}",
                f"mvp_scope_{index}_completed",
                "product_analytics",
                f"Emitted when this MVP scope item is completed: {_compact(scope_item)}",
                "Properties: user_id, scope_item, duration_ms, result.",
                "Scope completion can be tied back to rollout validation.",
                "product_analytics_owner",
                ["execution.mvp_scope"],
                evidence_ids,
            )
        )
    return events


def _logs(workflow: str, risks: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    logs = [
        _signal(
            "LOG1",
            "workflow_request_log",
            "structured_log",
            f"Info log for each {workflow} request or command execution.",
            "Fields: request_id, user_id_hash, workflow_stage, input_shape, duration_ms.",
            "No secrets, raw customer content, or personal data are logged by default.",
            "engineering_owner",
            ["project.workflow_context", "solution.technical_approach"],
            evidence_ids,
        ),
        _signal(
            "LOG2",
            "workflow_failure_log",
            "structured_log",
            "Error log for failed workflow attempts with stable failure classification.",
            "Fields: request_id, error_code, failure_stage, retryable, stack_component.",
            "Every workflow_failed event has a matching failure log.",
            "on_call_owner",
            ["execution.risks"],
            evidence_ids,
        ),
        _signal(
            "LOG3",
            "validation_decision_log",
            "audit_log",
            "Audit log for rollout validation, acceptance decisions, and explicit risk acceptance.",
            "Fields: decision_id, actor_role, criterion_id, risk_id, outcome, source_reference_id.",
            "All launch gates are explainable from structured logs.",
            "launch_owner",
            ["acceptance_criteria", "execution.validation_plan"],
            evidence_ids,
        ),
    ]
    if risks:
        logs.append(
            _signal(
                "LOG4",
                "risk_indicator_log",
                "structured_log",
                f"Warning log when known risks appear during the {workflow} path.",
                "Fields: request_id, risk_id, risk_indicator, mitigation_state.",
                "Risk indicators are searchable during pilot review.",
                "launch_owner",
                ["execution.risks", "risk_register"],
                evidence_ids,
            )
        )
    return logs


def _traces(
    workflow: str, solution: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    stack = solution.get("suggested_stack")
    components = _stack_components(stack)
    return [
        _signal(
            "TR1",
            "primary_workflow_trace",
            "distributed_trace",
            f"Trace the {workflow} request from public entry point through the value-producing operation.",
            f"Required spans: entrypoint, validation, {', '.join(components[:3]) if components else 'core_operation'}, response.",
            "All spans share request_id and spec_idea_id.",
            "engineering_owner",
            ["solution.suggested_stack", "solution.technical_approach"],
            evidence_ids,
        ),
        _signal(
            "TR2",
            "external_dependency_trace",
            "distributed_trace",
            "Trace calls to external APIs, data stores, model providers, queues, or integrations.",
            "Required span tags: dependency, operation, status_code, timeout_ms, retry_count.",
            "Dependency spans distinguish user errors from service failures.",
            "engineering_owner",
            ["solution.suggested_stack", "execution.risks"],
            evidence_ids,
        ),
    ]


def _slos(workflow: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _signal(
            "SLO1",
            "primary_workflow_availability",
            "slo",
            f"The {workflow} path is available to qualified pilot users.",
            "Successful health checks and non-5xx workflow attempts over total attempts.",
            ">= 99% during staffed rollout windows",
            "on_call_owner",
            ["project.workflow_context"],
            evidence_ids,
        ),
        _signal(
            "SLO2",
            "primary_workflow_latency",
            "slo",
            "Qualified users receive a response fast enough to continue their workflow.",
            "p95(workflow_duration_ms)",
            "<= 2 seconds until a domain-specific threshold is validated",
            "engineering_owner",
            ["solution.suggested_stack"],
            evidence_ids,
        ),
        _signal(
            "SLO3",
            "primary_workflow_success",
            "slo",
            "Qualified attempts complete without user-visible failure.",
            "count(workflow_completed) / count(workflow_started)",
            ">= 95% during validation",
            "product_owner",
            ["acceptance_criteria", "execution.validation_plan"],
            evidence_ids,
        ),
    ]


def _alerts(workflow: str, risks: list[str], evidence_ids: list[str]) -> list[dict[str, Any]]:
    alerts = [
        _alert(
            "AL1",
            "High workflow error rate",
            f"{workflow} error rate exceeds 5% for 15 minutes or 10 attempts.",
            "page",
            "on_call_owner",
            "Inspect workflow_failure_log, recent deploys, and rollback triggers.",
            ["MET3", "LOG2"],
            evidence_ids,
        ),
        _alert(
            "AL2",
            "Latency SLO burn",
            "p95 latency exceeds the SLO target for two consecutive windows.",
            "ticket",
            "engineering_owner",
            "Review primary_workflow_trace and dependency spans for the slow stage.",
            ["MET2", "TR1", "TR2"],
            evidence_ids,
        ),
        _alert(
            "AL3",
            "Activation drop",
            "Qualified activation count or workflow completion rate drops below the pilot target.",
            "ticket",
            "product_owner",
            "Review event funnel, validation feedback, and acceptance criteria regressions.",
            ["MET1", "MET4", "EV2"],
            evidence_ids,
        ),
    ]
    if risks:
        alerts.append(
            _alert(
                "AL4",
                "Known risk indicator observed",
                f"Risk indicator appears in {workflow} logs during rollout: {_compact(risks[0])}.",
                "ticket",
                "launch_owner",
                "Open the mitigation decision, decide rollback or acceptance, and attach validation evidence.",
                ["MET8", "LOG4"],
                evidence_ids,
            )
        )
    return alerts


def _dashboards(workflow: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "DB1",
            "title": "Service Health",
            "description": f"Operational health for the {workflow} path.",
            "owner": "engineering_owner",
            "panels": [
                "primary_workflow_success_rate",
                "primary_workflow_latency_p95_ms",
                "primary_workflow_error_rate",
                "external dependency errors by component",
            ],
            "evidence_reference_ids": evidence_ids,
        },
        {
            "id": "DB2",
            "title": "Product Adoption",
            "description": "Pilot usage, activation, completion, and value realization.",
            "owner": "product_owner",
            "panels": [
                "workflow_started to workflow_completed funnel",
                "qualified_activation_count",
                "value_proposition_realization_rate",
                "validation_feedback_submitted outcomes",
            ],
            "evidence_reference_ids": evidence_ids,
        },
        {
            "id": "DB3",
            "title": "Rollout Validation",
            "description": "Acceptance criteria status, open risks, alerts, and launch gate evidence.",
            "owner": "launch_owner",
            "panels": [
                "acceptance_criteria_pass_rate",
                "open_launch_risk_count",
                "active alerts by severity",
                "evidence references attached to validation decisions",
            ],
            "evidence_reference_ids": evidence_ids,
        },
    ]


def _owners(project: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "OWN1",
            "role": "product_owner",
            "suggested_owner": _compact(project.get("buyer")) or "launch sponsor",
            "responsibility": "Owns product analytics, activation targets, and value validation.",
        },
        {
            "id": "OWN2",
            "role": "engineering_owner",
            "suggested_owner": _engineering_owner(solution),
            "responsibility": "Owns metric, log, trace, and dashboard implementation.",
        },
        {
            "id": "OWN3",
            "role": "on_call_owner",
            "suggested_owner": "release engineer or service owner",
            "responsibility": "Owns alert routing, incident response, and rollback escalation.",
        },
        {
            "id": "OWN4",
            "role": "research_owner",
            "suggested_owner": _compact(project.get("specific_user")) or "validation owner",
            "responsibility": "Owns pilot feedback and evidence capture.",
        },
    ]


def _rollout_validation_checks(
    workflow: str,
    acceptance_criteria: list[dict[str, Any]],
    risks: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    checks = [
        _check(
            "RVC1",
            "Metrics emit for success, failure, latency, and activation in a staging or pilot run.",
            "engineering_owner",
            ["MET1", "MET2", "MET3", "MET4"],
            evidence_ids,
        ),
        _check(
            "RVC2",
            "Workflow events support a complete started to completed or failed funnel.",
            "product_owner",
            ["EV1", "EV2", "EV3"],
            evidence_ids,
        ),
        _check(
            "RVC3",
            "Failure logs and traces can identify the failing stage for the primary workflow.",
            "on_call_owner",
            ["LOG2", "TR1"],
            evidence_ids,
        ),
        _check(
            "RVC4",
            f"Dashboard panels show {workflow} health and validation status before launch review.",
            "launch_owner",
            ["DB1", "DB2", "DB3"],
            evidence_ids,
        ),
    ]
    if acceptance_criteria:
        checks.append(
            _check(
                "RVC5",
                "Acceptance criteria have pass/fail status and are referenced by workflow completion events.",
                "qa_owner",
                ["MET7", "EV2"],
                evidence_ids,
            )
        )
    if risks:
        checks.append(
            _check(
                "RVC6",
                "Known risks have monitors, explicit acceptance, or rollback triggers before rollout expands.",
                "launch_owner",
                ["MET8", "AL4", "LOG4"],
                evidence_ids,
            )
        )
    return checks


def _signal(
    signal_id: str,
    name: str,
    category: str,
    description: str,
    definition: str,
    target: str,
    owner: str,
    derived_from: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": signal_id,
        "name": name,
        "category": category,
        "description": _compact(description),
        "definition": _compact(definition),
        "target": _compact(target),
        "owner": owner,
        "derived_from": [item for item in derived_from if _compact(item)],
        "evidence_reference_ids": evidence_ids,
    }


def _alert(
    alert_id: str,
    name: str,
    threshold: str,
    severity: str,
    owner: str,
    response: str,
    signal_ids: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": alert_id,
        "name": name,
        "threshold": _compact(threshold),
        "severity": severity,
        "owner": owner,
        "response": _compact(response),
        "signal_ids": signal_ids,
        "evidence_reference_ids": evidence_ids,
    }


def _check(
    check_id: str,
    check: str,
    owner: str,
    signal_ids: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "check": _compact(check),
        "owner": owner,
        "status": "pending",
        "signal_ids": signal_ids,
        "evidence_reference_ids": evidence_ids,
    }


def _evidence_references(spec: dict[str, Any]) -> list[dict[str, str]]:
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
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
                "summary": "No evidence references were provided; observability recommendations use conservative fallback instrumentation.",
            }
        )
    return _dedupe_by_id(references)


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


def _risks(execution: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    risks = [_compact(item) for item in _list(execution.get("risks")) if _compact(item)]
    risk_register = spec.get("risk_register") if isinstance(spec.get("risk_register"), dict) else {}
    for risk in _list(risk_register.get("risks")):
        if isinstance(risk, dict):
            text = _compact(risk.get("description") or risk.get("title"))
            if text:
                risks.append(text)
    evaluation = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}
    risks.extend(_compact(item) for item in _list(evaluation.get("weaknesses")) if _compact(item))
    return list(dict.fromkeys(risks))


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


def _stack_components(stack: Any) -> list[str]:
    if not isinstance(stack, dict):
        return []
    return [_compact(value) for key, value in sorted(stack.items()) if key and _compact(value)]


def _engineering_owner(solution: dict[str, Any]) -> str:
    stack = solution.get("suggested_stack")
    if isinstance(stack, dict) and stack:
        language = _compact(stack.get("language"))
        framework = _compact(stack.get("framework"))
        label = " / ".join(item for item in (language, framework) if item)
        if label:
            return f"{label} service owner"
    return "service owner"


def _extend_section(lines: list[str], title: str, items: list[dict[str, Any]], renderer) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_signal(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Category: {_text(item.get('category'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Definition: {_text(item.get('definition'))}",
        f"- Target: {_text(item.get('target'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_alert(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Severity: {_text(item.get('severity'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Threshold: {_text(item.get('threshold'))}",
        f"- Response: {_text(item.get('response'))}",
        f"- Signals: {_join_code(item.get('signal_ids'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_dashboard(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('title'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        "- Panels:",
        *_bullets(item.get("panels")),
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        f"- Suggested owner: {_text(item.get('suggested_owner'))}",
        f"- Responsibility: {_text(item.get('responsibility'))}",
    ]


def _render_check(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Check: {_text(item.get('check'))}",
        f"- Signals: {_join_code(item.get('signal_ids'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Type: {_text(item.get('type'))}",
        f"- Summary: {_text(item.get('summary'))}",
    ]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for section, telemetry_type in (
        ("metrics", "metric"),
        ("events", "event"),
        ("logs", "log"),
        ("traces", "trace"),
        ("slos", "slo"),
    ):
        for item in _dict_items(plan.get(section)):
            rows.append(
                _csv_row(
                    plan,
                    section="telemetry",
                    type_=telemetry_type,
                    field="definition",
                    item_id=item.get("id"),
                    name=item.get("name"),
                    category=item.get("category"),
                    owner=item.get("owner"),
                    description=item.get("description"),
                    definition=item.get("definition"),
                    target=item.get("target"),
                    derived_from=item.get("derived_from"),
                    evidence_references=item.get("evidence_reference_ids"),
                )
            )

    for item in _dict_items(plan.get("dashboards")):
        rows.append(
            _csv_row(
                plan,
                section="dashboards",
                type_="dashboard",
                field="panels",
                item_id=item.get("id"),
                name=item.get("title"),
                owner=item.get("owner"),
                description=item.get("description"),
                panels=item.get("panels"),
                evidence_references=item.get("evidence_reference_ids"),
            )
        )

    for item in _dict_items(plan.get("alerts")):
        rows.append(
            _csv_row(
                plan,
                section="alerts",
                type_="alert",
                field="threshold",
                item_id=item.get("id"),
                name=item.get("name"),
                severity=item.get("severity"),
                owner=item.get("owner"),
                threshold=item.get("threshold"),
                response=item.get("response"),
                signals=item.get("signal_ids"),
                evidence_references=item.get("evidence_reference_ids"),
            )
        )

    for item in _dict_items(plan.get("owners")):
        rows.append(
            _csv_row(
                plan,
                section="ownership",
                type_="owner",
                field="responsibility",
                item_id=item.get("id"),
                name=item.get("role"),
                owner=item.get("role"),
                suggested_owner=item.get("suggested_owner"),
                description=item.get("responsibility"),
            )
        )

    for item in _dict_items(plan.get("rollout_validation_checks")):
        rows.append(
            _csv_row(
                plan,
                section="instrumentation_gaps",
                type_="gap",
                field="check",
                item_id=item.get("id"),
                name=item.get("check"),
                owner=item.get("owner"),
                description=item.get("check"),
                signals=item.get("signal_ids"),
                evidence_references=item.get("evidence_reference_ids"),
                status=item.get("status"),
            )
        )

    rows.append(
        _csv_row(
            plan,
            section="review_cadence",
            type_="cadence",
            field="cadence",
            item_id="CAD1",
            name="Observability review cadence",
            owner="launch_owner",
            cadence=_review_cadence(plan),
            description="Review telemetry, dashboards, alerts, unresolved instrumentation gaps, and launch evidence.",
        )
    )

    return rows


def _csv_row(
    plan: dict[str, Any],
    *,
    section: str,
    type_: str,
    field: Any = None,
    item_id: Any = None,
    name: Any = None,
    category: Any = None,
    severity: Any = None,
    owner: Any = None,
    suggested_owner: Any = None,
    cadence: Any = None,
    description: Any = None,
    definition: Any = None,
    target: Any = None,
    threshold: Any = None,
    response: Any = None,
    panels: Any = None,
    signals: Any = None,
    derived_from: Any = None,
    evidence_references: Any = None,
    status: Any = None,
) -> dict[str, str]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    values = {
        "section": section,
        "type": type_,
        "source_idea_id": source.get("idea_id"),
        "title": summary.get("title"),
        "workflow_context": summary.get("workflow_context"),
        "item_id": item_id,
        "name": name,
        "category": category,
        "severity": severity,
        "owner": owner,
        "suggested_owner": suggested_owner,
        "cadence": cadence,
        "field": field,
        "description": description,
        "definition": definition,
        "target": target,
        "threshold": threshold,
        "response": response,
        "panels": panels,
        "signals": signals,
        "derived_from": derived_from,
        "evidence_references": evidence_references,
        "status": status,
    }
    return {column: _csv_text(values.get(column)) for column in OBSERVABILITY_PLAN_CSV_COLUMNS}


def _review_cadence(plan: dict[str, Any]) -> str:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    if summary.get("risk_count"):
        return "Daily during pilot, weekly before rollout expansion, and after every page alert."
    return "Weekly during validation and before rollout expansion."


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
    if isinstance(value, (list, tuple, set)):
        return "; ".join(_csv_text(item) for item in value if _csv_text(item))
    return _compact(value)


def _bullets(values: Any) -> list[str]:
    items = [_compact(item) for item in _list(values) if _compact(item)]
    return [f"  - {item}" for item in items] if items else ["  - None."]


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


def _dedupe_by_id(references: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for reference in references:
        deduped.setdefault(reference["id"], reference)
    return list(deduped.values())


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
