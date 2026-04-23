"""Feedback-driven revision briefs for buildable ideas."""

from __future__ import annotations

from typing import Any

from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation

REVISION_BRIEF_SCHEMA_VERSION = "max-revision-brief/v1"

_DIMENSION_LABELS = {
    "pain_severity": "pain severity",
    "addressable_scale": "addressable scale",
    "build_effort": "build effort",
    "composability": "composability",
    "competitive_density": "competitive density",
    "timing_fit": "timing fit",
    "compounding_value": "compounding value",
}

_CRITIQUE_FIELD_MAP = {
    "urgency": "problem",
    "buyer_clarity": "buyer",
    "specificity": "specific_user",
    "evidence_support": "evidence_rationale",
    "feasibility": "tech_approach",
    "differentiation": "value_proposition",
    "distribution_path": "first_10_customers",
    "domain_risk": "domain_risks",
    "novelty": "solution",
    "usefulness": "value_proposition",
    "quality_score": "value_proposition",
}

_TAG_FIELD_MAP = {
    "no_clear_buyer": "buyer",
    "generic_ai_assistant": "solution",
    "weak_evidence": "evidence_rationale",
    "impossible_data_access": "tech_approach",
    "low_willingness_to_pay": "value_proposition",
    "too_broad": "problem",
    "unclear_workflow": "workflow_context",
    "high_domain_risk": "domain_risks",
}

_FIELD_ORDER = [
    "problem",
    "specific_user",
    "buyer",
    "workflow_context",
    "current_workaround",
    "solution",
    "value_proposition",
    "why_now",
    "validation_plan",
    "first_10_customers",
    "domain_risks",
    "evidence_rationale",
    "tech_approach",
    "composability_notes",
]


def build_revision_brief(store: Any, idea_id: str) -> dict:
    """Build a deterministic, read-only revision brief for one idea.

    The store is only read. Missing optional review artifacts are represented
    explicitly so callers can distinguish "no defect" from "not reviewed yet".
    """
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise ValueError(f"Idea not found: {idea_id}")

    evaluation = _maybe_call(store, "get_evaluation", idea_id)
    latest_feedback = _normalize_feedback(_maybe_call(store, "get_latest_feedback", idea_id))
    critiques = _as_list(_maybe_call(store, "get_idea_critiques", idea_id))
    latest_critique = critiques[0] if critiques else None
    prior_art_matches = _as_list(_maybe_call(store, "get_prior_art_matches", idea_id))

    defects = _key_defects(
        unit,
        evaluation=evaluation,
        latest_feedback=latest_feedback,
        latest_critique=latest_critique,
        prior_art_matches=prior_art_matches,
    )
    changes = _recommended_changes(defects)
    evidence = _evidence_to_collect(unit, defects, prior_art_matches)
    fields = _fields_to_update(changes)

    brief = {
        "schema_version": REVISION_BRIEF_SCHEMA_VERSION,
        "idea_id": unit.id,
        "current_state": _current_state(unit, evaluation, latest_critique, prior_art_matches),
        "latest_feedback": latest_feedback,
        "key_defects": defects,
        "recommended_changes": changes,
        "evidence_to_collect": evidence,
        "fields_to_update": fields,
    }
    brief["agent_prompt"] = _agent_prompt(brief)
    return brief


def _maybe_call(store: Any, method_name: str, *args: Any) -> Any:
    method = getattr(store, method_name, None)
    if not callable(method):
        return None
    return method(*args)


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalize_feedback(feedback: Any) -> dict | None:
    if not isinstance(feedback, dict):
        return None
    return {
        "buildable_unit_id": feedback.get("buildable_unit_id"),
        "outcome": feedback.get("outcome"),
        "reason": feedback.get("reason", "") or "",
        "approval_score": feedback.get("approval_score"),
        "created_at": feedback.get("created_at"),
    }


def _current_state(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    latest_critique: dict | None,
    prior_art_matches: list[dict],
) -> dict:
    state = {
        "id": unit.id,
        "title": unit.title,
        "status": unit.status,
        "domain": unit.domain,
        "category": str(unit.category),
        "prior_art_status": unit.prior_art_status,
        "prior_art_match_count": len(prior_art_matches),
        "missing_fields": _missing_fields(unit),
        "quality": {
            "quality_score": unit.quality_score,
            "novelty_score": unit.novelty_score,
            "usefulness_score": unit.usefulness_score,
            "rejection_tags": list(unit.rejection_tags),
        },
    }
    if evaluation:
        state["evaluation"] = {
            "overall_score": evaluation.overall_score,
            "recommendation": evaluation.recommendation,
            "weaknesses": list(evaluation.weaknesses),
            "lowest_dimensions": _lowest_dimensions(evaluation),
        }
    else:
        state["evaluation"] = None
    if latest_critique:
        state["latest_critique"] = {
            "stage": latest_critique.get("stage"),
            "dimensions": dict(latest_critique.get("dimensions", {})),
            "reasoning": latest_critique.get("reasoning", "") or "",
            "rejection_tags": list(latest_critique.get("rejection_tags", [])),
            "created_at": latest_critique.get("created_at"),
        }
    else:
        state["latest_critique"] = None
    return state


def _missing_fields(unit: BuildableUnit) -> list[str]:
    missing = []
    for field in _FIELD_ORDER:
        value = getattr(unit, field)
        if value in ("", [], {}, None):
            missing.append(field)
    return missing


def _lowest_dimensions(evaluation: UtilityEvaluation) -> list[dict]:
    rows = []
    for name in _DIMENSION_LABELS:
        score = getattr(evaluation, name)
        rows.append(
            {
                "dimension": name,
                "label": _DIMENSION_LABELS[name],
                "value": score.value,
                "confidence": score.confidence,
                "reasoning": score.reasoning,
            }
        )
    return sorted(rows, key=lambda row: (row["value"], row["dimension"]))[:3]


def _key_defects(
    unit: BuildableUnit,
    *,
    evaluation: UtilityEvaluation | None,
    latest_feedback: dict | None,
    latest_critique: dict | None,
    prior_art_matches: list[dict],
) -> list[dict]:
    defects: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add(source: str, field: str, issue: str, severity: str = "medium") -> None:
        key = (source, field, issue)
        if key in seen:
            return
        seen.add(key)
        defects.append(
            {
                "source": source,
                "severity": severity,
                "field": field,
                "issue": issue,
            }
        )

    if latest_feedback and latest_feedback.get("outcome") in {"rejected", "abandoned"}:
        reason = latest_feedback.get("reason") or "latest reviewer feedback was negative"
        add("feedback", "value_proposition", f"Reviewer outcome is {latest_feedback['outcome']}: {reason}", "high")
    elif latest_feedback and latest_feedback.get("outcome") == "approved" and latest_feedback.get("approval_score"):
        score = latest_feedback["approval_score"]
        if score < 7:
            add("feedback", "value_proposition", f"Approval conviction is only {score}/10", "medium")

    if latest_critique:
        dims = latest_critique.get("dimensions", {})
        for name in sorted(dims):
            if name not in _CRITIQUE_FIELD_MAP:
                continue
            value = _float_or_none(dims.get(name))
            if value is not None and value < 6.0:
                severity = "high" if value < 4.0 else "medium"
                add("critique", _CRITIQUE_FIELD_MAP[name], f"{name} scored {value:.1f}/10 in latest critique", severity)
        reasoning = (latest_critique.get("reasoning") or "").strip()
        if reasoning:
            add("critique", "value_proposition", reasoning, "medium")
        for tag in latest_critique.get("rejection_tags", []):
            add("critique", _TAG_FIELD_MAP.get(tag, "value_proposition"), f"Rejection tag: {tag}", "high")

    for tag in unit.rejection_tags:
        add("quality_gate", _TAG_FIELD_MAP.get(tag, "value_proposition"), f"Persisted rejection tag: {tag}", "high")

    if evaluation:
        for weakness in evaluation.weaknesses:
            add("evaluation", _field_for_text(weakness), weakness, "medium")
        for dim in _lowest_dimensions(evaluation):
            if dim["value"] < 6.5:
                add(
                    "evaluation",
                    _field_for_dimension(dim["dimension"]),
                    f"{dim['label']} is a weak evaluation dimension at {dim['value']:.1f}/10: {dim['reasoning']}",
                    "medium",
                )
    else:
        add("evaluation", "validation_plan", "No formal utility evaluation is recorded", "medium")

    if unit.prior_art_status == "strong_match":
        title = prior_art_matches[0]["title"] if prior_art_matches else "existing prior art"
        add("prior_art", "solution", f"Strong prior-art match found: {title}", "high")
    elif unit.prior_art_status == "weak_match":
        title = prior_art_matches[0]["title"] if prior_art_matches else "similar prior art"
        add("prior_art", "value_proposition", f"Weak prior-art overlap found: {title}", "medium")
    elif unit.prior_art_status == "unchecked":
        add("prior_art", "validation_plan", "Prior-art status is unchecked", "low")

    for field in _missing_fields(unit):
        add("current_state", field, f"{field} is empty", "medium")

    return defects


def _recommended_changes(defects: list[dict]) -> list[dict]:
    changes = []
    used_fields: set[str] = set()
    for defect in defects:
        field = defect["field"]
        if field in used_fields:
            continue
        used_fields.add(field)
        changes.append(
            {
                "priority": len(changes) + 1,
                "field": field,
                "instruction": _instruction_for_field(field, defect),
                "addresses": [defect["issue"]],
            }
        )
    return changes[:8]


def _fields_to_update(changes: list[dict]) -> list[dict]:
    return [
        {
            "field": change["field"],
            "revision_instruction": change["instruction"],
            "source_issues": change["addresses"],
        }
        for change in changes
    ]


def _evidence_to_collect(
    unit: BuildableUnit,
    defects: list[dict],
    prior_art_matches: list[dict],
) -> list[dict]:
    fields = {defect["field"] for defect in defects}
    evidence: list[dict] = []

    def add(question: str, method: str, supports: list[str]) -> None:
        evidence.append(
            {
                "priority": len(evidence) + 1,
                "question": question,
                "method": method,
                "supports_fields": supports,
            }
        )

    if {"problem", "specific_user", "buyer", "workflow_context"} & fields:
        add(
            "Who has this problem urgently enough to change behavior or pay?",
            "Interview 5 target users and capture current workaround, frequency, and buyer role.",
            ["problem", "specific_user", "buyer", "workflow_context"],
        )
    if {"value_proposition", "solution"} & fields:
        add(
            "What concrete improvement makes this idea worth choosing?",
            "Run a landing-page or concierge test with a before/after success metric.",
            ["solution", "value_proposition", "validation_plan"],
        )
    if {"evidence_rationale", "why_now"} & fields or not unit.evidence_signals:
        add(
            "Which independent signals support urgency and timing?",
            "Collect at least 3 recent evidence signals from different sources and connect them to the claim.",
            ["evidence_rationale", "why_now"],
        )
    if {"tech_approach", "domain_risks"} & fields:
        add(
            "What is the riskiest build or data-access assumption?",
            "Build a thin technical spike and record the constraint, fallback, and residual risk.",
            ["tech_approach", "domain_risks", "validation_plan"],
        )
    if prior_art_matches:
        add(
            "How is this meaningfully different from the closest existing alternative?",
            "Compare the top prior-art matches on target user, workflow, capability, and distribution wedge.",
            ["solution", "value_proposition", "composability_notes"],
        )

    if not evidence:
        add(
            "What evidence would increase confidence in the next revision?",
            "Validate the main workflow with 3 likely users and document the strongest objection.",
            ["validation_plan", "evidence_rationale"],
        )
    return evidence[:6]


def _agent_prompt(brief: dict) -> str:
    fields = ", ".join(item["field"] for item in brief["fields_to_update"]) or "validation_plan"
    defects = "; ".join(defect["issue"] for defect in brief["key_defects"][:3]) or "No major defects found"
    evidence = brief["evidence_to_collect"][0]["question"] if brief["evidence_to_collect"] else "What evidence is still missing?"
    return (
        f"Revise buildable idea {brief['idea_id']} ({brief['current_state']['title']}). "
        f"Preserve the core idea, but update these fields: {fields}. "
        f"Address: {defects}. "
        f"Collect or cite evidence for: {evidence}. "
        "Return a complete revised BuildableUnit-compatible payload and do not change the idea id."
    )


def _instruction_for_field(field: str, defect: dict) -> str:
    issue = defect["issue"]
    instructions = {
        "problem": "Rewrite the problem around a narrow workflow, explicit pain, and observable current workaround.",
        "specific_user": "Name the exact user role, context, and trigger moment where the problem appears.",
        "buyer": "Identify the economic buyer or approver and why they would fund this.",
        "workflow_context": "Specify the workflow step, input, output, and handoff where the product is used.",
        "current_workaround": "Describe how users solve this today and why that workaround fails.",
        "solution": "Refocus the solution on the smallest differentiated capability that resolves the defect.",
        "value_proposition": "State a measurable outcome and why it beats the status quo or closest alternative.",
        "why_now": "Tie timing to recent market, technical, regulatory, or ecosystem evidence.",
        "validation_plan": "Turn validation into a concrete test with audience, method, metric, and pass/fail threshold.",
        "first_10_customers": "List reachable first-customer segments or channels with a concrete outreach path.",
        "domain_risks": "Replace generic risks with domain-specific risks plus mitigation or fallback.",
        "evidence_rationale": "Connect each important claim to specific evidence and note what evidence is still missing.",
        "tech_approach": "Constrain the MVP architecture and prove the riskiest dependency or integration path.",
        "composability_notes": "Explain how the idea plugs into existing tools and avoids duplicating prior art.",
    }
    base = instructions.get(field, "Revise this field so it directly addresses the defect.")
    return f"{base} Source issue: {issue}"


def _field_for_dimension(dimension: str) -> str:
    return {
        "pain_severity": "problem",
        "addressable_scale": "specific_user",
        "build_effort": "tech_approach",
        "composability": "composability_notes",
        "competitive_density": "value_proposition",
        "timing_fit": "why_now",
        "compounding_value": "value_proposition",
    }.get(dimension, "value_proposition")


def _field_for_text(text: str) -> str:
    lowered = text.lower()
    checks = [
        (("buyer", "pay", "budget", "willingness"), "buyer"),
        (("user", "persona", "specific"), "specific_user"),
        (("workflow", "process", "handoff"), "workflow_context"),
        (("evidence", "signal", "support"), "evidence_rationale"),
        (("prior art", "competitor", "competition", "differentiation"), "value_proposition"),
        (("technical", "feasible", "integration", "data access"), "tech_approach"),
        (("timing", "why now"), "why_now"),
        (("validation", "test"), "validation_plan"),
    ]
    for keywords, field in checks:
        if any(keyword in lowered for keyword in keywords):
            return field
    return "value_proposition"


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
