"""Deterministic pilot rollout plans for persisted design briefs."""

from __future__ import annotations

import json
import re
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.pilot_rollout.v1"


def build_design_brief_pilot_rollout(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a staged pilot rollout plan from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_source_risks(source_ideas)]
    )
    evidence_gaps = _evidence_gaps(design_brief, source_ideas)
    rollout_phases = _rollout_phases(design_brief, lead_idea, risks, evidence_gaps)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.pilot_rollout",
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
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "phase_count": len(rollout_phases),
            "operator_task_count": 5,
            "customer_touchpoint_count": 4,
            "evidence_gap_count": len(evidence_gaps),
            "risk_count": len(risks),
        },
        "pilot_cohort": _pilot_cohort(design_brief, lead_idea),
        "entry_criteria": _entry_criteria(design_brief, source_ideas, evidence_gaps),
        "rollout_phases": rollout_phases,
        "success_thresholds": _success_thresholds(design_brief, source_ideas),
        "stop_conditions": _stop_conditions(risks, evidence_gaps),
        "operator_tasks": _operator_tasks(design_brief, lead_idea, risks),
        "customer_touchpoints": _customer_touchpoints(design_brief, lead_idea),
        "evidence_gaps": evidence_gaps,
        "source_ideas": source_ideas,
    }


def render_design_brief_pilot_rollout(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render the pilot rollout report as Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported pilot rollout format: {fmt}")

    brief = report["design_brief"]
    cohort = report["pilot_cohort"]
    lines = [
        f"# Pilot Rollout Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Pilot Cohort",
        "",
        f"- Target users: {cohort['target_users']}",
        f"- Buyer/sponsor: {cohort['buyer']}",
        f"- Cohort size: {cohort['size']}",
        f"- Recruitment source: {cohort['recruitment_source']}",
        f"- Qualification: {cohort['qualification']}",
        "",
        "## Entry Criteria",
        "",
    ]
    lines.extend(f"- {item}" for item in report["entry_criteria"])

    lines.extend(["", "## Rollout Phases", ""])
    for phase in report["rollout_phases"]:
        lines.extend(
            [
                f"### {phase['id']}: {phase['name']}",
                "",
                f"- Owner: {phase['owner']}",
                f"- Goal: {phase['goal']}",
                f"- Duration: {phase['duration']}",
                f"- Exit criteria: {phase['exit_criteria']}",
                "",
            ]
        )

    lines.extend(["## Success Thresholds", ""])
    for threshold in report["success_thresholds"]:
        lines.extend(
            [
                f"- **{threshold['metric']}**: {threshold['target']}",
                f"  Evidence: {threshold['evidence']}",
            ]
        )

    lines.extend(["", "## Stop Conditions", ""])
    lines.extend(f"- {item}" for item in report["stop_conditions"])

    lines.extend(["", "## Operator Tasks", ""])
    for task in report["operator_tasks"]:
        lines.extend(
            [
                f"- **{task['owner']}**: {task['task']}",
                f"  Cadence: {task['cadence']}; output: {task['output']}",
            ]
        )

    lines.extend(["", "## Customer Touchpoints", ""])
    for touchpoint in report["customer_touchpoints"]:
        lines.extend(
            [
                f"- **{touchpoint['when']}**: {touchpoint['touchpoint']}",
                f"  Owner: {touchpoint['owner']}; evidence to capture: {touchpoint['evidence_to_capture']}",
            ]
        )

    lines.extend(["", "## Evidence Gaps", ""])
    if report["evidence_gaps"]:
        lines.extend(
            f"- **{gap['field']}**: {gap['gap']} Action: {gap['action']}"
            for gap in report["evidence_gaps"]
        )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def _pilot_cohort(
    design_brief: dict[str, Any],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    target_user = _first_text(
        design_brief.get("specific_user"),
        lead_idea and lead_idea.get("specific_user"),
        lead_idea and lead_idea.get("target_users"),
        "target users",
    )
    buyer = _first_text(
        design_brief.get("buyer"), lead_idea and lead_idea.get("buyer"), "pilot sponsor"
    )
    first_customers = _first_text(
        lead_idea and lead_idea.get("first_10_customers"), "source idea shortlist"
    )
    readiness = float(design_brief.get("readiness_score") or 0.0)
    cohort_size = "3-5 qualified teams" if readiness >= 75 else "2-3 qualified teams"
    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
        "the target workflow",
    )
    return {
        "target_users": target_user,
        "buyer": buyer,
        "size": cohort_size,
        "recruitment_source": first_customers,
        "qualification": f"Participants own {workflow} and can commit to weekly feedback during the pilot.",
        "source_fields": ["specific_user", "buyer", "workflow_context", "first_10_customers"],
    }


def _entry_criteria(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence_gaps: list[dict[str, Any]],
) -> list[str]:
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))
    validation_plan = _first_text(
        design_brief.get("validation_plan"), "Pilot validation plan is approved."
    )
    return [
        f"MVP scope is limited to: {', '.join(scope) if scope else 'the core product concept'}.",
        f"First pilot increment is ready: {milestones[0] if milestones else 'controlled workflow prototype'}.",
        f"Validation plan is accepted: {validation_plan}",
        f"Source traceability covers {len([idea for idea in source_ideas if not idea.get('missing')])} persisted idea(s).",
        f"Open evidence gaps are triaged before kickoff: {len(evidence_gaps)} gap(s).",
    ]


def _rollout_phases(
    design_brief: dict[str, Any],
    lead_idea: dict[str, Any] | None,
    risks: list[str],
    evidence_gaps: list[dict[str, Any]],
) -> list[dict[str, str]]:
    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
        "the target workflow",
    )
    first_milestone = _first_text(
        *_string_list(design_brief.get("first_milestones")), "the first pilot increment"
    )
    primary_risk = risks[0] if risks else "No material pilot risk remains unowned."
    return [
        {
            "id": "phase-1",
            "name": "Pilot Prep",
            "owner": "Product lead",
            "goal": "Confirm cohort, scope, success metrics, and risk owners before any customer exposure.",
            "duration": "3-5 business days",
            "exit_criteria": "Pilot cohort, entry criteria, stop conditions, and evidence capture plan are approved.",
        },
        {
            "id": "phase-2",
            "name": "Concierge Validation",
            "owner": "Research lead",
            "goal": f"Run {workflow} with the first qualified participants and observe where the MVP promise holds or breaks.",
            "duration": "1 week",
            "exit_criteria": f"At least two participants complete the workflow or the team records why {primary_risk}",
        },
        {
            "id": "phase-3",
            "name": "Controlled Beta",
            "owner": "Engineering lead",
            "goal": f"Ship {first_milestone} to the full pilot cohort with instrumentation and support coverage.",
            "duration": "2 weeks",
            "exit_criteria": "Activation, workflow success, and defect thresholds are reviewed with product and engineering.",
        },
        {
            "id": "phase-4",
            "name": "Expansion Decision",
            "owner": "Product lead",
            "goal": "Decide whether to expand, revise, or stop based on pilot outcomes and remaining evidence gaps.",
            "duration": "2-3 business days",
            "exit_criteria": f"Decision memo resolves {len(evidence_gaps)} evidence gap(s), pilot risks, and next cohort scope.",
        },
    ]


def _success_thresholds(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, str]]:
    workflow = _first_text(design_brief.get("workflow_context"), "target workflow")
    value = _first_text(design_brief.get("merged_product_concept"), "the product concept")
    evidence_count = sum(
        len(_string_list(idea.get("evidence_signals")))
        + len(_string_list(idea.get("inspiring_insights")))
        for idea in source_ideas
        if not idea.get("missing")
    )
    return [
        {
            "metric": "Workflow completion",
            "target": f"3+ qualified participants complete {workflow} during the pilot.",
            "evidence": "Observed sessions, event logs, or customer-confirmed completion notes.",
        },
        {
            "metric": "Repeat value",
            "target": "2+ participants ask to repeat, extend, or hand the workflow to another teammate.",
            "evidence": "Follow-up notes tied to buyer or user pull.",
        },
        {
            "metric": "Evidence coverage",
            "target": f"Pilot adds at least 3 new evidence records to the existing {evidence_count} linked evidence item(s).",
            "evidence": "Signals, interview notes, support tickets, usage snapshots, or decision records.",
        },
        {
            "metric": "Concept fit",
            "target": f"Pilot feedback confirms {value} solves a high-priority workflow problem without a material workaround regression.",
            "evidence": "Structured feedback form and expansion decision memo.",
        },
    ]


def _stop_conditions(risks: list[str], evidence_gaps: list[dict[str, Any]]) -> list[str]:
    conditions = [
        "Two or more qualified participants cannot reach first value without unscheduled operator intervention.",
        "A customer reports a material workflow regression, privacy concern, or data handling blocker.",
        "Activation or completion evidence cannot be captured reliably during the controlled beta.",
    ]
    if risks:
        conditions.append(f"Primary unresolved risk materializes without mitigation: {risks[0]}")
    if evidence_gaps:
        source_gap = next(
            (gap for gap in evidence_gaps if gap["field"] == "source_evidence"),
            evidence_gaps[0],
        )
        conditions.append(
            f"Expansion is blocked until evidence gap is resolved: {source_gap['field']}"
        )
    return conditions


def _operator_tasks(
    design_brief: dict[str, Any],
    lead_idea: dict[str, Any] | None,
    risks: list[str],
) -> list[dict[str, str]]:
    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
        "target workflow",
    )
    risk_task = risks[0] if risks else "Validate no hidden launch-blocking risks emerge."
    return [
        {
            "owner": "Product lead",
            "task": "Maintain pilot decision log, cohort status, and weekly expand/revise/stop recommendation.",
            "cadence": "weekly",
            "output": "Decision log with owner and date.",
        },
        {
            "owner": "Engineering lead",
            "task": f"Monitor activation, completion, errors, and latency for {workflow}.",
            "cadence": "daily during beta",
            "output": "Pilot health dashboard or run log.",
        },
        {
            "owner": "Research lead",
            "task": "Capture structured user evidence after each pilot session.",
            "cadence": "after every touchpoint",
            "output": "Interview notes linked to participant and source assumption.",
        },
        {
            "owner": "Support owner",
            "task": "Track support requests, escalations, and workaround regressions.",
            "cadence": "daily during customer exposure",
            "output": "Support triage list with severity and resolution.",
        },
        {
            "owner": "Risk owner",
            "task": risk_task,
            "cadence": "before each phase exit",
            "output": "Risk disposition and mitigation evidence.",
        },
    ]


def _customer_touchpoints(
    design_brief: dict[str, Any],
    lead_idea: dict[str, Any] | None,
) -> list[dict[str, str]]:
    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
        "target workflow",
    )
    return [
        {
            "when": "Kickoff",
            "touchpoint": "Confirm participant workflow, success definition, data boundaries, and feedback cadence.",
            "owner": "Product lead",
            "evidence_to_capture": "Baseline workflow pain, current workaround, and success expectation.",
        },
        {
            "when": "First session",
            "touchpoint": f"Observe the participant attempt {workflow} with the pilot experience.",
            "owner": "Research lead",
            "evidence_to_capture": "Setup friction, first value moment, failures, and unsupported steps.",
        },
        {
            "when": "Midpoint",
            "touchpoint": "Review usage evidence, support issues, and whether the participant wants another run.",
            "owner": "Customer owner",
            "evidence_to_capture": "Repeat intent, unresolved blockers, and expansion requests.",
        },
        {
            "when": "Closeout",
            "touchpoint": "Ask for continue, revise, or stop recommendation and buyer-path signal.",
            "owner": "Product lead",
            "evidence_to_capture": "Continuation intent, buyer sponsor feedback, and next-cohort qualification.",
        },
    ]


def _evidence_gaps(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    checks = [
        (
            "specific_user",
            "Specific pilot user is not defined.",
            "Name the user role that will perform the pilot workflow.",
        ),
        (
            "buyer",
            "Buyer or sponsor is not defined.",
            "Identify who can approve continuation or expansion.",
        ),
        (
            "workflow_context",
            "Workflow context is missing.",
            "Document the trigger, input, output, and current workaround.",
        ),
        (
            "validation_plan",
            "Validation plan is missing.",
            "Write the pilot validation method and pass/fail decision rule.",
        ),
    ]
    for field, gap, action in checks:
        if not _first_text(design_brief.get(field)):
            gaps.append({"field": field, "gap": gap, "action": action})

    if not _string_list(design_brief.get("mvp_scope")):
        gaps.append(
            {
                "field": "mvp_scope",
                "gap": "Pilot scope is not bounded.",
                "action": "Select the smallest MVP behavior that can prove workflow value.",
            }
        )
    if not _string_list(design_brief.get("risks")) and not _source_risks(source_ideas):
        gaps.append(
            {
                "field": "risks",
                "gap": "No pilot risks are captured.",
                "action": "Record operational, workflow, data, and adoption risks before kickoff.",
            }
        )

    source_evidence_count = sum(
        len(_string_list(idea.get("evidence_signals")))
        + len(_string_list(idea.get("inspiring_insights")))
        for idea in source_ideas
        if not idea.get("missing")
    )
    if source_evidence_count == 0:
        gaps.append(
            {
                "field": "source_evidence",
                "gap": "No linked source ideas include evidence signals or inspiring insights.",
                "action": "Attach at least one source signal, insight, or interview note before expansion.",
            }
        )
    return gaps


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
                sources.append({"idea_id": idea_id, "role": "supporting", "rank": rank})

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


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        if not idea.get("missing"):
            risks.extend(_string_list(idea.get("domain_risks")))
    return risks


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = re.sub(r"\s+", " ", str(value or "").strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(str(value).strip())
    return deduped
