"""Generate deterministic customer onboarding plans for buildable specs."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from max.spec.generator import generate_spec_preview
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION = "max-customer-onboarding-plan/v1"
CUSTOMER_ONBOARDING_PLAN_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "idea_id",
    "title",
    "section",
    "row_type",
    "row_id",
    "name",
    "phase",
    "owner",
    "timing",
    "status",
    "metric",
    "risk",
    "description",
    "success_criteria",
    "evidence_references",
    "source_references",
    "details",
)


def generate_customer_onboarding_plan(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    tact_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn a buildable idea into deterministic customer onboarding guidance."""
    spec = tact_spec if isinstance(tact_spec, dict) else generate_spec_preview(unit, evaluation)
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    solution = spec.get("solution") if isinstance(spec.get("solution"), dict) else {}
    evidence = spec.get("evidence") if isinstance(spec.get("evidence"), dict) else {}
    evaluation_payload = spec.get("evaluation") if isinstance(spec.get("evaluation"), dict) else {}

    idea = _idea_metadata(unit, evaluation, project, execution)
    evidence_references = _evidence_references(unit, evidence)
    evidence_ids = [reference["id"] for reference in evidence_references]
    risks = _handoff_risks(unit, evaluation, execution, evaluation_payload, evidence_ids)

    return {
        "schema_version": CUSTOMER_ONBOARDING_PLAN_SCHEMA_VERSION,
        "kind": "max.customer_onboarding_plan",
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
        "idea": idea,
        "onboarding_segments": _onboarding_segments(idea, unit, evidence_ids),
        "first_session_checklist": _first_session_checklist(idea, solution, evidence_ids),
        "activation_milestones": _activation_milestones(idea, risks, evidence_ids),
        "enablement_assets": _enablement_assets(idea, unit, solution, evidence_ids),
        "success_metrics": _success_metrics(idea, risks, evidence_ids),
        "handoff_risks": risks,
        "evidence_references": evidence_references,
    }


def render_customer_onboarding_plan_markdown(
    plan: dict[str, Any], output_format: str = "markdown"
) -> str:
    """Render a customer onboarding plan as deterministic Markdown."""
    if output_format != "markdown":
        raise ValueError(f"Unsupported customer onboarding plan render format: {output_format}")

    idea = plan.get("idea", {})
    source = plan.get("source", {})
    title = _text(idea.get("title")) or _text(plan.get("idea_id")) or "Idea"

    lines = [
        f"# {title} Customer Onboarding Plan",
        "",
        f"- Schema version: {_text(plan.get('schema_version'))}",
        f"- Idea ID: {_text(plan.get('idea_id'))}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- Category: {_text(source.get('category')) or 'none'}",
        f"- Target user: {_text(idea.get('target_user'))}",
        f"- Buyer: {_text(idea.get('buyer'))}",
        f"- Workflow context: {_text(idea.get('workflow_context'))}",
        f"- Primary scope: {_text(idea.get('primary_scope'))}",
        f"- Recommendation: {_text(idea.get('recommendation')) or 'none'}",
        f"- Overall score: {_text(idea.get('overall_score')) or 'none'}",
        f"- Validation plan: {_text(idea.get('validation_plan'))}",
        "",
    ]

    _extend_section(
        lines,
        "Onboarding Segments",
        plan.get("onboarding_segments") or [],
        _render_segment,
    )
    _extend_section(
        lines,
        "First-Session Checklist",
        plan.get("first_session_checklist") or [],
        _render_check,
    )
    _extend_section(
        lines,
        "Activation Milestones",
        plan.get("activation_milestones") or [],
        _render_milestone,
    )
    _extend_section(
        lines,
        "Enablement Assets",
        plan.get("enablement_assets") or [],
        _render_asset,
    )
    _extend_section(
        lines,
        "Success Metrics",
        plan.get("success_metrics") or [],
        _render_metric,
    )
    _extend_section(
        lines,
        "Handoff Risks",
        plan.get("handoff_risks") or [],
        _render_risk,
    )
    _extend_section(
        lines,
        "Evidence References",
        plan.get("evidence_references") or [],
        _render_evidence,
    )

    lines.extend(
        [
            "## Source Flags",
            "",
            f"- Evaluation available: {_text(source.get('evaluation_available'))}",
            f"- Tact spec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
            f"- Evidence references: {_text(source.get('evidence_reference_count'))}",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_customer_onboarding_plan_csv(plan: dict[str, Any]) -> str:
    """Render a customer onboarding plan as deterministic CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=CUSTOMER_ONBOARDING_PLAN_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _csv_rows(plan or {}):
        writer.writerow(row)
    return output.getvalue()


def _idea_metadata(
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
        "buyer": _compact(project.get("buyer") or unit.buyer) or "customer sponsor",
        "workflow_context": workflow,
        "primary_scope": _first_string(execution.get("mvp_scope"))
        or unit.solution
        or f"first usable {unit.title} workflow",
        "current_workaround": unit.current_workaround or "current manual process",
        "first_10_customers": _compact(execution.get("first_10_customers"))
        or unit.first_10_customers
        or "first qualified customer cohort",
        "validation_plan": _compact(execution.get("validation_plan"))
        or unit.validation_plan
        or f"Run a staffed onboarding session for {workflow}.",
        "value_proposition": _compact(project.get("value_proposition"))
        or unit.value_proposition
        or unit.one_liner,
        "recommendation": evaluation.recommendation if evaluation else None,
        "overall_score": evaluation.overall_score if evaluation else None,
    }


def _onboarding_segments(
    idea: dict[str, Any], unit: BuildableUnit, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        _segment(
            "SEG1",
            "pilot_champion",
            idea["target_user"],
            f"Needs to complete {idea['workflow_context']} with a supported first-use path.",
            "high_touch",
            f"Book a guided session and confirm success against {idea['validation_plan']}",
            ["idea.target_user", "idea.validation_plan"],
            evidence_ids,
        ),
        _segment(
            "SEG2",
            "economic_sponsor",
            idea["buyer"],
            f"Needs proof that {idea['primary_scope']} advances the stated value proposition.",
            "briefing",
            "Share activation evidence, unresolved handoff risks, and next cohort decision.",
            ["idea.buyer", "idea.value_proposition"],
            evidence_ids,
        ),
        _segment(
            "SEG3",
            "first_customer_cohort",
            idea["first_10_customers"],
            "Needs repeatable setup, support path, and expectation setting before expansion.",
            "cohort",
            "Use the same first-session checklist and compare outcomes before expanding.",
            ["idea.first_10_customers", "idea.primary_scope"],
            evidence_ids,
        ),
        _segment(
            "SEG4",
            "fallback_or_workaround_owner",
            unit.specific_user or idea["target_user"],
            f"Needs the previous path available if onboarding blocks {idea['workflow_context']}.",
            "fallback",
            f"Keep {idea['current_workaround']} documented until activation is stable.",
            ["idea.current_workaround"],
            evidence_ids,
        ),
    ]


def _first_session_checklist(
    idea: dict[str, Any], solution: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        _check(
            "FS1",
            "Confirm customer fit and expected outcome.",
            "customer_success_owner",
            f"Requester matches {idea['target_user']} and success is tied to {idea['workflow_context']}.",
            ["idea.target_user", "idea.workflow_context"],
            evidence_ids,
        ),
        _check(
            "FS2",
            "Prepare account, permissions, and sample input.",
            "technical_owner",
            f"Customer can start {idea['primary_scope']} without waiting on missing setup.",
            ["idea.primary_scope", "solution.technical_approach"],
            evidence_ids,
        ),
        _check(
            "FS3",
            "Walk through the first value path.",
            "customer_success_owner",
            f"Customer completes {idea['workflow_context']} during the first session.",
            ["idea.workflow_context", "idea.validation_plan"],
            evidence_ids,
        ),
        _check(
            "FS4",
            "Record blockers, questions, and unsupported expectations.",
            "support_owner",
            "Open issues include owner, severity, workaround, and customer-facing next step.",
            ["handoff_risks", "idea.current_workaround"],
            evidence_ids,
        ),
        _check(
            "FS5",
            "Send follow-up assets and activation target.",
            "customer_success_owner",
            "Customer receives the correct enablement assets and next milestone.",
            ["enablement_assets", "activation_milestones"],
            evidence_ids,
        ),
    ]


def _activation_milestones(
    idea: dict[str, Any], risks: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    milestones = [
        _milestone(
            "AM1",
            "setup_complete",
            "first_session",
            f"{idea['target_user']} has access, context, and a prepared first-use input.",
            "Customer can start the workflow without support intervention.",
            "customer_success_owner",
            ["FS1", "FS2"],
            evidence_ids,
        ),
        _milestone(
            "AM2",
            "first_value_path_complete",
            "first_session",
            f"Customer completes {idea['workflow_context']} for the first qualified use case.",
            "Output is accepted by the customer as useful for the MVP scope.",
            "product_owner",
            ["FS3", "idea.value_proposition"],
            evidence_ids,
        ),
        _milestone(
            "AM3",
            "repeat_use_confirmed",
            "first_week",
            f"Customer repeats {idea['workflow_context']} without guided intervention.",
            "At least one repeat attempt completes or a documented blocker has an owner.",
            "customer_success_owner",
            ["success_metrics.SM2", "handoff_risks"],
            evidence_ids,
        ),
        _milestone(
            "AM4",
            "handoff_ready",
            "first_week",
            "Customer-facing support, product, and technical owners accept ongoing responsibility.",
            "Open onboarding risks are closed, accepted, or scheduled with a named owner.",
            "launch_owner",
            ["first_session_checklist", "handoff_risks"],
            evidence_ids,
        ),
    ]
    if risks:
        milestones.append(
            _milestone(
                "AM5",
                "risk_review_complete",
                "before_expansion",
                f"Review the highest-priority onboarding risk: {risks[0]['description']}",
                "Expansion decision includes mitigation, acceptance, or rollback to workaround.",
                "product_owner",
                [risks[0]["id"], "idea.current_workaround"],
                evidence_ids,
            )
        )
    return milestones


def _enablement_assets(
    idea: dict[str, Any],
    unit: BuildableUnit,
    solution: dict[str, Any],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        _asset(
            "EA1",
            "first_session_script",
            "customer_success_owner",
            f"Guided session outline for {idea['workflow_context']} and expected first value.",
            "before first pilot session",
            ["idea.workflow_context", "idea.validation_plan"],
            evidence_ids,
        ),
        _asset(
            "EA2",
            "setup_and_permissions_guide",
            "technical_owner",
            _setup_asset_description(solution, unit),
            "before first pilot session",
            ["solution.technical_approach", "unit.suggested_stack"],
            evidence_ids,
        ),
        _asset(
            "EA3",
            "scope_and_expectations_note",
            "product_owner",
            f"Customer-safe description of supported MVP scope: {idea['primary_scope']}.",
            "before customer commitment",
            ["idea.primary_scope", "idea.value_proposition"],
            evidence_ids,
        ),
        _asset(
            "EA4",
            "support_intake_template",
            "support_owner",
            "Template for blockers, severity, reproduction details, workaround, and next owner.",
            "before onboarding starts",
            ["first_session_checklist.FS4", "handoff_risks"],
            evidence_ids,
        ),
    ]


def _success_metrics(
    idea: dict[str, Any], risks: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    metrics = [
        _metric(
            "SM1",
            "first_session_completion_rate",
            "activation",
            f"Share of guided sessions where {idea['target_user']} completes setup and first value path.",
            "count(first_sessions_completed) / count(first_sessions_started)",
            ">= 80% for the first customer cohort",
            "customer_success_owner",
            ["FS1", "FS2", "FS3"],
            evidence_ids,
        ),
        _metric(
            "SM2",
            "repeat_use_count",
            "activation",
            f"Count of qualified repeat attempts for {idea['workflow_context']} after the guided session.",
            "count(workflow_completed where guided=false and qualified_user=true)",
            ">= 1 repeat completion per activated customer in the first week",
            "product_owner",
            ["AM3", "idea.workflow_context"],
            evidence_ids,
        ),
        _metric(
            "SM3",
            "onboarding_blocker_count",
            "handoff",
            "Open setup, expectation, support, or technical blockers from onboarding.",
            "count(open_onboarding_blockers)",
            "0 critical blockers before expanding the cohort",
            "launch_owner",
            ["FS4", "handoff_risks"],
            evidence_ids,
        ),
        _metric(
            "SM4",
            "value_confirmation_rate",
            "customer_value",
            f"Share of activated customers who confirm {idea['value_proposition']}.",
            "count(value_confirmed) / count(activated_customers)",
            ">= 70% of activated customers before broad handoff",
            "product_owner",
            ["idea.value_proposition", "AM2"],
            evidence_ids,
        ),
    ]
    if risks:
        metrics.append(
            _metric(
                "SM5",
                "risk_acceptance_coverage",
                "risk",
                "Share of onboarding risks with mitigation, acceptance, or explicit owner.",
                "count(risks_with_decision) / count(onboarding_risks)",
                "100% before rollout expansion",
                "launch_owner",
                ["handoff_risks"],
                evidence_ids,
            )
        )
    return metrics


def _handoff_risks(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    execution: dict[str, Any],
    evaluation_payload: dict[str, Any],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    explicit_risks = [*_string_list(execution.get("risks")), *unit.domain_risks]
    for risk in _dedupe(explicit_risks):
        risks.append(
            _risk(
                f"HR{len(risks) + 1}",
                "known_delivery_risk",
                "elevated",
                risk,
                "Review in the first-session debrief and do not expand until owner accepts mitigation.",
                "product_owner",
                ["execution.risks", "unit.domain_risks"],
                evidence_ids,
            )
        )

    weaknesses = (
        evaluation.weaknesses if evaluation else _string_list(evaluation_payload.get("weaknesses"))
    )
    for weakness in weaknesses[:2]:
        risks.append(
            _risk(
                f"HR{len(risks) + 1}",
                "evaluation_weakness",
                "standard",
                weakness,
                "Convert into expectation-setting notes or a product follow-up before handoff.",
                "product_owner",
                ["evaluation.weaknesses"],
                evidence_ids,
            )
        )

    if evaluation is None:
        risks.append(
            _risk(
                f"HR{len(risks) + 1}",
                "missing_evaluation",
                "elevated",
                "No utility evaluation is available for onboarding fit and priority context.",
                "Ask the product owner to approve pilot selection and customer-facing claims.",
                "product_owner",
                ["evaluation"],
                evidence_ids,
            )
        )

    if not evidence_ids or evidence_ids == ["spec:fallback"]:
        risks.append(
            _risk(
                f"HR{len(risks) + 1}",
                "missing_evidence",
                "standard",
                "No insight or signal identifiers are attached to the onboarding handoff.",
                "Treat first-session feedback as exploratory until evidence is linked.",
                "customer_success_owner",
                ["evidence"],
                evidence_ids,
            )
        )
    return risks


def _segment(
    segment_id: str,
    name: str,
    audience: str,
    need: str,
    onboarding_motion: str,
    entry_action: str,
    derived_from: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": segment_id,
        "name": name,
        "audience": _compact(audience),
        "need": _compact(need),
        "onboarding_motion": onboarding_motion,
        "entry_action": _compact(entry_action),
        "derived_from": derived_from,
        "evidence_reference_ids": evidence_ids,
    }


def _check(
    check_id: str,
    task: str,
    owner: str,
    done_when: str,
    derived_from: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "task": _compact(task),
        "owner": owner,
        "status": "pending",
        "done_when": _compact(done_when),
        "derived_from": derived_from,
        "evidence_reference_ids": evidence_ids,
    }


def _milestone(
    milestone_id: str,
    name: str,
    target_window: str,
    customer_outcome: str,
    exit_criteria: str,
    owner: str,
    references: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": milestone_id,
        "name": name,
        "target_window": target_window,
        "customer_outcome": _compact(customer_outcome),
        "exit_criteria": _compact(exit_criteria),
        "owner": owner,
        "references": references,
        "evidence_reference_ids": evidence_ids,
    }


def _asset(
    asset_id: str,
    name: str,
    owner: str,
    purpose: str,
    due: str,
    derived_from: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": asset_id,
        "name": name,
        "owner": owner,
        "purpose": _compact(purpose),
        "due": due,
        "derived_from": derived_from,
        "evidence_reference_ids": evidence_ids,
    }


def _metric(
    metric_id: str,
    name: str,
    category: str,
    description: str,
    measurement: str,
    target: str,
    owner: str,
    references: list[str],
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
        "references": references,
        "evidence_reference_ids": evidence_ids,
    }


def _risk(
    risk_id: str,
    source: str,
    severity: str,
    description: str,
    mitigation: str,
    owner: str,
    derived_from: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "source": source,
        "severity": severity,
        "description": _compact(description),
        "mitigation": _compact(mitigation),
        "owner": owner,
        "derived_from": derived_from,
        "evidence_reference_ids": evidence_ids,
    }


def _evidence_references(unit: BuildableUnit, evidence: dict[str, Any]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for insight_id in [*_string_list(evidence.get("insight_ids")), *unit.inspiring_insights]:
        references.append(
            {
                "id": f"insight:{insight_id}",
                "type": "insight",
                "summary": "Source insight linked to onboarding assumptions.",
            }
        )
    for signal_id in [*_string_list(evidence.get("signal_ids")), *unit.evidence_signals]:
        references.append(
            {
                "id": f"signal:{signal_id}",
                "type": "signal",
                "summary": "Source signal linked to onboarding demand or timing.",
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
    deduped = list({reference["id"]: reference for reference in references}.values())
    return deduped or [
        {
            "id": "spec:fallback",
            "type": "fallback",
            "summary": "No source evidence identifiers were provided.",
        }
    ]


def _setup_asset_description(solution: dict[str, Any], unit: BuildableUnit) -> str:
    approach = _compact(solution.get("technical_approach") or unit.tech_approach)
    if approach:
        return f"Setup guide covering account, permissions, and first input for {approach}."
    stack = (
        solution.get("suggested_stack")
        if isinstance(solution.get("suggested_stack"), dict)
        else unit.suggested_stack
    )
    if stack:
        return f"Setup guide covering account, permissions, and first input for {_format_stack(stack)}."
    return "Setup guide covering account, permissions, and first input."


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


def _render_segment(segment: dict[str, Any]) -> list[str]:
    return [
        f"### {segment['id']}: {segment['name']}",
        "",
        f"- Audience: {segment['audience']}",
        f"- Need: {segment['need']}",
        f"- Onboarding motion: {segment['onboarding_motion']}",
        f"- Entry action: {segment['entry_action']}",
        f"- Derived from: {_join(segment.get('derived_from'))}",
        f"- Evidence references: {_join(segment.get('evidence_reference_ids'))}",
    ]


def _render_check(check: dict[str, Any]) -> list[str]:
    return [
        f"### {check['id']}: {check['task']}",
        "",
        f"- Owner: {check['owner']}",
        f"- Status: {check['status']}",
        f"- Done when: {check['done_when']}",
        f"- Derived from: {_join(check.get('derived_from'))}",
        f"- Evidence references: {_join(check.get('evidence_reference_ids'))}",
    ]


def _render_milestone(milestone: dict[str, Any]) -> list[str]:
    return [
        f"### {milestone['id']}: {milestone['name']}",
        "",
        f"- Target window: {milestone['target_window']}",
        f"- Customer outcome: {milestone['customer_outcome']}",
        f"- Exit criteria: {milestone['exit_criteria']}",
        f"- Owner: {milestone['owner']}",
        f"- References: {_join(milestone.get('references'))}",
        f"- Evidence references: {_join(milestone.get('evidence_reference_ids'))}",
    ]


def _render_asset(asset: dict[str, Any]) -> list[str]:
    return [
        f"### {asset['id']}: {asset['name']}",
        "",
        f"- Owner: {asset['owner']}",
        f"- Purpose: {asset['purpose']}",
        f"- Due: {asset['due']}",
        f"- Derived from: {_join(asset.get('derived_from'))}",
        f"- Evidence references: {_join(asset.get('evidence_reference_ids'))}",
    ]


def _render_metric(metric: dict[str, Any]) -> list[str]:
    return [
        f"### {metric['id']}: {metric['name']}",
        "",
        f"- Category: {metric['category']}",
        f"- Description: {metric['description']}",
        f"- Measurement: `{metric['measurement']}`",
        f"- Target: {metric['target']}",
        f"- Owner: {metric['owner']}",
        f"- References: {_join(metric.get('references'))}",
        f"- Evidence references: {_join(metric.get('evidence_reference_ids'))}",
    ]


def _render_risk(risk: dict[str, Any]) -> list[str]:
    return [
        f"### {risk['id']}: {risk['source']} ({risk['severity']})",
        "",
        f"- Description: {risk['description']}",
        f"- Mitigation: {risk['mitigation']}",
        f"- Owner: {risk['owner']}",
        f"- Derived from: {_join(risk.get('derived_from'))}",
        f"- Evidence references: {_join(risk.get('evidence_reference_ids'))}",
    ]


def _render_evidence(reference: dict[str, Any]) -> list[str]:
    return [
        f"### {reference['id']}",
        "",
        f"- Type: {reference['type']}",
        f"- Summary: {reference['summary']}",
    ]


def _csv_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for segment in plan.get("onboarding_segments") or []:
        rows.append(
            _csv_row(
                plan,
                section="onboarding_segments",
                row_type="phase",
                row_id=segment.get("id"),
                name=segment.get("name"),
                phase=segment.get("onboarding_motion"),
                owner=segment.get("audience"),
                description=segment.get("need"),
                success_criteria=segment.get("entry_action"),
                evidence_references=segment.get("evidence_reference_ids"),
                source_references=segment.get("derived_from"),
                details={"audience": segment.get("audience")},
            )
        )
    for check in plan.get("first_session_checklist") or []:
        rows.append(
            _csv_row(
                plan,
                section="first_session_checklist",
                row_type="task",
                row_id=check.get("id"),
                name=check.get("task"),
                phase="first_session",
                owner=check.get("owner"),
                timing="first_session",
                status=check.get("status"),
                description=check.get("task"),
                success_criteria=check.get("done_when"),
                evidence_references=check.get("evidence_reference_ids"),
                source_references=check.get("derived_from"),
            )
        )
    for milestone in plan.get("activation_milestones") or []:
        rows.append(
            _csv_row(
                plan,
                section="activation_milestones",
                row_type="handoff_checkpoint",
                row_id=milestone.get("id"),
                name=milestone.get("name"),
                phase="activation",
                owner=milestone.get("owner"),
                timing=milestone.get("target_window"),
                description=milestone.get("customer_outcome"),
                success_criteria=milestone.get("exit_criteria"),
                evidence_references=milestone.get("evidence_reference_ids"),
                source_references=milestone.get("references"),
            )
        )
    for asset in plan.get("enablement_assets") or []:
        rows.append(
            _csv_row(
                plan,
                section="enablement_assets",
                row_type="task",
                row_id=asset.get("id"),
                name=asset.get("name"),
                phase="enablement",
                owner=asset.get("owner"),
                timing=asset.get("due"),
                description=asset.get("purpose"),
                success_criteria=asset.get("purpose"),
                evidence_references=asset.get("evidence_reference_ids"),
                source_references=asset.get("derived_from"),
            )
        )
    for metric in plan.get("success_metrics") or []:
        rows.append(
            _csv_row(
                plan,
                section="success_metrics",
                row_type="success_metric",
                row_id=metric.get("id"),
                name=metric.get("name"),
                phase=metric.get("category"),
                owner=metric.get("owner"),
                metric=metric.get("measurement"),
                description=metric.get("description"),
                success_criteria=metric.get("target"),
                evidence_references=metric.get("evidence_reference_ids"),
                source_references=metric.get("references"),
            )
        )
    for risk in plan.get("handoff_risks") or []:
        rows.append(
            _csv_row(
                plan,
                section="handoff_risks",
                row_type="risk",
                row_id=risk.get("id"),
                name=risk.get("source"),
                phase="handoff",
                owner=risk.get("owner"),
                status=risk.get("severity"),
                risk=risk.get("description"),
                description=risk.get("description"),
                success_criteria=risk.get("mitigation"),
                evidence_references=risk.get("evidence_reference_ids"),
                source_references=risk.get("derived_from"),
            )
        )
    for index, milestone in enumerate(
        _list(plan.get("onboarding_milestones") or plan.get("milestones")), start=1
    ):
        rows.append(_generic_milestone_csv_row(plan, milestone, index))
        for task_index, task in enumerate(
            _list(milestone.get("tasks") or milestone.get("checklist_items")),
            start=1,
        ):
            rows.append(
                _generic_task_csv_row(
                    plan,
                    task,
                    task_index,
                    parent_id=_text(milestone.get("id")) or f"M{index}",
                    parent_name=milestone.get("name") or milestone.get("title"),
                )
            )
    for index, task in enumerate(_list(plan.get("onboarding_tasks") or plan.get("tasks")), start=1):
        rows.append(_generic_task_csv_row(plan, task, index))
    for index, criterion in enumerate(_list(plan.get("success_criteria")), start=1):
        rows.append(_generic_success_criterion_csv_row(plan, criterion, index))
    for index, prerequisite in enumerate(_list(plan.get("prerequisites")), start=1):
        rows.append(
            _generic_note_csv_row(plan, "prerequisites", "prerequisite", prerequisite, index)
        )
    for index, artifact in enumerate(
        _list(plan.get("customer_facing_artifacts") or plan.get("artifacts")),
        start=1,
    ):
        rows.append(_generic_artifact_csv_row(plan, artifact, index))
    for index, risk in enumerate(
        _list(plan.get("risks") or plan.get("risk_mitigation_notes")), start=1
    ):
        rows.append(_generic_risk_csv_row(plan, risk, index))
    return rows


def _generic_milestone_csv_row(
    plan: dict[str, Any], milestone: dict[str, Any], index: int
) -> dict[str, str]:
    row_id = _text(milestone.get("id")) or f"M{index}"
    return _csv_row(
        plan,
        section="onboarding_milestones",
        row_type="milestone",
        row_id=row_id,
        name=_first_value(milestone, "name", "title", "milestone"),
        phase=_first_value(milestone, "phase", "stage", "category"),
        owner=milestone.get("owner"),
        timing=_first_value(milestone, "target_timing", "target_window", "timing", "due"),
        status=milestone.get("status"),
        description=_first_value(milestone, "description", "customer_outcome", "outcome", "goal"),
        success_criteria=_first_value(
            milestone,
            "success_criteria",
            "exit_criteria",
            "done_when",
            "target",
        ),
        evidence_references=_first_value(
            milestone, "evidence_reference_ids", "evidence_references"
        ),
        source_references=_first_value(
            milestone, "source_references", "references", "derived_from"
        ),
        details={
            "prerequisites": milestone.get("prerequisites"),
            "customer_facing_artifacts": _first_value(
                milestone, "customer_facing_artifacts", "artifacts"
            ),
            "risk": _first_value(milestone, "risk", "risk_note"),
            "mitigation": _first_value(milestone, "mitigation", "mitigation_note"),
        },
    )


def _generic_task_csv_row(
    plan: dict[str, Any],
    task: dict[str, Any],
    index: int,
    *,
    parent_id: str = "",
    parent_name: Any = "",
) -> dict[str, str]:
    raw_id = _text(task.get("id")) or f"T{index}"
    row_id = f"{parent_id}.{raw_id}" if parent_id else raw_id
    return _csv_row(
        plan,
        section="onboarding_tasks",
        row_type="task",
        row_id=row_id,
        name=_first_value(task, "name", "task", "title"),
        phase=_first_value(task, "phase", "stage"),
        owner=task.get("owner"),
        timing=_first_value(task, "target_timing", "target_window", "timing", "due"),
        status=task.get("status"),
        description=_first_value(task, "description", "task", "name"),
        success_criteria=_first_value(
            task,
            "success_criteria",
            "done_when",
            "exit_criteria",
            "target",
        ),
        evidence_references=_first_value(task, "evidence_reference_ids", "evidence_references"),
        source_references=_first_value(task, "source_references", "references", "derived_from"),
        details={
            "parent_milestone": parent_name,
            "prerequisites": task.get("prerequisites"),
            "customer_facing_artifacts": _first_value(
                task, "customer_facing_artifacts", "artifacts"
            ),
        },
    )


def _generic_success_criterion_csv_row(
    plan: dict[str, Any], criterion: dict[str, Any], index: int
) -> dict[str, str]:
    return _csv_row(
        plan,
        section="success_criteria",
        row_type="success_criterion",
        row_id=_text(criterion.get("id")) or f"SC{index}",
        name=_first_value(criterion, "name", "metric", "title"),
        phase=criterion.get("phase"),
        owner=criterion.get("owner"),
        timing=_first_value(criterion, "target_timing", "timing", "due"),
        status=criterion.get("status"),
        metric=criterion.get("metric"),
        description=_first_value(criterion, "description", "evidence"),
        success_criteria=_first_value(criterion, "target", "success_criteria", "criteria"),
        evidence_references=_first_value(
            criterion, "evidence_reference_ids", "evidence_references"
        ),
        source_references=_first_value(
            criterion, "source_references", "references", "derived_from"
        ),
    )


def _generic_note_csv_row(
    plan: dict[str, Any],
    section: str,
    row_type: str,
    item: dict[str, Any],
    index: int,
) -> dict[str, str]:
    prefix = "PR" if row_type == "prerequisite" else "N"
    return _csv_row(
        plan,
        section=section,
        row_type=row_type,
        row_id=_text(item.get("id")) or f"{prefix}{index}",
        name=_first_value(item, "name", "title", "item"),
        owner=item.get("owner"),
        timing=_first_value(item, "target_timing", "timing", "due"),
        status=item.get("status"),
        description=_first_value(item, "description", "note", "item"),
        success_criteria=_first_value(item, "success_criteria", "done_when", "ready_when"),
    )


def _generic_artifact_csv_row(
    plan: dict[str, Any], artifact: dict[str, Any], index: int
) -> dict[str, str]:
    return _csv_row(
        plan,
        section="customer_facing_artifacts",
        row_type="artifact",
        row_id=_text(artifact.get("id")) or f"CA{index}",
        name=_first_value(artifact, "name", "title", "artifact"),
        owner=artifact.get("owner"),
        timing=_first_value(artifact, "target_timing", "timing", "due", "ready_by"),
        status=artifact.get("status"),
        description=_first_value(artifact, "description", "purpose", "artifact"),
        success_criteria=_first_value(artifact, "success_criteria", "ready_when"),
        source_references=_first_value(artifact, "source_references", "references", "derived_from"),
    )


def _generic_risk_csv_row(plan: dict[str, Any], risk: dict[str, Any], index: int) -> dict[str, str]:
    return _csv_row(
        plan,
        section="risk_mitigation_notes",
        row_type="risk",
        row_id=_text(risk.get("id")) or f"R{index}",
        name=_first_value(risk, "name", "source", "risk"),
        phase=_first_value(risk, "phase", "stage"),
        owner=risk.get("owner"),
        timing=_first_value(risk, "target_timing", "timing", "due"),
        status=_first_value(risk, "status", "severity"),
        risk=_first_value(risk, "risk", "description", "note"),
        description=_first_value(risk, "description", "risk", "note"),
        success_criteria=_first_value(risk, "mitigation", "mitigation_note", "success_criteria"),
        evidence_references=_first_value(risk, "evidence_reference_ids", "evidence_references"),
        source_references=_first_value(risk, "source_references", "references", "derived_from"),
    )


def _csv_row(
    plan: dict[str, Any],
    *,
    section: str,
    row_type: str,
    row_id: Any = "",
    name: Any = "",
    phase: Any = "",
    owner: Any = "",
    timing: Any = "",
    status: Any = "",
    metric: Any = "",
    risk: Any = "",
    description: Any = "",
    success_criteria: Any = "",
    evidence_references: Any = None,
    source_references: Any = None,
    details: dict[str, Any] | None = None,
) -> dict[str, str]:
    idea = plan.get("idea") if isinstance(plan.get("idea"), dict) else {}
    return {
        "schema_version": _text(plan.get("schema_version")),
        "kind": _text(plan.get("kind")),
        "idea_id": _text(plan.get("idea_id")),
        "title": _text(idea.get("title")),
        "section": section,
        "row_type": row_type,
        "row_id": _text(row_id),
        "name": _text(name),
        "phase": _text(phase),
        "owner": _text(owner),
        "timing": _text(timing),
        "status": _text(status),
        "metric": _text(metric),
        "risk": _text(risk),
        "description": _text(description),
        "success_criteria": _text(success_criteria),
        "evidence_references": _csv_join(evidence_references),
        "source_references": _csv_join(source_references),
        "details": _csv_details(details),
    }


def _first_string(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            text = _compact(item)
            if text:
                return text
        return ""
    return _compact(value)


def _list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item if isinstance(item, dict) else {"item": item} for item in value]
    if isinstance(value, dict):
        return [value]
    text = _compact(value)
    return [{"item": text}] if text else []


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list) and any(_compact(item) for item in value):
            return value
        if _compact(value):
            return value
    return ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _compact(item))]
    text = _compact(value)
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if _compact(value)))


def _format_stack(stack: dict[str, Any]) -> str:
    return (
        ", ".join(f"{key}={value}" for key, value in sorted(stack.items())) or "unspecified stack"
    )


def _compact(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return _compact(value)


def _join(values: list[str] | None) -> str:
    items = [f"`{value}`" for value in values or [] if _compact(value)]
    return ", ".join(items) if items else "none"


def _csv_join(values: Any) -> str:
    if isinstance(values, list):
        return " | ".join(_compact(value) for value in values if _compact(value))
    return _compact(values)


def _csv_details(details: dict[str, Any] | None) -> str:
    if not details:
        return ""
    return "; ".join(
        f"{key}={_csv_join(value)}" for key, value in sorted(details.items()) if _csv_join(value)
    )
