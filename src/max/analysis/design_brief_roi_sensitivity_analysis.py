"""Deterministic ROI sensitivity analysis artifacts for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from max.analysis._design_brief_plan_common import (
    brief_context,
    design_brief_block,
    first_text,
    join_text,
    source_block,
    text,
)

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.roi_sensitivity_analysis"
SCHEMA_VERSION = "max.design_brief.roi_sensitivity_analysis.v1"


def build_design_brief_roi_sensitivity_analysis(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build deterministic ROI sensitivity guidance from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    evidence_references = _evidence_references(brief, context)
    evidence_gaps = _evidence_gaps(brief, context, evidence_references)
    value_drivers = _value_drivers(context)
    cost_drivers = _cost_drivers(context)
    scenario_assumptions = _scenario_assumptions(context, value_drivers, cost_drivers, evidence_gaps)
    break_even_risks = _break_even_risks(context, scenario_assumptions, evidence_gaps)
    confidence_band = _confidence_band(context, evidence_references, evidence_gaps)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "buyer": context["buyer"],
            "specific_user": context["target_user"],
            "workflow_context": context["workflow_context"],
        },
        "summary": {
            "confidence_level": confidence_band["level"],
            "base_case_payback_months": scenario_assumptions[1]["payback_months"],
            "break_even_risk_count": len(break_even_risks),
            "evidence_gap_count": len(evidence_gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "scenario_assumptions": scenario_assumptions,
        "value_drivers": value_drivers,
        "cost_drivers": cost_drivers,
        "break_even_risks": break_even_risks,
        "confidence_band": confidence_band,
        "evidence_references": evidence_references,
        "evidence_gaps": evidence_gaps,
        "open_questions": _open_questions(context, evidence_gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_roi_sensitivity_analysis(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    """Render an ROI sensitivity analysis as deterministic Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported ROI sensitivity analysis format: {fmt}")

    brief = report["design_brief"]
    lines = [
        f"# ROI Sensitivity Analysis: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Confidence: {report['confidence_band']['level']} ({report['confidence_band']['score']}/100)",
        "",
        "## Scenario Assumptions",
        "",
    ]
    for scenario in report["scenario_assumptions"]:
        lines.append(
            f"- **{scenario['id']} {scenario['name']}**: adoption {scenario['adoption_rate_percent']}%; "
            f"benefit ${scenario['annual_benefit_usd']}; cost ${scenario['implementation_cost_usd']}; "
            f"payback {scenario['payback_months']} months"
        )

    for key, title in (
        ("value_drivers", "Value Drivers"),
        ("cost_drivers", "Cost Drivers"),
        ("break_even_risks", "Break-Even Risks"),
        ("evidence_references", "Evidence References"),
        ("evidence_gaps", "Evidence Gaps"),
        ("open_questions", "Open Questions"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report[key]
        if not rows:
            lines.append("- None")
            continue
        for row in rows:
            label = row.get("name") or row.get("type") or row.get("id")
            detail = row.get("description") or row.get("rationale") or row.get("question") or row.get("impact")
            lines.append(f"- **{row['id']} {label}**: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def roi_sensitivity_analysis_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'ROI Sensitivity Analysis'))}-"
        f"roi-sensitivity-analysis.{extension}"
    )


def _value_drivers(context: dict[str, Any]) -> list[dict[str, str]]:
    source_id = context["primary_source_idea_id"]
    return [
        {
            "id": "V1",
            "name": "Workflow efficiency",
            "description": f"Reduced manual effort in {context['workflow_context']}.",
            "evidence": join_text(context["evidence"], "brief assumptions"),
            "source_idea_id": source_id,
        },
        {
            "id": "V2",
            "name": "Adoption or revenue lift",
            "description": f"{context['buyer']} sponsors adoption by {context['target_user']}.",
            "evidence": context["buyer"],
            "source_idea_id": source_id,
        },
        {
            "id": "V3",
            "name": "Risk and rework reduction",
            "description": "Value improves when launch, support, and compliance rework are avoided.",
            "evidence": join_text(context["risks"], "no explicit risk evidence"),
            "source_idea_id": source_id,
        },
    ]


def _cost_drivers(context: dict[str, Any]) -> list[dict[str, Any]]:
    scope_count = max(1, len(context["mvp_scope"]))
    risk_count = len(context["risks"])
    return [
        {
            "id": "C1",
            "name": "MVP implementation scope",
            "description": f"{scope_count} MVP scope item(s) drive product and engineering effort.",
            "relative_weight": scope_count + 2,
        },
        {
            "id": "C2",
            "name": "Validation and launch work",
            "description": "Discovery, pilot support, training, and launch acceptance work.",
            "relative_weight": 3 if context["evidence"] else 5,
        },
        {
            "id": "C3",
            "name": "Risk review buffer",
            "description": f"{risk_count} explicit risk signal(s) may add review or mitigation cost.",
            "relative_weight": max(1, risk_count + 1),
        },
    ]


def _scenario_assumptions(
    context: dict[str, Any],
    value_drivers: list[dict[str, str]],
    cost_drivers: list[dict[str, Any]],
    evidence_gaps: list[dict[str, str]],
) -> list[dict[str, Any]]:
    readiness = max(20.0, min(95.0, context["readiness_score"] or 45.0))
    scope_count = max(1, len(context["mvp_scope"]))
    gap_penalty = len(evidence_gaps) * 2500
    base_cost = 42000 + scope_count * 9000 + sum(driver["relative_weight"] for driver in cost_drivers) * 3500
    base_benefit = int((36000 + scope_count * 18000) * (readiness / 70.0))
    scenarios = (
        ("best_case", "Best case", 35, 1.35, 0.85, "Strong buyer pull and low delivery friction."),
        ("base_case", "Base case", 22, 1.0, 1.0, "Current brief assumptions hold through validation."),
        ("worst_case", "Worst case", 10, 0.55, 1.25, "Adoption, pricing, or validation assumptions slip."),
    )
    result = []
    for scenario_id, name, adoption, benefit_multiplier, cost_multiplier, rationale in scenarios:
        benefit = _round_money(base_benefit * benefit_multiplier)
        cost = _round_money(base_cost * cost_multiplier + gap_penalty)
        result.append(
            {
                "id": scenario_id,
                "name": name,
                "adoption_rate_percent": adoption,
                "annual_benefit_usd": benefit,
                "implementation_cost_usd": cost,
                "payback_months": max(1, round(cost / max(1, benefit) * 12)),
                "rationale": rationale,
                "primary_value_driver_ids": [driver["id"] for driver in value_drivers],
                "primary_cost_driver_ids": [driver["id"] for driver in cost_drivers],
            }
        )
    return result


def _break_even_risks(
    context: dict[str, Any],
    scenario_assumptions: list[dict[str, Any]],
    evidence_gaps: list[dict[str, str]],
) -> list[dict[str, str]]:
    base = scenario_assumptions[1]
    risks = [
        {
            "id": "B1",
            "name": "Adoption below base case",
            "impact": f"Payback exceeds {base['payback_months']} months if target users do not adopt the workflow.",
            "evidence": context["workflow_context"],
        },
        {
            "id": "B2",
            "name": "Implementation cost expansion",
            "impact": "Scope or integration growth can erase the base-case payback window.",
            "evidence": join_text(context["mvp_scope"], "MVP scope not specified"),
        },
    ]
    if evidence_gaps:
        risks.append(
            {
                "id": "B3",
                "name": "Evidence gap drag",
                "impact": "Missing buyer, workflow, pricing, or validation evidence makes break-even assumptions fragile.",
                "evidence": join_text([gap["id"] for gap in evidence_gaps], "none"),
            }
        )
    return risks


def _confidence_band(
    context: dict[str, Any],
    evidence_references: list[dict[str, str]],
    evidence_gaps: list[dict[str, str]],
) -> dict[str, Any]:
    score = round(max(10, min(95, context["readiness_score"] * 0.45 + len(evidence_references) * 9 - len(evidence_gaps) * 8)))
    level = "high" if score >= 75 else "medium" if score >= 50 else "low"
    return {
        "level": level,
        "score": score,
        "low_payback_confidence": max(5, score - 20),
        "high_payback_confidence": min(95, score + 15),
        "rationale": f"Based on readiness, {len(evidence_references)} evidence reference(s), and {len(evidence_gaps)} evidence gap(s).",
    }


def _evidence_references(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for field in ("validation_plan", "synthesis_rationale", "why_this_now"):
        value = text(brief.get(field))
        if value:
            references.append({"id": f"design_brief.{field}", "type": field, "description": value})
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        idea_id = str(idea["id"])
        for field in ("buyer", "workflow_context", "value_proposition", "evidence_signals", "validation_plan"):
            value = first_text(idea.get(field))
            if value:
                references.append({"id": f"{idea_id}.{field}", "type": field, "description": value})
    return references


def _evidence_gaps(
    brief: dict[str, Any],
    context: dict[str, Any],
    evidence_references: list[dict[str, str]],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    checks = (
        ("missing_pricing", "No pricing, budget, willingness-to-pay, or contract evidence is attached.", [brief.get("pricing_strategy"), brief.get("business_model"), *[idea.get("pricing_model") for idea in context["source_ideas"]]]),
        ("missing_buyer", "No explicit buyer or budget owner evidence is attached.", [] if "buyer" in context["fallbacks_used"] else [context["buyer"]]),
        ("missing_workflow", "No explicit workflow evidence is attached for benefit sizing.", [] if "workflow_context" in context["fallbacks_used"] else [context["workflow_context"]]),
        ("missing_validation", "No validation plan or evidence signals are attached.", context["evidence"]),
    )
    for gap_id, description, values in checks:
        if not any(text(value) for value in values):
            gaps.append({"id": gap_id, "description": description})
    if len(evidence_references) < 3:
        gaps.append({"id": "thin_evidence_base", "description": "Fewer than three independent evidence references support the sensitivity model."})
    return gaps


def _open_questions(context: dict[str, Any], evidence_gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    questions = [
        {"id": "Q1", "question": f"What measurable outcome proves value in {context['workflow_context']}?"},
        {"id": "Q2", "question": "What price, budget, or avoided-cost threshold defines break-even?"},
    ]
    if evidence_gaps:
        questions.append({"id": "Q3", "question": "Which missing evidence gap must close before ROI is used for prioritization?"})
    return questions


def _round_money(value: float) -> int:
    return int(round(value / 1000.0) * 1000)


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
