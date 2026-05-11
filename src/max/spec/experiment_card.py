"""Generate deterministic experiment cards for validating one buildable idea."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


EXPERIMENT_CARD_SCHEMA_VERSION = "max-experiment-card/v1"

EXPERIMENT_CARD_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "idea_id",
    "title",
    "idea_title",
    "primary_hypothesis",
    "target_persona",
    "target_buyer",
    "workflow_context",
    "sample_size",
    "duration_days",
    "test_type",
    "test_description",
    "riskiest_assumptions",
    "success_metrics",
    "failure_signals",
    "recruitment_channels",
    "success_criteria",
    "rollback_triggers",
    "learnings_capture",
    "decision_proceed",
    "decision_iterate",
    "decision_stop",
    "seven_day_plan",
)

DIMENSION_NAMES = (
    "pain_severity",
    "addressable_scale",
    "build_effort",
    "composability",
    "competitive_density",
    "timing_fit",
    "compounding_value",
)
LOW_DIMENSION_THRESHOLD = 6.0


def generate_experiment_card(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
) -> dict[str, Any]:
    """Build a deterministic one-week experiment plan for a single idea."""
    target = _target_participant(unit)
    riskiest_assumptions = _riskiest_assumptions(unit, evaluation)

    return {
        "schema_version": EXPERIMENT_CARD_SCHEMA_VERSION,
        "kind": "max.experiment_card",
        "idea_id": unit.id,
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": unit.id,
            "status": unit.status,
            "domain": unit.domain,
            "category": str(unit.category),
            "evaluation_available": evaluation is not None,
            "recommendation": evaluation.recommendation if evaluation else None,
            "overall_score": evaluation.overall_score if evaluation else None,
        },
        "idea_summary": {
            "title": unit.title,
            "one_liner": unit.one_liner,
            "problem": unit.problem,
            "solution": unit.solution,
            "value_proposition": unit.value_proposition,
            "category": str(unit.category),
            "domain": unit.domain,
            "target_user": target["persona"],
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
            "current_workaround": unit.current_workaround,
            "why_now": unit.why_now,
        },
        "riskiest_assumptions": riskiest_assumptions,
        "primary_hypothesis": _primary_hypothesis(unit, target["persona"]),
        "target_participant": target,
        "recruitment_channel_suggestions": _recruitment_channels(unit),
        "minimum_viable_test": _minimum_viable_test(unit, riskiest_assumptions),
        "success_metrics": _success_metrics(unit, evaluation),
        "failure_signals": _failure_signals(unit, evaluation),
        "seven_day_execution_plan": _seven_day_execution_plan(unit),
        "instrumentation_notes": _instrumentation_notes(unit),
        "decision_rules": _decision_rules(evaluation),
    }


def render_experiment_card_csv(card: dict[str, Any]) -> str:
    """Render experiment card as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(EXPERIMENT_CARD_CSV_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerow(_experiment_card_csv_row(card or {}))  # type: ignore[arg-type]
    return output.getvalue()


def _experiment_card_csv_row(card: dict[str, Any]) -> dict[str, str]:
    """Build CSV row for experiment card."""
    idea_summary = card.get("idea_summary", {})
    target_participant = card.get("target_participant", {})
    minimum_viable_test = card.get("minimum_viable_test", {})
    success_metrics = card.get("success_metrics", [])
    failure_signals = card.get("failure_signals", [])
    riskiest_assumptions = card.get("riskiest_assumptions", [])
    recruitment_channels = card.get("recruitment_channel_suggestions", [])
    decision_rules = card.get("decision_rules", {})
    seven_day_plan = card.get("seven_day_execution_plan", [])

    return {
        "schema_version": _csv_cell(card.get("schema_version")),
        "kind": _csv_cell(card.get("kind")),
        "idea_id": _csv_cell(card.get("idea_id")),
        "title": _csv_cell(idea_summary.get("title")),
        "idea_title": _csv_cell(idea_summary.get("title")),
        "primary_hypothesis": _csv_cell(card.get("primary_hypothesis")),
        "target_persona": _csv_cell(target_participant.get("persona")),
        "target_buyer": _csv_cell(target_participant.get("buyer")),
        "workflow_context": _csv_cell(target_participant.get("workflow_context")),
        "sample_size": _csv_cell(target_participant.get("sample_size")),
        "duration_days": _csv_cell(minimum_viable_test.get("duration_days")),
        "test_type": _csv_cell(minimum_viable_test.get("type")),
        "test_description": _csv_cell(minimum_viable_test.get("description")),
        "riskiest_assumptions": _csv_cell(
            [f"{a.get('id')}: {a.get('assumption')}" for a in riskiest_assumptions if isinstance(a, dict)]
        ),
        "success_metrics": _csv_cell(
            [f"{m.get('metric')}: {m.get('target')}" for m in success_metrics if isinstance(m, dict)]
        ),
        "failure_signals": _csv_cell(
            [f"{s.get('signal')}: {s.get('threshold')}" for s in failure_signals if isinstance(s, dict)]
        ),
        "recruitment_channels": _csv_cell(
            [c.get("channel") for c in recruitment_channels if isinstance(c, dict)]
        ),
        "success_criteria": _csv_cell(decision_rules.get("proceed")),
        "rollback_triggers": _csv_cell(decision_rules.get("stop")),
        "learnings_capture": _csv_cell(card.get("instrumentation_notes")),
        "decision_proceed": _csv_cell(decision_rules.get("proceed")),
        "decision_iterate": _csv_cell(decision_rules.get("iterate")),
        "decision_stop": _csv_cell(decision_rules.get("stop")),
        "seven_day_plan": _csv_cell(
            [
                f"{day.get('day')}: {day.get('focus')} - {day.get('actions')}"
                for day in seven_day_plan
                if isinstance(day, dict)
            ]
        ),
    }


def _csv_cell(value: Any) -> str:
    """Format a value for CSV cell output."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_cell(key)}={_csv_cell(item)}"
            for key, item in sorted(value.items())
            if _csv_cell(item)
        )
    if isinstance(value, (list, tuple, set)):
        items = value if isinstance(value, list) else list(value)
        return " | ".join(_csv_cell(item) for item in items if _csv_cell(item))
    return _compact(value)


def _riskiest_assumptions(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
) -> list[dict[str, str]]:
    assumptions: list[dict[str, str]] = []

    for index, risk in enumerate(unit.domain_risks, start=1):
        risk = _compact(risk)
        if risk:
            assumptions.append(
                _assumption(
                    f"domain_risk_{index}",
                    "domain_risk",
                    risk,
                    "Domain-specific risk must be disproved before build scope is trusted.",
                    "Ask target participants to identify whether this risk blocks adoption.",
                )
            )

    missing_fields = [
        (
            "missing_specific_user",
            unit.specific_user,
            "The first adopter persona is specific enough to recruit and observe.",
            "Persona ambiguity can hide weak demand behind generic interest.",
        ),
        (
            "missing_buyer",
            unit.buyer,
            "A buyer or sponsor exists for adopting the solution.",
            "No buyer means validation may prove usage interest without a path to adoption.",
        ),
        (
            "missing_workflow_context",
            unit.workflow_context,
            "The idea fits into a concrete workflow that can be tested in one session.",
            "Workflow ambiguity makes success metrics hard to interpret.",
        ),
    ]
    for assumption_id, value, assumption, rationale in missing_fields:
        if not _compact(value):
            assumptions.append(
                _assumption(
                    assumption_id,
                    "idea_field",
                    assumption,
                    rationale,
                    "Use discovery questions to force a concrete participant, buyer, and workflow.",
                )
            )

    if evaluation is None:
        assumptions.append(
            _assumption(
                "missing_evaluation",
                "evaluation",
                "The idea has enough utility to justify a buildable experiment.",
                "No utility evaluation is available, so validation must test basic demand first.",
                "Prioritize pain, urgency, and willingness to try a rough workflow.",
            )
        )
    else:
        for index, weakness in enumerate(evaluation.weaknesses, start=1):
            weakness = _compact(weakness)
            if weakness:
                assumptions.append(
                    _assumption(
                        f"evaluation_weakness_{index}",
                        "evaluation_weakness",
                        weakness,
                        "Utility evaluation named this as a weakness.",
                        "Probe this weakness directly before expanding scope.",
                    )
                )
        for name in DIMENSION_NAMES:
            score = getattr(evaluation, name)
            if score.value < LOW_DIMENSION_THRESHOLD:
                label = name.replace("_", " ")
                assumptions.append(
                    _assumption(
                        f"low_{name}",
                        "evaluation_dimension",
                        f"{label} is strong enough for an MVP.",
                        f"{label} scored {score.value:.1f}/10 with confidence {score.confidence:.2f}.",
                        _dimension_probe(name),
                    )
                )

    if not assumptions:
        assumptions.append(
            _assumption(
                "baseline_demand",
                "idea",
                "Target users experience the stated problem often enough to try a lightweight MVP.",
                "Every buildable idea still needs direct demand validation.",
                "Confirm frequency, current workaround, and willingness to use the proposed workflow.",
            )
        )

    return assumptions[:5]


def _assumption(
    assumption_id: str,
    source: str,
    assumption: str,
    rationale: str,
    test_focus: str,
) -> dict[str, str]:
    return {
        "id": assumption_id,
        "source": source,
        "assumption": assumption,
        "rationale": rationale,
        "test_focus": test_focus,
    }


def _target_participant(unit: BuildableUnit) -> dict[str, Any]:
    persona = _compact(unit.specific_user) or _target_user_label(unit.target_users)
    workflow = _compact(unit.workflow_context) or "the workflow described by the problem statement"
    buyer = _compact(unit.buyer) or "the person accountable for adopting or funding the workflow"
    return {
        "persona": persona,
        "buyer": buyer,
        "workflow_context": workflow,
        "screening_criteria": [
            f"Currently owns or performs {workflow}.",
            f"Has experienced: {_compact(unit.problem) or unit.title}.",
            f"Can describe their current workaround: {_compact(unit.current_workaround) or 'manual or existing tool-based process'}.",
        ],
        "sample_size": 5,
    }


def _recruitment_channels(unit: BuildableUnit) -> list[dict[str, str]]:
    channels: list[dict[str, str]] = []
    first_customers = _compact(unit.first_10_customers)
    if first_customers:
        channels.append(
            {
                "channel": "first_10_customers",
                "rationale": first_customers,
                "ask": f"Invite 5 people from this pool to try a rough {unit.title} workflow.",
            }
        )

    domain = _compact(unit.domain)
    category = str(unit.category)
    if "cli" in category or "library" in category or "mcp" in unit.title.lower():
        channels.append(
            {
                "channel": "developer_communities",
                "rationale": "The idea targets technical workflow owners who can evaluate a rough tool quickly.",
                "ask": "Post a concise problem statement in relevant GitHub, Discord, Slack, Hacker News, or forum threads.",
            }
        )
    elif domain:
        channels.append(
            {
                "channel": "domain_communities",
                "rationale": f"The idea is tagged to {domain}, so domain-specific operators are the best early judges.",
                "ask": f"Reach out in {domain} communities and ask for a 20-minute workflow review.",
            }
        )
    else:
        channels.append(
            {
                "channel": "direct_outreach",
                "rationale": "Direct interviews are the fastest way to validate a single buildable idea.",
                "ask": "Send targeted outreach to people matching the participant criteria.",
            }
        )

    channels.append(
        {
            "channel": "existing_evidence_sources",
            "rationale": "Attached insights and signals point to places where the problem has already appeared.",
            "ask": "Return to the original evidence threads and ask participants to compare the proposed workflow to their workaround.",
        }
    )
    return _dedupe_by_channel(channels)[:3]


def _minimum_viable_test(
    unit: BuildableUnit,
    assumptions: list[dict[str, str]],
) -> dict[str, Any]:
    validation_plan = _compact(unit.validation_plan)
    test_type = "concierge_workflow" if not validation_plan else "scripted_validation"
    return {
        "type": test_type,
        "description": validation_plan
        or f"Simulate {unit.title} manually for target participants and compare it with their current workaround.",
        "duration_days": 7,
        "participant_count": 5,
        "steps": [
            "Screen participants against the target participant criteria.",
            "Ask each participant to walk through the current workaround and pain points.",
            f"Show or simulate the proposed solution: {_compact(unit.solution) or unit.title}.",
            "Collect commitment, objections, and observable workflow completion data.",
        ],
        "assumptions_tested": [assumption["id"] for assumption in assumptions],
    }


def _success_metrics(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
) -> list[dict[str, str]]:
    metrics = [
        {
            "metric": "qualified_participants",
            "target": "5 participants match the screening criteria within 7 days.",
            "why": "Recruiting speed tests whether the target segment is reachable.",
        },
        {
            "metric": "problem_confirmation",
            "target": "At least 4 of 5 participants report the problem as recurring and worth solving.",
            "why": "Confirms the problem statement has enough pull for an MVP.",
        },
        {
            "metric": "workflow_commitment",
            "target": "At least 3 of 5 participants agree to try the MVP, join a pilot, or provide a follow-up artifact.",
            "why": "Commitment is stronger evidence than positive feedback.",
        },
    ]
    if _compact(unit.value_proposition):
        metrics.append(
            {
                "metric": "value_proposition_fit",
                "target": f"At least 3 participants repeat the value in their own words: {unit.value_proposition}.",
                "why": "Tests whether the promised value is understandable and desired.",
            }
        )
    if evaluation and evaluation.overall_score >= 75:
        metrics.append(
            {
                "metric": "high_score_validation",
                "target": "No more than 1 participant names an unfixable adoption blocker.",
                "why": "A high utility score should survive direct participant scrutiny.",
            }
        )
    return metrics


def _failure_signals(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
) -> list[dict[str, str]]:
    signals = [
        {
            "signal": "weak_recruiting",
            "threshold": "Fewer than 3 qualified participants can be recruited in 7 days.",
            "response": "Revisit target participant and recruitment channels before building.",
        },
        {
            "signal": "low_pain",
            "threshold": "More than 2 participants describe the problem as rare, low-cost, or already solved.",
            "response": "Stop or narrow the idea to a sharper workflow.",
        },
        {
            "signal": "no_commitment",
            "threshold": "Fewer than 2 participants agree to a pilot, follow-up, or artifact review.",
            "response": "Do not build beyond a prototype until the value proposition changes.",
        },
    ]
    for risk in unit.domain_risks[:2]:
        if _compact(risk):
            signals.append(
                {
                    "signal": "domain_risk_confirmed",
                    "threshold": risk,
                    "response": "Treat the domain risk as a build gate or explicit non-goal.",
                }
            )
    if evaluation and evaluation.recommendation in {"no", "strong_no"}:
        signals.append(
            {
                "signal": "evaluation_rejection_confirmed",
                "threshold": f"Participant evidence confirms the {evaluation.recommendation} recommendation.",
                "response": "Stop the idea unless scope changes materially.",
            }
        )
    return signals


def _seven_day_execution_plan(unit: BuildableUnit) -> list[dict[str, str]]:
    return [
        {
            "day": "Day 1",
            "focus": "Experiment setup",
            "actions": "Define participant screener, outreach copy, interview script, and tracking sheet.",
            "deliverable": "Ready-to-run validation packet.",
        },
        {
            "day": "Day 2",
            "focus": "Recruitment",
            "actions": "Send outreach through the selected channels and schedule qualified participants.",
            "deliverable": "At least 5 scheduled or pending participant conversations.",
        },
        {
            "day": "Day 3",
            "focus": "Problem interviews",
            "actions": f"Validate frequency, current workaround, and cost of: {_compact(unit.problem) or unit.title}.",
            "deliverable": "Interview notes tagged by problem severity and workaround.",
        },
        {
            "day": "Day 4",
            "focus": "Solution simulation",
            "actions": f"Show or manually simulate: {_compact(unit.solution) or unit.one_liner}.",
            "deliverable": "Observed reactions, objections, and workflow completion notes.",
        },
        {
            "day": "Day 5",
            "focus": "Commitment test",
            "actions": "Ask for pilot participation, a follow-up artifact, waitlist signup, or buyer introduction.",
            "deliverable": "Commitment count and named blockers.",
        },
        {
            "day": "Day 6",
            "focus": "Evidence synthesis",
            "actions": "Score success metrics, cluster objections, and compare findings to riskiest assumptions.",
            "deliverable": "Experiment scorecard.",
        },
        {
            "day": "Day 7",
            "focus": "Decision",
            "actions": "Apply decision rules and choose proceed, iterate, or stop.",
            "deliverable": "Build decision with next-scope recommendation.",
        },
    ]


def _instrumentation_notes(unit: BuildableUnit) -> list[str]:
    notes = [
        "Log participant source, persona fit, workflow context, current workaround, and commitment outcome.",
        "Record every objection against the matching riskiest assumption ID.",
        "Separate polite interest from concrete commitments such as pilot access, artifacts, introductions, or paid intent.",
    ]
    if unit.evidence_signals or unit.inspiring_insights:
        notes.append("Link interview notes back to the source insight and signal IDs that motivated the idea.")
    if _compact(unit.validation_plan):
        notes.append("Capture pass/fail evidence for the stated validation plan separately from qualitative interview notes.")
    return notes


def _decision_rules(evaluation: UtilityEvaluation | None) -> dict[str, str]:
    proceed_score = "3 or more concrete commitments and no unfixable blocker"
    if evaluation and evaluation.recommendation in {"strong_yes", "yes"}:
        proceed_score = "3 or more concrete commitments, problem confirmed by 4 participants, and evaluation weaknesses not confirmed"
    return {
        "proceed": f"Build the MVP if {proceed_score}.",
        "iterate": "Revise target user, scope, or value proposition if pain is real but commitment or workflow fit is weak.",
        "stop": "Do not build if recruiting fails, fewer than 2 participants confirm recurring pain, or a critical blocker is confirmed.",
    }


def _primary_hypothesis(unit: BuildableUnit, persona: str) -> str:
    problem = _compact(unit.problem) or "the stated problem"
    solution = _compact(unit.solution) or unit.title
    workaround = _compact(unit.current_workaround)
    if workaround:
        return (
            f"{persona} will try {unit.title} because {problem} is painful enough "
            f"to replace or augment {workaround} with {solution}."
        )
    return f"{persona} will try {unit.title} because {problem} is painful enough to justify {solution}."


def _target_user_label(target_users: str) -> str:
    value = _compact(target_users)
    if value == "humans":
        return "human workflow owner"
    if value == "agents":
        return "agent workflow owner"
    if value == "both":
        return "human or agent workflow owner"
    return value or "target user"


def _dimension_probe(name: str) -> str:
    probes = {
        "pain_severity": "Ask how often the problem happens, what it costs, and what happens if it remains unsolved.",
        "addressable_scale": "Validate whether the workflow appears across multiple teams or communities.",
        "build_effort": "Test whether a narrow manual or no-code simulation can deliver the core value.",
        "composability": "Ask what tools, APIs, or workflows the MVP must integrate with to be useful.",
        "competitive_density": "Ask what alternatives participants already use and why they are insufficient.",
        "timing_fit": "Ask why solving this now matters more than it did six months ago.",
        "compounding_value": "Ask whether usage creates reusable data, integrations, or workflow leverage over time.",
    }
    return probes.get(name, "Probe the low-scoring evaluation dimension directly.")


def _dedupe_by_channel(channels: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for channel in channels:
        key = channel["channel"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(channel)
    return deduped


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def render_experiment_card_csv(card: dict[str, Any]) -> str:
    """Render experiment card as deterministic, spreadsheet-friendly CSV."""
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=list(EXPERIMENT_CARD_CSV_COLUMNS),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerow(_csv_row(card or {}))  # type: ignore[arg-type]
    return output.getvalue()


def _csv_row(card: dict[str, Any]) -> dict[str, str]:
    idea_summary = card.get("idea_summary")
    idea_summary = idea_summary if isinstance(idea_summary, dict) else {}
    target_participant = card.get("target_participant")
    target_participant = target_participant if isinstance(target_participant, dict) else {}
    mvt = card.get("minimum_viable_test")
    mvt = mvt if isinstance(mvt, dict) else {}
    decision_rules = card.get("decision_rules")
    decision_rules = decision_rules if isinstance(decision_rules, dict) else {}

    success_metrics = card.get("success_metrics")
    success_metrics = success_metrics if isinstance(success_metrics, list) else []
    failure_signals = card.get("failure_signals")
    failure_signals = failure_signals if isinstance(failure_signals, list) else []
    assumptions = card.get("riskiest_assumptions")
    assumptions = assumptions if isinstance(assumptions, list) else []
    channels = card.get("recruitment_channel_suggestions")
    channels = channels if isinstance(channels, list) else []
    plan = card.get("seven_day_execution_plan")
    plan = plan if isinstance(plan, list) else []

    return {
        "schema_version": _csv_cell(card.get("schema_version")),
        "kind": _csv_cell(card.get("kind")),
        "idea_id": _csv_cell(card.get("idea_id")),
        "title": _csv_cell(idea_summary.get("title")),
        "idea_title": _csv_cell(idea_summary.get("title")),
        "primary_hypothesis": _csv_cell(card.get("primary_hypothesis")),
        "target_persona": _csv_cell(target_participant.get("persona")),
        "target_buyer": _csv_cell(target_participant.get("buyer")),
        "workflow_context": _csv_cell(target_participant.get("workflow_context")),
        "sample_size": _csv_cell(target_participant.get("sample_size")),
        "test_type": _csv_cell(mvt.get("type")),
        "test_description": _csv_cell(mvt.get("description")),
        "duration_days": _csv_cell(mvt.get("duration_days")),
        "success_metrics": _csv_cell(
            [
                f"{m.get('metric')}: {m.get('target')}"
                for m in success_metrics
                if isinstance(m, dict)
            ]
        ),
        "failure_signals": _csv_cell(
            [
                f"{s.get('signal')}: {s.get('threshold')}"
                for s in failure_signals
                if isinstance(s, dict)
            ]
        ),
        "decision_proceed": _csv_cell(decision_rules.get("proceed")),
        "decision_iterate": _csv_cell(decision_rules.get("iterate")),
        "decision_stop": _csv_cell(decision_rules.get("stop")),
        "riskiest_assumptions": _csv_cell(
            [
                f"{a.get('id')}: {a.get('assumption')}"
                for a in assumptions
                if isinstance(a, dict)
            ]
        ),
        "recruitment_channels": _csv_cell(
            [c.get("channel") for c in channels if isinstance(c, dict)]
        ),
        "success_criteria": _csv_cell(decision_rules.get("proceed")),
        "rollback_triggers": _csv_cell(decision_rules.get("stop")),
        "learnings_capture": _csv_cell(card.get("instrumentation_notes")),
        "seven_day_plan": _csv_cell(
            [f"{d.get('day')}: {d.get('focus')}" for d in plan if isinstance(d, dict)]
        ),
    }


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "; ".join(
            f"{_csv_cell(key)}={_csv_cell(item)}"
            for key, item in sorted(value.items())
            if _csv_cell(item)
        )
    if isinstance(value, (list, tuple, set)):
        return " | ".join(_csv_cell(item) for item in _list(value) if _csv_cell(item))
    return _compact(value)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]
