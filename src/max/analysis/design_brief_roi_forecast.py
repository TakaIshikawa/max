"""Deterministic ROI forecast export for persisted design briefs."""

from __future__ import annotations

import csv
import json
import math
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.roi_forecast.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "kind",
    "design_brief_id",
    "design_brief_title",
    "row_type",
    "item_id",
    "item_name",
    "low_usd",
    "high_usd",
    "expected_months",
    "confidence_score",
    "confidence_level",
    "basis",
    "rationale",
    "source_reference_ids",
    "action_text",
)


def build_design_brief_roi_forecast(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a deterministic ROI forecast from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    evidence_references = _evidence_references(design_brief, source_ideas)
    evidence_score = _evidence_score(design_brief, source_ideas, evidence_references)
    assumptions = _assumptions(design_brief, source_ideas, evidence_score)
    cost_bands = _implementation_cost_bands(design_brief, source_ideas)
    benefit_bands = _benefit_bands(design_brief, source_ideas, assumptions, evidence_score)
    payback_range = _payback_range(cost_bands, benefit_bands)
    confidence = _confidence_level(design_brief, evidence_score, evidence_references)
    next_actions = _next_actions(design_brief, confidence, evidence_references)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.roi_forecast",
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
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
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
            "implementation_cost_low_usd": cost_bands["total"]["low_usd"],
            "implementation_cost_high_usd": cost_bands["total"]["high_usd"],
            "annual_benefit_low_usd": benefit_bands["total_annual_benefit"]["low_usd"],
            "annual_benefit_high_usd": benefit_bands["total_annual_benefit"]["high_usd"],
            "payback_expected_months": payback_range["expected_months"],
            "confidence_level": confidence["level"],
            "evidence_reference_count": len(evidence_references),
        },
        "assumptions": assumptions,
        "implementation_cost_bands": cost_bands,
        "benefit_bands": benefit_bands,
        "payback_range": payback_range,
        "confidence_level": confidence,
        "evidence_references": evidence_references,
        "next_actions": next_actions,
        "source_ideas": source_ideas,
    }


def render_design_brief_roi_forecast(report: dict[str, Any], fmt: str = "json") -> str:
    """Render an ROI forecast as deterministic JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported ROI forecast format: {fmt}")

    brief = report["design_brief"]
    payback = report["payback_range"]
    confidence = report["confidence_level"]
    lines = [
        f"# ROI Forecast: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Buyer: {brief['buyer'] or 'TBD buyer'}",
        f"Workflow: {brief['workflow_context'] or 'TBD workflow'}",
        "",
        "## Forecast Summary",
        "",
        f"- Implementation cost: ${report['summary']['implementation_cost_low_usd']:,}"
        f"-${report['summary']['implementation_cost_high_usd']:,}",
        f"- Annual benefit: ${report['summary']['annual_benefit_low_usd']:,}"
        f"-${report['summary']['annual_benefit_high_usd']:,}",
        f"- Payback range: {payback['optimistic_months']}-{payback['conservative_months']} months",
        f"- Expected payback: {payback['expected_months']} months",
        f"- Confidence: {confidence['level']} ({confidence['score']}/100)",
        "",
        "## Assumptions",
        "",
    ]
    lines.extend(
        f"- **{item['id']}**: {item['assumption']} ({item['basis']})"
        for item in report["assumptions"]
    )

    lines.extend(["", "## Implementation Cost Bands", ""])
    for item in report["implementation_cost_bands"]["components"]:
        lines.append(
            f"- **{item['name']}**: ${item['low_usd']:,}-${item['high_usd']:,} - "
            f"{item['rationale']}"
        )

    lines.extend(["", "## Benefit Bands", ""])
    for item in report["benefit_bands"]["components"]:
        lines.append(
            f"- **{item['name']}**: ${item['low_usd']:,}-${item['high_usd']:,} annually - "
            f"{item['rationale']}"
        )

    lines.extend(["", "## Payback Range", ""])
    lines.extend(
        [
            f"- Optimistic: {payback['optimistic_months']} months",
            f"- Expected: {payback['expected_months']} months",
            f"- Conservative: {payback['conservative_months']} months",
            f"- Basis: {payback['basis']}",
        ]
    )

    lines.extend(["", "## Confidence", ""])
    lines.extend(
        [
            f"- Level: {confidence['level']}",
            f"- Score: {confidence['score']}/100",
            f"- Rationale: {confidence['rationale']}",
        ]
    )

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        lines.extend(
            f"- `{item['id']}` ({item['type']}): {item['description']}"
            for item in report["evidence_references"]
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {item}" for item in report["next_actions"])
    return "\n".join(lines).rstrip() + "\n"


def roi_forecast_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'ROI-Forecast'))}-roi-forecast."
        f"{extension}"
    )


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    source_reference_ids = _reference_ids(report)

    for item in report.get("assumptions") or []:
        rows.append(
            _csv_row(
                report,
                row_type="assumption",
                item_id=item.get("id"),
                item_name=item.get("assumption"),
                basis=item.get("basis"),
                source_reference_ids=source_reference_ids,
            )
        )

    cost_bands = report.get("implementation_cost_bands") or {}
    for item in cost_bands.get("components") or []:
        rows.append(
            _csv_row(
                report,
                row_type="implementation_cost_component",
                item_id=item.get("id"),
                item_name=item.get("name"),
                low_usd=item.get("low_usd"),
                high_usd=item.get("high_usd"),
                rationale=item.get("rationale"),
                source_reference_ids=source_reference_ids,
            )
        )
    if cost_bands.get("total"):
        total = cost_bands["total"]
        rows.append(
            _csv_row(
                report,
                row_type="implementation_cost_total",
                item_id="implementation_cost_total",
                item_name="Implementation cost total",
                low_usd=total.get("low_usd"),
                high_usd=total.get("high_usd"),
                source_reference_ids=source_reference_ids,
            )
        )

    benefit_bands = report.get("benefit_bands") or {}
    for item in benefit_bands.get("components") or []:
        rows.append(
            _csv_row(
                report,
                row_type="benefit_component",
                item_id=item.get("id"),
                item_name=item.get("name"),
                low_usd=item.get("low_usd"),
                high_usd=item.get("high_usd"),
                rationale=item.get("rationale"),
                source_reference_ids=source_reference_ids,
            )
        )
    if benefit_bands.get("total_annual_benefit"):
        total = benefit_bands["total_annual_benefit"]
        rows.append(
            _csv_row(
                report,
                row_type="benefit_total",
                item_id="total_annual_benefit",
                item_name="Annual benefit total",
                low_usd=total.get("low_usd"),
                high_usd=total.get("high_usd"),
                source_reference_ids=source_reference_ids,
            )
        )

    payback = report.get("payback_range") or {}
    if payback:
        rows.append(
            _csv_row(
                report,
                row_type="payback_range",
                item_id="payback_range",
                item_name=(
                    f"{_csv_text(payback.get('optimistic_months'))}-"
                    f"{_csv_text(payback.get('conservative_months'))} months"
                ),
                expected_months=payback.get("expected_months"),
                basis=payback.get("basis"),
                source_reference_ids=source_reference_ids,
            )
        )

    confidence = report.get("confidence_level") or {}
    if confidence:
        rows.append(
            _csv_row(
                report,
                row_type="confidence",
                item_id="confidence_level",
                item_name=confidence.get("level"),
                confidence_score=confidence.get("score"),
                confidence_level=confidence.get("level"),
                rationale=confidence.get("rationale"),
                source_reference_ids=source_reference_ids,
            )
        )

    for item in report.get("evidence_references") or []:
        rows.append(
            _csv_row(
                report,
                row_type="evidence_reference",
                item_id=item.get("id"),
                item_name=item.get("type"),
                rationale=item.get("description"),
                source_reference_ids=[item.get("id")],
            )
        )

    for index, action in enumerate(report.get("next_actions") or [], start=1):
        rows.append(
            _csv_row(
                report,
                row_type="next_action",
                item_id=f"next_action_{index}",
                item_name=f"Next action {index}",
                source_reference_ids=source_reference_ids,
                action_text=action,
            )
        )

    return rows


def _csv_row(report: dict[str, Any], **values: Any) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    row = {
        "schema_version": report.get("schema_version"),
        "kind": report.get("kind"),
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        **values,
    }
    return {column: _csv_text(row.get(column)) for column in CSV_COLUMNS}


def _reference_ids(report: dict[str, Any]) -> list[str]:
    return [item["id"] for item in report.get("evidence_references") or [] if item.get("id")]


def _assumptions(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence_score: int,
) -> list[dict[str, str]]:
    customer_segment = _first_text(
        design_brief.get("first_10_customers"),
        _field_values(source_ideas, "first_10_customers"),
        default="the first 10 target customers",
    )
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        default="the target workflow",
    )
    buyer = _first_text(
        design_brief.get("buyer"),
        _field_values(source_ideas, "buyer"),
        default="the accountable buyer",
    )
    assumptions = [
        {
            "id": "A1",
            "assumption": f"Initial adoption is modeled against {customer_segment}.",
            "basis": "first_10_customers and source idea customer fields",
        },
        {
            "id": "A2",
            "assumption": f"Value accrues through reduced friction in {workflow}.",
            "basis": "workflow_context, current_workaround, and value proposition fields",
        },
        {
            "id": "A3",
            "assumption": f"{buyer} can sponsor validation and budget decisions.",
            "basis": "buyer and design_status fields",
        },
    ]
    if evidence_score < 45:
        assumptions.append(
            {
                "id": "A4",
                "assumption": (
                    "Forecast uses conservative adoption and benefit ranges because linked "
                    "evidence is thin."
                ),
                "basis": "evidence references, source idea signals, and validation plan coverage",
            }
        )
    return assumptions


def _implementation_cost_bands(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    scope_count = max(1, len(_string_list(design_brief.get("mvp_scope"))))
    milestone_count = len(_string_list(design_brief.get("first_milestones")))
    risk_count = len(_string_list(design_brief.get("risks"))) + len(
        _field_values(source_ideas, "domain_risks")
    )
    stack_count = _stack_count(design_brief, source_ideas)
    complexity = max(3, scope_count + math.ceil(milestone_count / 2) + stack_count)
    risk_buffer = min(4, risk_count)

    product_low = 12000 + scope_count * 4500
    product_high = 24000 + scope_count * 8000
    engineering_low = 18000 + complexity * 6500
    engineering_high = 36000 + complexity * 11000
    validation_low = 9000 + risk_buffer * 3500
    validation_high = 18000 + risk_buffer * 6500
    risk_low = risk_buffer * 5000
    risk_high = risk_buffer * 12000

    components = [
        {
            "id": "implementation_design",
            "name": "Implementation design and product handoff",
            "low_usd": product_low,
            "high_usd": product_high,
            "rationale": (
                f"{scope_count} MVP scope item(s) require planning and stakeholder review."
            ),
        },
        {
            "id": "engineering_delivery",
            "name": "Engineering delivery",
            "low_usd": engineering_low,
            "high_usd": engineering_high,
            "rationale": f"Complexity score {complexity} from scope, milestones, and stack hints.",
        },
        {
            "id": "validation_and_launch",
            "name": "Validation and launch",
            "low_usd": validation_low,
            "high_usd": validation_high,
            "rationale": "Validation plan, launch readiness, and stakeholder acceptance work.",
        },
    ]
    if risk_buffer:
        components.append(
            {
                "id": "risk_review_buffer",
                "name": "Risk review buffer",
                "low_usd": risk_low,
                "high_usd": risk_high,
                "rationale": f"{risk_count} risk signal(s) add review and mitigation effort.",
            }
        )

    return {
        "currency": "USD",
        "components": components,
        "total": {
            "low_usd": sum(item["low_usd"] for item in components),
            "high_usd": sum(item["high_usd"] for item in components),
        },
    }


def _benefit_bands(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    assumptions: list[dict[str, str]],
    evidence_score: int,
) -> dict[str, Any]:
    scope_count = max(1, len(_string_list(design_brief.get("mvp_scope"))))
    readiness = float(design_brief.get("readiness_score") or 0.0)
    evidence_factor = 0.75 if evidence_score < 45 else 1.0 if evidence_score < 70 else 1.2
    readiness_factor = max(0.65, min(1.2, readiness / 80.0 if readiness else 0.75))
    customer_count = _customer_count(design_brief, source_ideas)
    workflow_text = _context_text(design_brief, source_ideas)
    efficiency_weight = (
        1.25
        if _has_any(
            workflow_text,
            ("manual", "handoff", "audit", "workflow", "support", "ops", "operations"),
        )
        else 0.85
    )
    revenue_weight = (
        1.15
        if _has_any(
            workflow_text,
            ("buyer", "customer", "revenue", "sales", "pricing", "market"),
        )
        else 0.8
    )

    efficiency_low = _round_money(
        22000 * scope_count * efficiency_weight * readiness_factor * evidence_factor
    )
    efficiency_high = _round_money(efficiency_low * (1.9 if evidence_score >= 45 else 1.45))
    revenue_low = _round_money(
        9000 * customer_count * revenue_weight * readiness_factor * evidence_factor
    )
    revenue_high = _round_money(revenue_low * (2.2 if evidence_score >= 45 else 1.5))

    components = [
        {
            "id": "efficiency_gain",
            "name": "Efficiency benefit",
            "low_usd": efficiency_low,
            "high_usd": efficiency_high,
            "rationale": (
                "Estimated annual value from reducing manual workflow effort and launch friction."
            ),
        },
        {
            "id": "adoption_or_revenue_gain",
            "name": "Adoption or revenue benefit",
            "low_usd": revenue_low,
            "high_usd": revenue_high,
            "rationale": (
                f"Modeled from {customer_count} early customer/account target(s) and buyer fit."
            ),
        },
    ]
    if any("conservative" in item["assumption"].lower() for item in assumptions):
        components.append(
            {
                "id": "thin_evidence_discount",
                "name": "Thin-evidence discount",
                "low_usd": 0,
                "high_usd": 0,
                "rationale": (
                    "Benefit bands are intentionally narrowed until primary evidence is attached."
                ),
            }
        )

    return {
        "currency": "USD",
        "components": components,
        "total_annual_benefit": {
            "low_usd": sum(item["low_usd"] for item in components),
            "high_usd": sum(item["high_usd"] for item in components),
        },
    }


def _payback_range(
    cost_bands: dict[str, Any],
    benefit_bands: dict[str, Any],
) -> dict[str, Any]:
    low_cost = cost_bands["total"]["low_usd"]
    high_cost = cost_bands["total"]["high_usd"]
    low_benefit = max(1, benefit_bands["total_annual_benefit"]["low_usd"])
    high_benefit = max(1, benefit_bands["total_annual_benefit"]["high_usd"])
    expected_cost = (low_cost + high_cost) / 2
    expected_benefit = (low_benefit + high_benefit) / 2
    return {
        "optimistic_months": _months(low_cost, high_benefit),
        "expected_months": _months(expected_cost, expected_benefit),
        "conservative_months": _months(high_cost, low_benefit),
        "basis": (
            "Payback is implementation cost divided by annualized benefit, expressed in months."
        ),
    }


def _confidence_level(
    design_brief: dict[str, Any],
    evidence_score: int,
    evidence_references: list[dict[str, str]],
) -> dict[str, Any]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    score = min(95, max(15, round(evidence_score * 0.65 + readiness * 0.35)))
    if score >= 75:
        level = "high"
    elif score >= 50:
        level = "medium"
    else:
        level = "low"
    rationale = (
        f"Based on readiness score {readiness:.1f}, "
        f"{len(evidence_references)} evidence reference(s), "
        "and linked source idea coverage."
    )
    return {"level": level, "score": score, "rationale": rationale}


def _evidence_references(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    if _has_value(design_brief.get("validation_plan")):
        references.append(
            {
                "id": "design_brief.validation_plan",
                "type": "validation_plan",
                "description": _clean(design_brief.get("validation_plan")),
            }
        )
    if _has_value(design_brief.get("synthesis_rationale")):
        references.append(
            {
                "id": "design_brief.synthesis_rationale",
                "type": "synthesis_rationale",
                "description": _clean(design_brief.get("synthesis_rationale")),
            }
        )

    for idea in source_ideas:
        if idea.get("missing"):
            continue
        idea_id = str(idea["id"])
        if _has_value(idea.get("evidence_rationale")):
            references.append(
                {
                    "id": f"{idea_id}.evidence_rationale",
                    "type": "source_idea_rationale",
                    "description": _clean(idea.get("evidence_rationale")),
                }
            )
        for signal_id in _string_list(idea.get("evidence_signals")):
            references.append(
                {
                    "id": signal_id,
                    "type": "evidence_signal",
                    "description": f"Linked evidence signal from source idea {idea_id}.",
                }
            )
        for insight_id in _string_list(idea.get("inspiring_insights")):
            references.append(
                {
                    "id": insight_id,
                    "type": "insight",
                    "description": f"Linked insight from source idea {idea_id}.",
                }
            )
    return _dedupe_references(references)


def _evidence_score(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence_references: list[dict[str, str]],
) -> int:
    score = min(40, len(evidence_references) * 8)
    score += min(20, len([idea for idea in source_ideas if not idea.get("missing")]) * 8)
    if _has_value(design_brief.get("validation_plan")):
        score += 15
    if _has_value(design_brief.get("buyer")):
        score += 10
    if _has_value(design_brief.get("first_10_customers")):
        score += 10
    if _has_value(design_brief.get("risks")):
        score += 5
    return min(100, score)


def _next_actions(
    design_brief: dict[str, Any],
    confidence: dict[str, Any],
    evidence_references: list[dict[str, str]],
) -> list[str]:
    actions = [
        "Confirm forecast bands with the buyer before committing implementation budget.",
        "Attach actual pilot conversion, cycle-time, or revenue measurements after validation.",
    ]
    if confidence["level"] == "low" or len(evidence_references) < 3:
        actions.insert(
            0,
            "Collect at least three independent evidence references before using this ROI forecast "
            "for prioritization.",
        )
    if not _has_value(design_brief.get("validation_plan")):
        actions.insert(
            0,
            "Define the validation plan and success threshold that will confirm payback "
            "assumptions.",
        )
    return actions


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
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

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


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        for item in _string_list(value):
            if item:
                return item
    return default


def _context_text(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for field in (
        "title",
        "domain",
        "theme",
        "buyer",
        "workflow_context",
        "merged_product_concept",
        "validation_plan",
        "first_10_customers",
    ):
        values.extend(_string_list(design_brief.get(field)))
    for field in (
        "buyer",
        "specific_user",
        "workflow_context",
        "current_workaround",
        "value_proposition",
        "first_10_customers",
    ):
        values.extend(_field_values(source_ideas, field))
    return " ".join(values).lower()


def _customer_count(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> int:
    text = " ".join(
        [
            *_string_list(design_brief.get("first_10_customers")),
            *_field_values(source_ideas, "first_10_customers"),
        ]
    ).lower()
    digits = [int(part) for part in text.replace("-", " ").split() if part.isdigit()]
    if digits:
        return max(1, min(25, max(digits)))
    if text:
        return 10
    return 3


def _stack_count(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> int:
    stacks: list[str] = []
    stacks.extend(_string_list(design_brief.get("suggested_stack")))
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        stacks.extend(_string_list(idea.get("suggested_stack")))
        stacks.extend(_string_list(idea.get("tech_approach")))
    return min(4, len(_dedupe(stacks)))


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _months(cost: float, annual_benefit: float) -> int:
    return max(1, int(math.ceil((cost / max(1.0, annual_benefit)) * 12)))


def _round_money(value: float) -> int:
    return int(round(value / 1000.0) * 1000)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _dedupe_references(references: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in references:
        item_id = item["id"]
        if item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return deduped


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return "; ".join(text for item in value if (text := _csv_text(item)))
    if isinstance(value, dict):
        return "; ".join(
            text
            for key, item in value.items()
            if (text := f"{_csv_text(key)}: {_csv_text(item)}".strip(": "))
        )
    return str(value).strip()


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_") or "design-brief"
