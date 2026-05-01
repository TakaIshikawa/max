"""Deterministic unit economics reports for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.unit_economics.v1"


def build_design_brief_unit_economics(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a deterministic unit economics report from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    evaluations = [store.get_evaluation(idea_id) for idea_id in source_idea_ids]
    evaluations = [evaluation for evaluation in evaluations if evaluation is not None]
    evidence_signal_ids = sorted(
        {
            signal_id
            for idea in source_ideas
            for signal_id in _string_list(idea.get("evidence_signals"))
        }
    )
    readiness_score = float(design_brief.get("readiness_score") or 0.0)
    average_evaluation = _average_evaluation_score(evaluations)
    confidence = _confidence(readiness_score, average_evaluation, len(evidence_signal_ids))
    assumptions = _assumptions(design_brief, source_ideas, confidence)
    cost_drivers = _cost_drivers(design_brief, source_ideas, average_evaluation)
    payback_bands = _payback_bands(assumptions, cost_drivers, confidence)
    risks = _risks(design_brief, source_ideas, confidence, evidence_signal_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.unit_economics",
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
            "readiness_score": readiness_score,
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
            "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer")),
            "specific_user": _first_text(
                design_brief.get("specific_user"),
                _field_values(source_ideas, "specific_user"),
            ),
            "workflow_context": _first_text(
                design_brief.get("workflow_context"),
                _field_values(source_ideas, "workflow_context"),
            ),
        },
        "summary": {
            "gross_margin_band": payback_bands["gross_margin_band"],
            "expected_payback_months": payback_bands["expected_months"],
            "confidence_level": confidence["level"],
            "evidence_signal_count": len(evidence_signal_ids),
        },
        "assumptions": assumptions,
        "cost_drivers": cost_drivers,
        "payback_bands": payback_bands,
        "risks": risks,
        "validation_questions": _validation_questions(design_brief, assumptions, cost_drivers),
        "confidence": confidence,
        "source_ideas": source_ideas,
    }


def render_design_brief_unit_economics(report: dict[str, Any], fmt: str = "json") -> str:
    """Render unit economics as deterministic JSON or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported unit economics format: {fmt}")

    brief = report["design_brief"]
    payback = report["payback_bands"]
    confidence = report["confidence"]
    lines = [
        f"# Unit Economics: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Buyer: {brief['buyer'] or 'TBD buyer'}",
        f"Workflow: {brief['workflow_context'] or 'TBD workflow'}",
        f"Confidence: {confidence['level']} ({confidence['score']}/100)",
        "",
        "## Summary",
        "",
        f"- Gross margin band: {payback['gross_margin_band']}",
        f"- Expected payback: {payback['expected_months']} months",
        f"- Conservative payback: {payback['conservative_months']} months",
        f"- Basis: {payback['basis']}",
        "",
        "## Assumptions",
        "",
    ]
    lines.extend(
        f"- **{item['id']}**: {item['label']} = {item['value']} ({item['basis']})"
        for item in report["assumptions"]
    )
    lines.extend(["", "## Cost Drivers", ""])
    lines.extend(
        f"- **{item['name']}**: {item['direction']} - {item['rationale']}"
        for item in report["cost_drivers"]
    )
    lines.extend(["", "## Payback Bands", ""])
    lines.extend(
        [
            f"- Optimistic: {payback['optimistic_months']} months",
            f"- Expected: {payback['expected_months']} months",
            f"- Conservative: {payback['conservative_months']} months",
            f"- Gross margin: {payback['gross_margin_band']}",
        ]
    )
    lines.extend(["", "## Risks", ""])
    lines.extend(
        f"- **{risk['severity']}**: {risk['risk']} - {risk['mitigation']}"
        for risk in report["risks"]
    )
    lines.extend(["", "## Validation Questions", ""])
    lines.extend(f"- {question}" for question in report["validation_questions"])
    return "\n".join(lines).rstrip() + "\n"


def unit_economics_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    brief_id = _filename_part(str(design_brief["id"]))
    title = _filename_part(str(design_brief.get("title") or ""))
    title_part = f"-{title}" if title else ""
    return f"{brief_id}{title_part}-unit-economics.{extension}"


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ordered_ids = list(
        dict.fromkeys(
            [
                design_brief.get("lead_idea_id"),
                *list(design_brief.get("source_idea_ids") or []),
                *[source.get("idea_id") for source in design_brief.get("sources", [])],
            ]
        )
    )
    ideas: list[dict[str, Any]] = []
    for idea_id in ordered_ids:
        if not idea_id:
            continue
        unit = store.get_buildable_unit(str(idea_id))
        if not unit:
            ideas.append({"id": str(idea_id), "missing": True})
            continue
        ideas.append(unit.model_dump(mode="json"))
    return ideas


def _assumptions(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    confidence: dict[str, Any],
) -> list[dict[str, str]]:
    buyer = _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer")
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        "target workflow",
    )
    value = _first_text(
        design_brief.get("value_proposition"),
        _field_values(source_ideas, "value_proposition"),
        "validated workflow value",
    )
    margin = "70-80%" if confidence["score"] >= 70 else "60-75%"
    return [
        {
            "id": "assumption_buyer_budget",
            "label": "Budget owner",
            "value": buyer,
            "basis": "design brief buyer and source idea buyer fields",
        },
        {
            "id": "assumption_value_metric",
            "label": "Value metric",
            "value": f"successful {workflow} outcome",
            "basis": "workflow context from the design brief lineage",
        },
        {
            "id": "assumption_margin",
            "label": "Gross margin target",
            "value": margin,
            "basis": f"{confidence['level']} confidence from readiness and evidence coverage",
        },
        {
            "id": "assumption_willingness_to_pay",
            "label": "Willingness to pay anchor",
            "value": value,
            "basis": "value proposition from the brief and source ideas",
        },
    ]


def _cost_drivers(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    average_evaluation: float | None,
) -> list[dict[str, str]]:
    stack_terms = " ".join(
        str(item)
        for idea in source_ideas
        for item in list((idea.get("suggested_stack") or {}).values())
    ).lower()
    technical_basis = _first_text(
        design_brief.get("technical_approach"),
        design_brief.get("tech_approach"),
        *_field_values(source_ideas, "tech_approach"),
        "implementation complexity from source ideas",
    )
    data_direction = "variable"
    if any(term in stack_terms for term in ("llm", "ai", "model", "openai")):
        data_direction = "usage-sensitive"
    if average_evaluation is not None and average_evaluation >= 80:
        delivery_direction = "moderate"
    else:
        delivery_direction = "high-touch"
    return [
        {
            "id": "cost_driver_delivery",
            "name": "Implementation and onboarding",
            "direction": delivery_direction,
            "rationale": technical_basis,
        },
        {
            "id": "cost_driver_runtime",
            "name": "Runtime and integration usage",
            "direction": data_direction,
            "rationale": "cost scales with workflow volume, integrations, and hosted service usage",
        },
        {
            "id": "cost_driver_validation",
            "name": "Buyer validation and support",
            "direction": "front-loaded",
            "rationale": _first_text(
                design_brief.get("validation_plan"),
                *_field_values(source_ideas, "validation_plan"),
                "validation requires direct buyer review before scaling",
            ),
        },
    ]


def _payback_bands(
    assumptions: list[dict[str, str]],
    cost_drivers: list[dict[str, str]],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    expected = 9 if confidence["score"] >= 75 else 12 if confidence["score"] >= 55 else 15
    if any(driver["direction"] == "high-touch" for driver in cost_drivers):
        expected += 2
    margin = next(
        (item["value"] for item in assumptions if item["id"] == "assumption_margin"),
        "60-75%",
    )
    return {
        "optimistic_months": max(3, expected - 4),
        "expected_months": expected,
        "conservative_months": expected + 6,
        "gross_margin_band": margin,
        "basis": "derived from readiness, evidence coverage, evaluation score, and delivery cost profile",
    }


def _risks(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    confidence: dict[str, Any],
    evidence_signal_ids: list[str],
) -> list[dict[str, str]]:
    domain_risks = [
        str(risk)
        for risk in [
            *list(design_brief.get("risks") or []),
            *[
                risk
                for idea in source_ideas
                for risk in _string_list(idea.get("domain_risks"))
            ],
        ]
        if str(risk).strip()
    ]
    risks = [
        {
            "id": "risk_cost_to_serve",
            "severity": "medium",
            "risk": "Cost to serve may rise faster than customer value if integrations are bespoke.",
            "mitigation": "Validate repeatable onboarding tasks and cap custom work during pilots.",
        },
        {
            "id": "risk_payback_evidence",
            "severity": "high" if confidence["score"] < 55 else "medium",
            "risk": "Payback assumptions need direct buyer confirmation before launch planning.",
            "mitigation": "Run pricing and willingness-to-pay interviews with the target buyer.",
        },
    ]
    if not evidence_signal_ids:
        risks.append(
            {
                "id": "risk_missing_market_evidence",
                "severity": "high",
                "risk": "No linked evidence signals support the unit economics assumptions.",
                "mitigation": "Attach market, pricing, or usage evidence before treating economics as validated.",
            }
        )
    if domain_risks:
        risks.append(
            {
                "id": "risk_domain",
                "severity": "medium",
                "risk": domain_risks[0],
                "mitigation": "Convert the top domain risk into an explicit validation milestone.",
            }
        )
    return risks


def _validation_questions(
    design_brief: dict[str, Any],
    assumptions: list[dict[str, str]],
    cost_drivers: list[dict[str, str]],
) -> list[str]:
    buyer = _first_text(design_brief.get("buyer"), "the target buyer")
    value_metric = next(
        (item["value"] for item in assumptions if item["id"] == "assumption_value_metric"),
        "the proposed value metric",
    )
    primary_cost = cost_drivers[0]["name"].lower()
    return [
        f"What budget line would {buyer} use for {value_metric}?",
        f"Which {primary_cost} activities must be standardized before pilots scale?",
        "What usage threshold creates a clear expansion or upgrade moment?",
        "What payback window would make the buyer comfortable approving a first paid pilot?",
    ]


def _confidence(
    readiness_score: float,
    average_evaluation: float | None,
    evidence_signal_count: int,
) -> dict[str, Any]:
    score = int(round(readiness_score * 0.45))
    if average_evaluation is not None:
        score += int(round(average_evaluation * 0.35))
    else:
        score += 15
    score += min(evidence_signal_count * 7, 20)
    score = max(0, min(100, score))
    level = "high" if score >= 75 else "medium" if score >= 55 else "low"
    return {
        "score": score,
        "level": level,
        "drivers": [
            f"readiness_score={readiness_score:.1f}",
            f"average_evaluation={average_evaluation:.1f}" if average_evaluation is not None else "average_evaluation=missing",
            f"evidence_signal_count={evidence_signal_count}",
        ],
    }


def _average_evaluation_score(evaluations: list[Any]) -> float | None:
    scores = [float(evaluation.overall_score or 0.0) for evaluation in evaluations]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    return [str(idea.get(field) or "") for idea in source_ideas if str(idea.get(field) or "").strip()]


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            nested = _first_text(*value)
            if nested:
                return nested
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")
