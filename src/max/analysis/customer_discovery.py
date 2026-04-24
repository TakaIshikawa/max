"""Deterministic customer discovery scripts for individual ideas."""

from __future__ import annotations

from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation


def _clean(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _profile_list(unit: BuildableUnit) -> list[str]:
    user = _clean(unit.specific_user, _clean(unit.target_users, "prospective user"))
    buyer = _clean(unit.buyer, "economic buyer or team lead responsible for the workflow")
    workflow = _clean(unit.workflow_context, "the workflow affected by this problem")
    first_customers = _clean(unit.first_10_customers, "")

    profiles = [
        f"Primary user: {user} who regularly handles {workflow}.",
        f"Buyer or sponsor: {buyer} who owns budget, risk, or adoption for {workflow}.",
    ]
    if first_customers:
        profiles.append(f"Early adopter segment: {first_customers}.")
    return profiles


def _experiment_context(validation_experiments: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for experiment in validation_experiments[:5]:
        hypothesis = _clean(experiment.get("hypothesis"), "the current validation hypothesis")
        metric = _clean(experiment.get("success_metric"), "the planned success metric")
        status = _clean(experiment.get("status"), "planned")
        lines.append(f"{hypothesis} ({status}; metric: {metric})")
    return lines


def generate_customer_discovery_script(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None = None,
    evidence_density: dict[str, Any] | None = None,
    validation_experiments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, template-based discovery script for one idea."""
    validation_experiments = validation_experiments or []
    evidence_density = evidence_density or {}

    user = _clean(unit.specific_user, _clean(unit.target_users, "prospective user"))
    buyer = _clean(unit.buyer, "team lead or budget owner")
    workflow = _clean(unit.workflow_context, "their current workflow")
    workaround = _clean(unit.current_workaround, "their current workaround")
    problem = _clean(unit.problem, "the problem this idea targets")
    solution = _clean(unit.solution, "the proposed solution")
    value = _clean(unit.value_proposition, "the expected value")
    why_now = _clean(unit.why_now, "why this problem matters now")
    validation_plan = _clean(unit.validation_plan, "a lightweight validation plan")

    interview_goals = [
        f"Confirm that {user} experiences this problem with enough frequency and urgency.",
        f"Map the current {workflow}, including tools, handoffs, delays, and failure points.",
        f"Understand whether {buyer} would sponsor a change and what proof they need.",
    ]
    if evaluation:
        interview_goals.append(
            f"Validate the evaluation thesis: {evaluation.recommendation} at "
            f"{evaluation.overall_score:.1f}/100, especially strengths and weaknesses."
        )
    if validation_experiments:
        interview_goals.append("Use the conversation to sharpen existing validation experiments.")

    screening_questions = [
        {
            "prompt": f"What is your role in {workflow}?",
            "rationale": "Qualifies whether the respondent directly uses, buys, or influences the workflow.",
            "source": "idea_profile",
        },
        {
            "prompt": f"How often do you encounter: {problem}?",
            "rationale": "Filters for real and recurring exposure to the target pain.",
            "source": "problem",
        },
        {
            "prompt": f"What do you use today instead, including {workaround}?",
            "rationale": "Screens out respondents without an active workaround or budgeted pain.",
            "source": "current_workaround",
        },
    ]

    discovery_questions = [
        {
            "prompt": f"Walk me through the last time {problem} showed up in {workflow}.",
            "rationale": "Anchors the interview in a recent concrete incident.",
            "source": "problem",
        },
        {
            "prompt": "What happened before and after that moment?",
            "rationale": "Reveals upstream triggers, downstream consequences, and hidden stakeholders.",
            "source": "workflow_context",
        },
        {
            "prompt": "What did the issue cost you in time, money, risk, or missed opportunities?",
            "rationale": "Quantifies pain severity and willingness to change.",
            "source": "value_proposition",
        },
        {
            "prompt": f"What makes this more or less urgent now: {why_now}?",
            "rationale": "Tests timing fit without pitching.",
            "source": "why_now",
        },
        {
            "prompt": f"Who else would need to approve or use a solution for {workflow}?",
            "rationale": "Separates user pain from buyer authority and adoption constraints.",
            "source": "buyer",
        },
    ]

    demo_prompts = [
        f"Show a low-fidelity walkthrough of: {solution}. Ask what feels useful, unnecessary, or missing.",
        f"Ask the respondent to compare the concept against {workaround}, using their last real incident.",
        f"Ask what proof would make {buyer} comfortable piloting this in {workflow}.",
    ]

    disconfirming_questions = [
        {
            "prompt": "When is this problem annoying but not worth solving?",
            "rationale": "Finds low-urgency segments and false-positive demand.",
            "source": "disconfirmation",
        },
        {
            "prompt": f"What would make you keep using {workaround} instead of switching?",
            "rationale": "Surfaces switching costs, inertia, and incumbent advantages.",
            "source": "current_workaround",
        },
        {
            "prompt": f"If {solution} existed today, why might your team still decline to adopt it?",
            "rationale": "Tests adoption blockers before building.",
            "source": "solution",
        },
    ]

    success_signals = [
        f"Respondent can describe a recent, specific incident involving {problem}.",
        "Respondent has an active workaround, budget owner, or escalation path.",
        f"Respondent agrees that {value} would be meaningful if delivered.",
        f"Respondent names a plausible next step aligned with: {validation_plan}.",
    ]

    if evidence_density:
        density_score = evidence_density.get("density_score")
        signal_count = evidence_density.get("signal_count", 0)
        if density_score is not None:
            success_signals.append(
                f"Conversation adds first-hand evidence to a current density score of {density_score} "
                f"from {signal_count} signal(s)."
            )

    for context in _experiment_context(validation_experiments):
        disconfirming_questions.append(
            {
                "prompt": f"What evidence would prove this hypothesis wrong: {context}?",
                "rationale": "Connects the interview to existing validation experiment risk.",
                "source": "validation_experiment",
            }
        )
        success_signals.append(f"Interview produces evidence for or against: {context}.")

    follow_up_artifacts = [
        "Interview notes with verbatim problem statements and ranked pain points.",
        "Stakeholder map covering user, buyer, approver, and implementation owner.",
        "Updated validation plan with next experiment, sample target, and success metric.",
    ]
    if validation_experiments:
        follow_up_artifacts.append("Validation experiment updates with status, result summary, and evidence URLs.")

    return {
        "idea_id": unit.id,
        "idea_title": unit.title,
        "interview_goals": interview_goals,
        "target_respondent_profiles": _profile_list(unit),
        "screening_questions": screening_questions,
        "discovery_questions": discovery_questions,
        "demo_prompts": demo_prompts,
        "disconfirming_questions": disconfirming_questions,
        "success_signals": success_signals,
        "follow_up_artifacts": follow_up_artifacts,
        "sections": {
            "screening": {
                "goal": "Qualify respondent fit before spending interview time.",
                "questions": screening_questions,
            },
            "interview": {
                "goal": "Understand the workflow, pain, buying path, and reaction to the concept.",
                "questions": discovery_questions,
                "demo_prompts": demo_prompts,
                "disconfirming_questions": disconfirming_questions,
            },
            "follow_up": {
                "goal": "Turn the conversation into validation evidence and next actions.",
                "artifacts": follow_up_artifacts,
                "success_signals": success_signals,
            },
        },
    }
