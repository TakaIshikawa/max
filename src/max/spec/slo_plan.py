"""Generate deterministic service-level objective plans for buildable specs."""

from __future__ import annotations

from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


SLO_PLAN_SCHEMA_VERSION = "max-slo-plan/v1"

_DIMENSION_NAMES = (
    "pain_severity",
    "addressable_scale",
    "build_effort",
    "composability",
    "competitive_density",
    "timing_fit",
    "compounding_value",
)


def generate_slo_plan(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn a buildable idea into deterministic operating success targets."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}

    summary = _summary(unit, evaluation, project, execution)
    evidence_refs = _evidence_refs(unit, evidence)
    gaps = _gaps(unit, evaluation, spec, project, execution, evidence_refs)
    objectives = _objectives(summary, unit, evaluation, evidence_refs)
    alerts = _alerts(summary, objectives, unit, evaluation, gaps)

    return {
        "schema_version": SLO_PLAN_SCHEMA_VERSION,
        "kind": "max.slo_plan",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": str(unit.category),
            "evaluation_available": evaluation is not None,
            "tact_spec_available": bool(spec),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
            "evidence_reference_count": len(evidence_refs),
        },
        "summary": summary,
        "objectives": objectives,
        "alerts": alerts,
        "error_budget_policy": _error_budget_policy(summary, objectives, unit, evaluation),
        "validation_steps": _validation_steps(summary, objectives, alerts, gaps),
        "gaps": gaps,
        "next_actions": _next_actions(summary, gaps, evaluation),
    }


def render_slo_plan_markdown(plan: dict[str, Any], output_format: str = "markdown") -> str:
    """Render a generated SLO plan as a deterministic Markdown document."""
    if output_format != "markdown":
        raise ValueError(f"Unsupported SLO plan render format: {output_format}")

    summary = plan.get("summary", {})
    source = plan.get("source", {})
    title = _text(summary.get("title")) or _text(plan.get("idea_id")) or "Idea"

    lines = [
        f"# {title} SLO Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Idea ID: {_text(plan.get('idea_id'))}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Category: {_text(source.get('category')) or 'none'}",
        f"- Target user: {_text(summary.get('target_user'))}",
        f"- Buyer: {_text(summary.get('buyer'))}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Launch tier: {_text(summary.get('launch_tier'))}",
        f"- Recommendation: {_text(summary.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(summary.get('overall_score')) or 'none'}",
        "",
    ]

    _extend_section(lines, "Objectives", plan.get("objectives") or [], _render_objective)
    _extend_section(lines, "Alerts", plan.get("alerts") or [], _render_alert)
    lines.extend(_section("Error Budget Policy", _policy_lines(plan.get("error_budget_policy") or {})))
    _extend_section(lines, "Validation Steps", plan.get("validation_steps") or [], _render_step)
    _extend_section(lines, "Gaps", plan.get("gaps") or [], _render_gap)
    _extend_section(lines, "Next Actions", plan.get("next_actions") or [], _render_action)
    lines.extend(
        [
            "## Source Flags",
            "",
            f"- Evaluation available: {_text(source.get('evaluation_available'))}",
            f"- Tact spec available: {_text(source.get('tact_spec_available'))}",
            f"- Tact spec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
            f"- Evidence references: {_text(source.get('evidence_reference_count'))}",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _summary(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    project: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    workflow = _compact(project.get("workflow_context") or unit.workflow_context) or f"{unit.title} workflow"
    return {
        "title": _compact(project.get("title")) or unit.title,
        "one_liner": _compact(project.get("summary")) or unit.one_liner,
        "target_user": _compact(project.get("specific_user") or unit.specific_user or project.get("target_users") or unit.target_users)
        or "primary user",
        "buyer": _compact(project.get("buyer") or unit.buyer) or "launch sponsor",
        "workflow_context": workflow,
        "primary_scope": _first_string(execution.get("mvp_scope")) or unit.solution or f"first usable {unit.title} workflow",
        "value_proposition": _compact(project.get("value_proposition") or unit.value_proposition)
        or "validated customer value",
        "validation_plan": _compact(execution.get("validation_plan")) or unit.validation_plan or f"Validate {workflow}.",
        "launch_tier": _launch_tier(evaluation),
        "recommendation": evaluation.recommendation if evaluation else None,
        "overall_score": evaluation.overall_score if evaluation else None,
    }


def _objectives(
    summary: dict[str, Any],
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    launch_tier = summary["launch_tier"]
    availability_target = "99.5%" if launch_tier == "production_candidate" else "99.0%"
    latency_target = "p95 <= 1500 ms" if _needs_fast_feedback(unit) else "p95 <= 2500 ms"
    freshness_target = "Signals, generated outputs, and customer-visible status are no more than 24 hours stale."
    support_target = "First response within 4 business hours for pilot-impacting tickets."
    if evaluation and evaluation.pain_severity.value >= 8.0:
        support_target = "First response within 2 business hours for pilot-impacting tickets."

    return [
        _objective(
            "SLO1",
            "availability",
            f"{summary['workflow_context']} remains reachable for expected pilot users.",
            availability_target,
            "count(successful_health_checks) / count(all_health_checks)",
            "rolling 7 days during pilot, rolling 30 days after launch",
            "on_call_owner",
            ["unit.workflow_context", "execution.validation_plan"],
            evidence_refs,
        ),
        _objective(
            "SLO2",
            "latency",
            f"{summary['target_user']} receives a user-visible response while completing {summary['workflow_context']}.",
            latency_target,
            "p95(workflow_response_time_ms)",
            "rolling 24 hours",
            "technical_owner",
            ["unit.tech_approach", "unit.suggested_stack"],
            evidence_refs,
        ),
        _objective(
            "SLO3",
            "freshness",
            freshness_target,
            "<= 24 hours stale",
            "max(now - source_updated_at, now - output_generated_at)",
            "checked daily",
            "data_owner",
            ["unit.evidence_rationale", "spec.evidence"],
            evidence_refs,
        ),
        _objective(
            "SLO4",
            "support_response",
            f"{summary['target_user']} gets timely help when {summary['workflow_context']} is blocked.",
            support_target,
            "p90(first_human_response_time)",
            "rolling 7 days",
            "support_owner",
            ["unit.specific_user", "unit.buyer"],
            evidence_refs,
        ),
    ]


def _alerts(
    summary: dict[str, Any],
    objectives: list[dict[str, Any]],
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    alerts = [
        _alert(
            "AL1",
            "availability_burn",
            "critical",
            "SLO1 availability error budget burns faster than 2x expected rate for 30 minutes.",
            "Page on_call_owner and pause launch expansion until health checks recover.",
            "on_call_owner",
            ["SLO1"],
        ),
        _alert(
            "AL2",
            "latency_regression",
            "high",
            "SLO2 p95 latency exceeds target for 3 consecutive measurement windows.",
            "Open engineering incident and compare recent releases, configuration, and dependency latency.",
            "technical_owner",
            ["SLO2"],
        ),
        _alert(
            "AL3",
            "freshness_stale",
            "standard",
            "SLO3 freshness exceeds 24 hours or a source sync fails twice in a row.",
            "Refresh source data, mark outputs stale if needed, and notify the product owner.",
            "data_owner",
            ["SLO3"],
        ),
        _alert(
            "AL4",
            "support_response_miss",
            "high",
            "SLO4 support response target is missed for a pilot-blocking ticket.",
            "Escalate to support owner and attach customer impact to launch review.",
            "support_owner",
            ["SLO4"],
        ),
    ]
    if unit.domain_risks:
        alerts.append(
            _alert(
                "AL5",
                "known_risk_materialized",
                "critical",
                f"A known domain risk appears in telemetry or support intake: {unit.domain_risks[0]}.",
                "Escalate to launch_owner and decide whether to consume error budget, mitigate, or pause rollout.",
                "launch_owner",
                ["unit.domain_risks", "error_budget_policy"],
            )
        )
    if evaluation is None or gaps:
        alerts.append(
            _alert(
                f"AL{len(alerts) + 1}",
                "readiness_gap_open",
                "standard",
                "A required SLO input remains missing at launch review.",
                "Keep launch in limited pilot until the gap is accepted or closed.",
                "product_owner",
                ["gaps", "next_actions"],
            )
        )
    if summary["launch_tier"] == "production_candidate":
        alerts.append(
            _alert(
                f"AL{len(alerts) + 1}",
                "budget_exhaustion_forecast",
                "critical",
                "Projected monthly error budget exhaustion is above 80% before mid-period.",
                "Freeze non-critical changes and require owner approval for further rollout.",
                "launch_owner",
                ["error_budget_policy"],
            )
        )
    return alerts


def _error_budget_policy(
    summary: dict[str, Any],
    objectives: list[dict[str, Any]],
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
) -> dict[str, Any]:
    availability = next(item for item in objectives if item["type"] == "availability")
    budget = "1.0% pilot unavailability budget"
    if availability["target"] == "99.5%":
        budget = "0.5% monthly unavailability budget"

    freeze_threshold = "50%"
    if evaluation and evaluation.recommendation in {"strong_yes", "yes"} and evaluation.overall_score >= 75:
        freeze_threshold = "75%"

    return {
        "id": "EBP1",
        "policy": f"Use {budget} for {summary['workflow_context']} and treat customer-visible failures as budget spend.",
        "measurement_window": "monthly after launch; weekly during pilot",
        "budget_source_objective_id": availability["id"],
        "burn_rate_actions": [
            "At 25% consumed: review recent releases and known risks.",
            f"At {freeze_threshold} consumed: freeze non-critical rollout and require product-owner approval.",
            "At 100% consumed: pause expansion, publish incident summary, and complete mitigation before resuming.",
        ],
        "change_policy": "Non-critical launches wait while the error budget is exhausted or critical alerts are open.",
        "exception_policy": f"{summary['buyer']} may accept a one-time exception only with mitigation, owner, and expiry recorded.",
        "risk_notes": unit.domain_risks[:3],
    }


def _validation_steps(
    summary: dict[str, Any],
    objectives: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    steps = [
        _step(
            "VAL1",
            "Instrument every objective before pilot traffic.",
            "Each SLO has a metric name, owner, target, and dashboard panel.",
            "technical_owner",
            [item["id"] for item in objectives],
        ),
        _step(
            "VAL2",
            f"Run the documented validation path: {summary['validation_plan']}",
            "Validation run records availability, latency, freshness, and support-response measurements.",
            "qa_owner",
            ["summary.validation_plan"],
        ),
        _step(
            "VAL3",
            "Test alert routing and escalation.",
            "Every alert recommendation has a destination, severity, owner, and sample notification.",
            "on_call_owner",
            [item["id"] for item in alerts],
        ),
        _step(
            "VAL4",
            "Review error-budget policy at go/no-go.",
            "Launch notes record budget owner, freeze threshold, and exception process.",
            "launch_owner",
            ["error_budget_policy"],
        ),
    ]
    if gaps:
        steps.append(
            _step(
                "VAL5",
                "Close or explicitly accept SLO input gaps.",
                "Each gap has an owner, impact, and disposition before broad launch.",
                "product_owner",
                [item["id"] for item in gaps],
            )
        )
    return steps


def _gaps(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    spec: dict[str, Any],
    project: dict[str, Any],
    execution: dict[str, Any],
    evidence_refs: list[str],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if evaluation is None:
        gaps.append(_gap("GAP1", "missing_evaluation", "No utility evaluation is available to calibrate launch tier and target strictness.", "product_owner", "Use conservative pilot SLOs until evaluation is attached."))
    if not spec:
        gaps.append(_gap("GAP2", "missing_tact_spec", "No TactSpec preview is attached, so execution scope and preview evidence cannot be cross-checked.", "product_owner", "Generate or attach a spec preview before launch review."))
    if not _compact(project.get("workflow_context") or unit.workflow_context):
        gaps.append(_gap("GAP3", "missing_workflow_context", "Primary workflow is not specified.", "product_owner", "Name the workflow that availability and latency objectives cover."))
    if not _compact(execution.get("validation_plan") or unit.validation_plan):
        gaps.append(_gap("GAP4", "missing_validation_plan", "No validation plan is available for proving SLO instrumentation.", "qa_owner", "Add a repeatable validation path with expected measurements."))
    if not evidence_refs:
        gaps.append(_gap("GAP5", "missing_evidence_refs", "No insight or signal identifiers are attached to the idea.", "product_owner", "Attach evidence IDs so freshness and launch assumptions can be audited."))
    if not unit.buyer and not project.get("buyer"):
        gaps.append(_gap("GAP6", "missing_buyer", "No launch sponsor or buyer is specified for exception approval.", "product_owner", "Name the person or role allowed to accept SLO exceptions."))
    return gaps


def _next_actions(
    summary: dict[str, Any],
    gaps: list[dict[str, Any]],
    evaluation: UtilityEvaluation | None,
) -> list[dict[str, Any]]:
    actions = [
        _action("NA1", "technical_owner", "Add SLO metrics and dashboard panels for availability, latency, and freshness.", "before pilot"),
        _action("NA2", "on_call_owner", "Create alert rules and verify routing with sample notifications.", "before pilot"),
        _action("NA3", "support_owner", "Confirm support queue owner and first-response reporting for pilot users.", "before launch"),
        _action("NA4", "launch_owner", "Review error-budget burn and open alerts during go/no-go.", "go/no-go"),
    ]
    if gaps:
        actions.insert(
            0,
            _action("NA0", "product_owner", f"Resolve or accept {len(gaps)} SLO input gap(s).", "before broad launch"),
        )
    if evaluation is None:
        actions.append(
            _action("NA5", "product_owner", "Attach utility evaluation before tightening SLOs beyond pilot defaults.", "before broad launch")
        )
    if summary["launch_tier"] == "production_candidate":
        actions.append(
            _action("NA6", "launch_owner", "Decide whether production SLOs should replace pilot thresholds after the first measurement window.", "post-launch review")
        )
    return actions


def _objective(
    objective_id: str,
    objective_type: str,
    description: str,
    target: str,
    measurement: str,
    window: str,
    owner: str,
    derived_from: list[str],
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "id": objective_id,
        "type": objective_type,
        "description": description,
        "target": target,
        "measurement": measurement,
        "window": window,
        "owner": owner,
        "derived_from": derived_from,
        "evidence_refs": evidence_refs,
    }


def _alert(
    alert_id: str,
    name: str,
    severity: str,
    condition: str,
    recommended_response: str,
    owner: str,
    objective_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": alert_id,
        "name": name,
        "severity": severity,
        "condition": condition,
        "recommended_response": recommended_response,
        "owner": owner,
        "objective_ids": objective_ids,
    }


def _step(
    step_id: str,
    task: str,
    done_when: str,
    owner: str,
    references: list[str],
) -> dict[str, Any]:
    return {
        "id": step_id,
        "task": task,
        "owner": owner,
        "status": "pending",
        "done_when": done_when,
        "references": references,
    }


def _gap(gap_id: str, category: str, description: str, owner: str, remediation: str) -> dict[str, Any]:
    return {
        "id": gap_id,
        "category": category,
        "description": description,
        "owner": owner,
        "impact": "SLO plan uses conservative defaults until this is closed.",
        "remediation": remediation,
    }


def _action(action_id: str, owner: str, action: str, timing: str) -> dict[str, Any]:
    return {
        "id": action_id,
        "owner": owner,
        "action": action,
        "timing": timing,
    }


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


def _render_objective(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['type']}",
        "",
        f"- Description: {item['description']}",
        f"- Target: {item['target']}",
        f"- Measurement: {item['measurement']}",
        f"- Window: {item['window']}",
        f"- Owner: {item['owner']}",
        f"- Derived from: {_join(item.get('derived_from'))}",
        f"- Evidence refs: {_join(item.get('evidence_refs'))}",
    ]


def _render_alert(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['name']} ({item['severity']})",
        "",
        f"- Condition: {item['condition']}",
        f"- Recommended response: {item['recommended_response']}",
        f"- Owner: {item['owner']}",
        f"- Objective IDs: {_join(item.get('objective_ids'))}",
    ]


def _policy_lines(policy: dict[str, Any]) -> list[str]:
    return [
        f"Policy: {_text(policy.get('policy'))}",
        f"Measurement window: {_text(policy.get('measurement_window'))}",
        f"Budget source objective: {_text(policy.get('budget_source_objective_id'))}",
        "Burn-rate actions:",
        *_bullets(policy.get("burn_rate_actions") or [], empty="None."),
        f"Change policy: {_text(policy.get('change_policy'))}",
        f"Exception policy: {_text(policy.get('exception_policy'))}",
        "Risk notes:",
        *_bullets(policy.get("risk_notes") or [], empty="None."),
    ]


def _render_step(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['task']}",
        "",
        f"- Owner: {item['owner']}",
        f"- Status: {item['status']}",
        f"- Done when: {item['done_when']}",
        f"- References: {_join(item.get('references'))}",
    ]


def _render_gap(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['category']}",
        "",
        f"- Description: {item['description']}",
        f"- Owner: {item['owner']}",
        f"- Impact: {item['impact']}",
        f"- Remediation: {item['remediation']}",
    ]


def _render_action(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item['id']}: {item['owner']}",
        "",
        f"- Action: {item['action']}",
        f"- Timing: {item['timing']}",
    ]


def _section(title: str, body: list[str]) -> list[str]:
    return [f"## {title}", "", *body, ""]


def _bullets(items: list[Any], *, empty: str | None = None) -> list[str]:
    values = [f"- {_text(item)}" for item in items if _text(item)]
    if values:
        return values
    return [empty] if empty else []


def _evidence_refs(unit: BuildableUnit, evidence: dict[str, Any]) -> list[str]:
    refs = [
        *[f"insight:{item}" for item in _string_list(evidence.get("insight_ids"))],
        *[f"signal:{item}" for item in _string_list(evidence.get("signal_ids"))],
        *[f"insight:{item}" for item in unit.inspiring_insights],
        *[f"signal:{item}" for item in unit.evidence_signals],
    ]
    return _dedupe(refs)


def _launch_tier(evaluation: UtilityEvaluation | None) -> str:
    if evaluation is None:
        return "limited_pilot"
    if evaluation.recommendation in {"strong_yes", "yes"} and evaluation.overall_score >= 75:
        return "production_candidate"
    if evaluation.recommendation in {"no", "strong_no"} or evaluation.overall_score < 50:
        return "validation_only"
    return "limited_pilot"


def _needs_fast_feedback(unit: BuildableUnit) -> bool:
    text = " ".join(
        [
            unit.title,
            unit.one_liner,
            unit.workflow_context,
            unit.solution,
            unit.tech_approach,
            " ".join(str(value) for value in unit.suggested_stack.values()),
        ]
    ).lower()
    return any(term in text for term in ("cli", "ci", "api", "realtime", "real-time", "pre-release"))


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


def _join(values: Any) -> str:
    items = _string_list(values)
    return ", ".join(items) if items else "none"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
