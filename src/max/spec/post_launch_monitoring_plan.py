"""Generate deterministic post-launch monitoring plans for buildable specs."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


POST_LAUNCH_MONITORING_PLAN_SCHEMA_VERSION = "max-post-launch-monitoring-plan/v1"
POST_LAUNCH_MONITORING_PLAN_CSV_COLUMNS = (
    "section",
    "type",
    "idea_id",
    "title",
    "item_id",
    "phase",
    "metric_or_signal",
    "threshold",
    "owner",
    "review_cadence",
    "escalation_path",
    "evidence",
    "mitigation_action",
    "description",
    "measurement",
    "severity",
    "references",
)


def generate_post_launch_monitoring_plan(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn a buildable idea into deterministic post-launch operating checks."""
    spec = tact_spec if isinstance(tact_spec, dict) else generate_spec_preview(unit, evaluation)
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    evaluation_payload = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    summary = _summary(unit, evaluation, project, execution)
    evidence_references = _evidence_references(unit, evidence)
    evidence_ids = [reference["id"] for reference in evidence_references]
    risks = _risks(unit, execution, evaluation_payload)
    health_metrics = _health_metrics(summary, unit, solution, evidence_ids, risks)
    alert_thresholds = _alert_thresholds(summary, health_metrics, risks, evidence_ids)

    return {
        "schema_version": POST_LAUNCH_MONITORING_PLAN_SCHEMA_VERSION,
        "kind": "max.post_launch_monitoring_plan",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": str(unit.category),
            "evaluation_available": evaluation is not None,
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(evidence_references),
        },
        "summary": summary,
        "health_metrics": health_metrics,
        "alert_thresholds": alert_thresholds,
        "review_cadence": _review_cadence(summary, evidence_ids),
        "rollback_triggers": _rollback_triggers(summary, risks, evidence_ids),
        "owners": _owners(summary, solution),
        "evidence_references": evidence_references,
    }


def render_post_launch_monitoring_plan_markdown(
    plan: dict[str, Any], output_format: str = "markdown"
) -> str:
    """Render a post-launch monitoring plan as deterministic Markdown."""
    if output_format != "markdown":
        raise ValueError(
            f"Unsupported post-launch monitoring plan render format: {output_format}"
        )

    summary = plan.get("summary", {})
    source = plan.get("source", {})
    title = _text(summary.get("title")) or _text(plan.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Post-Launch Monitoring Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Idea ID: {_text(plan.get('idea_id'))}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Category: {_text(source.get('category')) or 'none'}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Launch posture: {_text(summary.get('launch_posture'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
    ]

    _extend_section(lines, "Health Metrics", plan.get("health_metrics") or [], _render_metric)
    _extend_section(
        lines, "Alert Thresholds", plan.get("alert_thresholds") or [], _render_alert
    )
    _extend_section(
        lines, "Review Cadence", plan.get("review_cadence") or [], _render_review
    )
    _extend_section(
        lines, "Rollback Triggers", plan.get("rollback_triggers") or [], _render_trigger
    )
    _extend_section(lines, "Owners", plan.get("owners") or [], _render_owner)
    _extend_section(
        lines, "Evidence References", plan.get("evidence_references") or [], _render_evidence
    )

    return "\n".join(lines).rstrip() + "\n"


def render_post_launch_monitoring_plan_csv(plan: dict[str, Any]) -> str:
    """Render a post-launch monitoring plan as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=POST_LAUNCH_MONITORING_PLAN_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(plan or {}):
        writer.writerow(row)
    return output.getvalue()


def _summary(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    project: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    workflow = (
        _compact(project.get("workflow_context"))
        or _compact(unit.workflow_context)
        or f"{unit.title} workflow"
    )
    return {
        "title": _compact(project.get("title")) or unit.title,
        "one_liner": _compact(project.get("summary")) or unit.one_liner,
        "target_user": _compact(
            project.get("specific_user") or unit.specific_user or project.get("target_users")
        )
        or unit.target_users
        or "primary user",
        "buyer": _compact(project.get("buyer") or unit.buyer) or "launch sponsor",
        "workflow_context": workflow,
        "primary_scope": _first_string(execution.get("mvp_scope"))
        or unit.solution
        or f"first usable {unit.title} workflow",
        "validation_plan": _compact(execution.get("validation_plan"))
        or unit.validation_plan
        or f"Run a staffed pilot for {workflow}.",
        "launch_posture": _launch_posture(evaluation),
        "recommendation": evaluation.recommendation if evaluation else None,
        "overall_score": evaluation.overall_score if evaluation else None,
    }


def _health_metrics(
    summary: dict[str, Any],
    unit: BuildableUnit,
    solution: dict[str, Any],
    evidence_ids: list[str],
    risks: list[str],
) -> list[dict[str, Any]]:
    latency_target = "p95 <= 1500 ms" if _needs_fast_feedback(unit, solution) else "p95 <= 2500 ms"
    metrics = [
        _metric(
            "HM1",
            "workflow_success_rate",
            "service_health",
            f"Share of {summary['workflow_context']} attempts completed successfully.",
            "count(workflow_completed) / count(workflow_started)",
            ">= 95% during the first 7 launch days",
            "product_owner",
            ["summary.workflow_context", "summary.validation_plan"],
            evidence_ids,
        ),
        _metric(
            "HM2",
            "workflow_latency_p95",
            "service_health",
            f"95th percentile user-visible response time for {summary['workflow_context']}.",
            "p95(workflow_duration_ms)",
            latency_target,
            "technical_owner",
            ["unit.tech_approach", "solution.suggested_stack"],
            evidence_ids,
        ),
        _metric(
            "HM3",
            "workflow_error_rate",
            "service_health",
            "User-visible failures, unhandled exceptions, and exhausted retries.",
            "count(workflow_failed) / count(workflow_started)",
            "<= 2% during staffed rollout windows",
            "on_call_owner",
            ["execution.risks", "unit.domain_risks"],
            evidence_ids,
        ),
        _metric(
            "HM4",
            "qualified_activation_count",
            "product_health",
            f"Number of qualified {summary['target_user']} users completing the MVP value path.",
            "count_distinct(user_id where workflow_completed and qualified_user=true)",
            ">= 1 qualified user in the first review window",
            "product_owner",
            ["unit.specific_user", "unit.target_users"],
            evidence_ids,
        ),
        _metric(
            "HM5",
            "support_blocker_count",
            "support_health",
            "Open launch-blocking support issues from pilot or production users.",
            "count(open_support_tickets where launch_blocker=true)",
            "0 unresolved blockers before rollout expansion",
            "support_owner",
            ["summary.buyer", "summary.target_user"],
            evidence_ids,
        ),
    ]
    if risks:
        metrics.append(
            _metric(
                "HM6",
                "known_risk_indicator_count",
                "risk_health",
                "Count of known launch risks observed in telemetry, feedback, or support intake.",
                "count(risk_indicators where mitigation_state != 'closed')",
                "0 critical indicators open for more than one review window",
                "launch_owner",
                ["execution.risks", "unit.domain_risks"],
                evidence_ids,
            )
        )
    return metrics


def _alert_thresholds(
    summary: dict[str, Any],
    metrics: list[dict[str, Any]],
    risks: list[str],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    alerts = [
        _alert(
            "AT1",
            "success_rate_drop",
            "critical",
            "HM1 falls below 90% for 30 minutes or 10 consecutive attempts.",
            "Pause rollout expansion, inspect recent changes, and start incident review.",
            "on_call_owner",
            ["HM1"],
            evidence_ids,
        ),
        _alert(
            "AT2",
            "latency_regression",
            "high",
            "HM2 misses target for 3 consecutive measurement windows.",
            "Compare release, dependency, and trace data before allowing additional users.",
            "technical_owner",
            ["HM2"],
            evidence_ids,
        ),
        _alert(
            "AT3",
            "error_rate_spike",
            "critical",
            "HM3 exceeds 5% for 15 minutes or any critical path returns persistent 5xx errors.",
            "Page the on-call owner and prepare rollback if the next check window does not recover.",
            "on_call_owner",
            ["HM3"],
            evidence_ids,
        ),
        _alert(
            "AT4",
            "activation_stall",
            "standard",
            "No qualified activation is recorded in the first scheduled review window.",
            f"Review {summary['validation_plan']} and confirm pilot users can reach the value path.",
            "product_owner",
            ["HM4"],
            evidence_ids,
        ),
        _alert(
            "AT5",
            "support_blocker_open",
            "high",
            "A launch-blocking support issue remains open past the next business review.",
            "Assign owner, record user impact, and decide fix-forward or rollback.",
            "support_owner",
            ["HM5"],
            evidence_ids,
        ),
    ]
    if risks:
        alerts.append(
            _alert(
                "AT6",
                "known_risk_materialized",
                "critical",
                f"Known launch risk appears after launch: {risks[0]}.",
                "Escalate to launch owner and decide mitigation, acceptance, or rollback.",
                "launch_owner",
                [metrics[-1]["id"]],
                evidence_ids,
            )
        )
    return alerts


def _review_cadence(summary: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _review(
            "RC1",
            "first_24_hours",
            "Twice on launch day: first staffed hour and end of launch day.",
            "Confirm core health metrics, open alerts, support blockers, and pilot feedback.",
            "launch_owner",
            ["HM1", "HM2", "HM3", "HM5"],
            evidence_ids,
        ),
        _review(
            "RC2",
            "first_week",
            "Daily for the first 5 business days after launch.",
            "Review activation, value-path completion, alert history, known risks, and fixes shipped.",
            "product_owner",
            ["HM1", "HM4", "HM6"],
            evidence_ids,
        ),
        _review(
            "RC3",
            "rollout_expansion",
            "Before each cohort, account, or traffic expansion.",
            f"Go/no-go review against {summary['workflow_context']} health and rollback triggers.",
            "launch_owner",
            ["HM1", "HM2", "HM3", "RT1", "RT2", "RT3"],
            evidence_ids,
        ),
        _review(
            "RC4",
            "steady_state_handoff",
            "At the end of the first full measurement window.",
            "Convert pilot thresholds into steady-state SLOs, dashboards, and owner rotations.",
            "technical_owner",
            ["owners", "alert_thresholds"],
            evidence_ids,
        ),
    ]


def _rollback_triggers(
    summary: dict[str, Any], risks: list[str], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    triggers = [
        _trigger(
            "RT1",
            "critical_health_regression",
            "AT1 or AT3 remains critical for two consecutive staffed review windows.",
            "Rollback or disable the affected release path until success and error metrics recover.",
            "on_call_owner",
            ["AT1", "AT3"],
            evidence_ids,
        ),
        _trigger(
            "RT2",
            "customer_value_blocked",
            f"{summary['target_user']} cannot complete {summary['workflow_context']} in validation.",
            "Pause expansion and restore the last known working path or manual workaround.",
            "product_owner",
            ["HM1", "HM4", "summary.validation_plan"],
            evidence_ids,
        ),
        _trigger(
            "RT3",
            "support_or_data_safety_blocker",
            "A launch blocker exposes customer data risk, data loss, or an unresolved support escalation.",
            "Disable the risky capability, notify launch sponsor, and keep rollout paused.",
            "launch_owner",
            ["HM5", "AT5"],
            evidence_ids,
        ),
    ]
    if risks:
        triggers.append(
            _trigger(
                "RT4",
                "known_risk_unmitigated",
                f"Known risk has material impact without accepted mitigation: {risks[0]}.",
                "Rollback the affected workflow or get explicit launch-sponsor acceptance with expiry.",
                "launch_owner",
                ["AT6", "HM6"],
                evidence_ids,
            )
        )
    return triggers


def _owners(summary: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": "OWN1",
            "role": "launch_owner",
            "suggested_owner": summary["buyer"],
            "responsibility": "Owns go/no-go decisions, rollback approval, and review cadence.",
            "handoff": "Receives daily launch summary until steady-state handoff is complete.",
        },
        {
            "id": "OWN2",
            "role": "product_owner",
            "suggested_owner": summary["buyer"],
            "responsibility": "Owns activation, workflow success, and customer-value review.",
            "handoff": "Confirms pilot feedback and value-path evidence in each review window.",
        },
        {
            "id": "OWN3",
            "role": "technical_owner",
            "suggested_owner": _engineering_owner(solution),
            "responsibility": "Owns dashboards, telemetry quality, and fix-forward decisions.",
            "handoff": "Maintains post-launch dashboard and converts thresholds into SLOs.",
        },
        {
            "id": "OWN4",
            "role": "on_call_owner",
            "suggested_owner": "release engineer or service owner",
            "responsibility": "Owns alert routing, incident response, and rollback execution.",
            "handoff": "Receives tested alert routes and rollback instructions before launch.",
        },
        {
            "id": "OWN5",
            "role": "support_owner",
            "suggested_owner": "support lead or customer-facing owner",
            "responsibility": "Owns launch-blocking support intake and escalation summaries.",
            "handoff": "Publishes unresolved blockers before every rollout expansion review.",
        },
    ]


def _metric(
    metric_id: str,
    name: str,
    category: str,
    description: str,
    measurement: str,
    target: str,
    owner: str,
    derived_from: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "name": name,
        "category": category,
        "description": _compact(description),
        "measurement": _compact(measurement),
        "target": _compact(target),
        "owner": owner,
        "derived_from": [item for item in derived_from if _compact(item)],
        "evidence_reference_ids": evidence_ids,
    }


def _alert(
    alert_id: str,
    name: str,
    severity: str,
    threshold: str,
    response: str,
    owner: str,
    metric_ids: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": alert_id,
        "name": name,
        "severity": severity,
        "threshold": _compact(threshold),
        "response": _compact(response),
        "owner": owner,
        "metric_ids": metric_ids,
        "evidence_reference_ids": evidence_ids,
    }


def _review(
    review_id: str,
    phase: str,
    cadence: str,
    agenda: str,
    owner: str,
    references: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": review_id,
        "phase": phase,
        "cadence": cadence,
        "agenda": _compact(agenda),
        "owner": owner,
        "references": references,
        "evidence_reference_ids": evidence_ids,
    }


def _trigger(
    trigger_id: str,
    name: str,
    condition: str,
    action: str,
    owner: str,
    references: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": trigger_id,
        "name": name,
        "condition": _compact(condition),
        "action": _compact(action),
        "owner": owner,
        "references": references,
        "evidence_reference_ids": evidence_ids,
    }


def _evidence_references(unit: BuildableUnit, evidence: dict[str, Any]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for insight_id in [*_string_list(evidence.get("insight_ids")), *unit.inspiring_insights]:
        references.append(
            {
                "id": f"insight:{insight_id}",
                "type": "insight",
                "summary": "Source insight linked to launch assumptions.",
            }
        )
    for signal_id in [*_string_list(evidence.get("signal_ids")), *unit.evidence_signals]:
        references.append(
            {
                "id": f"signal:{signal_id}",
                "type": "signal",
                "summary": "Evidence signal linked to launch assumptions.",
            }
        )
    for idea_id in [*_string_list(evidence.get("source_idea_ids")), *unit.source_idea_ids]:
        references.append(
            {
                "id": f"idea:{idea_id}",
                "type": "source_idea",
                "summary": "Source idea linked to this launch.",
            }
        )
    rationale = _compact(evidence.get("rationale") or unit.evidence_rationale)
    if rationale:
        references.append(
            {
                "id": "spec:evidence_rationale",
                "type": "rationale",
                "summary": rationale,
            }
        )
    if not references:
        references.append(
            {
                "id": "spec:fallback",
                "type": "fallback",
                "summary": "No evidence references were provided; monitoring uses conservative launch defaults.",
            }
        )
    return _dedupe_by_id(references)


def _risks(
    unit: BuildableUnit, execution: dict[str, Any], evaluation_payload: dict[str, Any]
) -> list[str]:
    risks = [*_string_list(execution.get("risks")), *unit.domain_risks]
    risks.extend(_string_list(evaluation_payload.get("weaknesses")))
    return _dedupe(risks)


def _launch_posture(evaluation: UtilityEvaluation | None) -> str:
    if evaluation is None:
        return "limited_pilot"
    if evaluation.recommendation in {"strong_yes", "yes"} and evaluation.overall_score >= 75:
        return "production_candidate"
    if evaluation.recommendation in {"no", "strong_no"} or evaluation.overall_score < 50:
        return "validation_only"
    return "limited_pilot"


def _needs_fast_feedback(unit: BuildableUnit, solution: dict[str, Any]) -> bool:
    stack = solution.get("suggested_stack")
    stack_values = stack.values() if isinstance(stack, dict) else []
    text = " ".join(
        [
            unit.title,
            unit.one_liner,
            unit.workflow_context,
            unit.solution,
            unit.tech_approach,
            *[str(value) for value in unit.suggested_stack.values()],
            *[str(value) for value in stack_values],
        ]
    ).lower()
    return any(term in text for term in ("cli", "ci", "api", "realtime", "real-time"))


def _engineering_owner(solution: dict[str, Any]) -> str:
    stack = solution.get("suggested_stack")
    if isinstance(stack, dict) and stack:
        language = _compact(stack.get("language"))
        framework = _compact(stack.get("framework"))
        label = " / ".join(item for item in (language, framework) if item)
        if label:
            return f"{label} service owner"
    return "service owner"


def _extend_section(
    lines: list[str],
    title: str,
    items: list[dict[str, Any]],
    renderer,
) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_metric(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Category: {_text(item.get('category'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Description: {_text(item.get('description'))}",
        f"- Measurement: {_text(item.get('measurement'))}",
        f"- Target: {_text(item.get('target'))}",
        f"- Derived from: {_join_code(item.get('derived_from'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_alert(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))} ({_text(item.get('severity'))})",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Threshold: {_text(item.get('threshold'))}",
        f"- Response: {_text(item.get('response'))}",
        f"- Metrics: {_join_code(item.get('metric_ids'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_review(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('phase'))}",
        f"- Cadence: {_text(item.get('cadence'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Agenda: {_text(item.get('agenda'))}",
        f"- References: {_join_code(item.get('references'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_trigger(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('name'))}",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Condition: {_text(item.get('condition'))}",
        f"- Action: {_text(item.get('action'))}",
        f"- References: {_join_code(item.get('references'))}",
        f"- Evidence references: {_join_code(item.get('evidence_reference_ids'))}",
    ]


def _render_owner(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}: {_text(item.get('role'))}",
        f"- Suggested owner: {_text(item.get('suggested_owner'))}",
        f"- Responsibility: {_text(item.get('responsibility'))}",
        f"- Handoff: {_text(item.get('handoff'))}",
    ]


def _render_evidence(item: dict[str, Any]) -> list[str]:
    return [
        f"### {_text(item.get('id'))}",
        f"- Type: {_text(item.get('type'))}",
        f"- Summary: {_text(item.get('summary'))}",
    ]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    rows: list[dict[str, str]] = []

    for metric in plan.get("health_metrics") or []:
        if not isinstance(metric, dict):
            continue
        rows.append(
            _csv_row(
                section="health_metrics",
                type="metric",
                idea_id=plan.get("idea_id"),
                title=summary.get("title"),
                item_id=metric.get("id"),
                phase=summary.get("launch_posture"),
                metric_or_signal=metric.get("name"),
                threshold=metric.get("target"),
                owner=metric.get("owner"),
                evidence=metric.get("evidence_reference_ids"),
                description=metric.get("description"),
                measurement=metric.get("measurement"),
                references=metric.get("derived_from"),
            )
        )

    for alert in plan.get("alert_thresholds") or []:
        if not isinstance(alert, dict):
            continue
        rows.append(
            _csv_row(
                section="alert_thresholds",
                type="alert",
                idea_id=plan.get("idea_id"),
                title=summary.get("title"),
                item_id=alert.get("id"),
                phase="alert_response",
                metric_or_signal=alert.get("name"),
                threshold=alert.get("threshold"),
                owner=alert.get("owner"),
                escalation_path=alert.get("response"),
                evidence=alert.get("evidence_reference_ids"),
                severity=alert.get("severity"),
                references=alert.get("metric_ids"),
            )
        )

    for review in plan.get("review_cadence") or []:
        if not isinstance(review, dict):
            continue
        rows.append(
            _csv_row(
                section="review_cadence",
                type="review_check",
                idea_id=plan.get("idea_id"),
                title=summary.get("title"),
                item_id=review.get("id"),
                phase=review.get("phase"),
                metric_or_signal=review.get("agenda"),
                owner=review.get("owner"),
                review_cadence=review.get("cadence"),
                evidence=review.get("evidence_reference_ids"),
                references=review.get("references"),
            )
        )

    for trigger in plan.get("rollback_triggers") or []:
        if not isinstance(trigger, dict):
            continue
        rows.append(
            _csv_row(
                section="rollback_triggers",
                type="rollback_trigger",
                idea_id=plan.get("idea_id"),
                title=summary.get("title"),
                item_id=trigger.get("id"),
                phase="rollback_decision",
                metric_or_signal=trigger.get("name"),
                threshold=trigger.get("condition"),
                owner=trigger.get("owner"),
                evidence=trigger.get("evidence_reference_ids"),
                mitigation_action=trigger.get("action"),
                references=trigger.get("references"),
            )
        )

    return rows


def _csv_row(**values: Any) -> dict[str, str]:
    return {
        column: _csv_text(values.get(column))
        for column in POST_LAUNCH_MONITORING_PLAN_CSV_COLUMNS
    }


def _first_string(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            compact = _compact(item)
            if compact:
                return compact
    return _compact(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    if isinstance(value, tuple):
        return [_compact(item) for item in value if _compact(item)]
    compact = _compact(value)
    return [compact] if compact else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        compact = _compact(value)
        if not compact or compact in seen:
            continue
        seen.add(compact)
        result.append(compact)
    return result


def _dedupe_by_id(references: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for reference in references:
        deduped.setdefault(reference["id"], reference)
    return list(deduped.values())


def _join_code(values: Any) -> str:
    items = _string_list(values)
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


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
    return str(value).strip()
