"""Deterministic unit economics reports for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.unit_economics.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "kind",
    "design_brief_id",
    "design_brief_title",
    "section",
    "row_id",
    "label",
    "metric",
    "value",
    "low_usd",
    "high_usd",
    "months",
    "gross_margin_band",
    "direction",
    "motion",
    "severity",
    "basis",
    "note",
    "source_idea_ids",
)


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
    revenue_model = _revenue_model(design_brief, source_ideas, confidence)
    acquisition_channels = _acquisition_channels(design_brief, source_ideas, evidence_signal_ids)
    cost_drivers = _cost_drivers(design_brief, source_ideas, average_evaluation)
    payback_bands = _payback_bands(assumptions, revenue_model, cost_drivers, confidence)
    gross_margin_risk_notes = _gross_margin_risk_notes(
        design_brief,
        source_ideas,
        revenue_model,
        cost_drivers,
        confidence,
        evidence_signal_ids,
    )
    sensitivity_cases = _sensitivity_cases(payback_bands, revenue_model, cost_drivers, confidence)
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
            "buyer": _first_text(
                design_brief.get("buyer"),
                _field_values(source_ideas, "buyer"),
                "target buyer",
            ),
            "specific_user": _first_text(
                design_brief.get("specific_user"),
                _field_values(source_ideas, "specific_user"),
                "target user",
            ),
            "workflow_context": _first_text(
                design_brief.get("workflow_context"),
                _field_values(source_ideas, "workflow_context"),
                "target workflow",
            ),
        },
        "summary": {
            "gross_margin_band": payback_bands["gross_margin_band"],
            "expected_payback_months": payback_bands["expected_months"],
            "target_monthly_price_band_usd": revenue_model["target_monthly_price_band_usd"],
            "confidence_level": confidence["level"],
            "evidence_signal_count": len(evidence_signal_ids),
        },
        "assumptions": assumptions,
        "revenue_model": revenue_model,
        "acquisition_channels": acquisition_channels,
        "cost_drivers": cost_drivers,
        "payback_bands": payback_bands,
        "gross_margin_risk_notes": gross_margin_risk_notes,
        "sensitivity_cases": sensitivity_cases,
        "risks": risks,
        "validation_questions": _validation_questions(
            design_brief,
            assumptions,
            revenue_model,
            acquisition_channels,
            cost_drivers,
        ),
        "confidence": confidence,
        "source_ideas": source_ideas,
    }


def render_design_brief_unit_economics(report: dict[str, Any], fmt: str = "json") -> str:
    """Render unit economics as deterministic JSON, CSV, or Markdown."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
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
    revenue = report["revenue_model"]
    lines.extend(
        [
            "",
            "## Revenue Model",
            "",
            f"- **Packaging**: {revenue['packaging']}",
            f"- **Pricing basis**: {revenue['pricing_basis']}",
            f"- **Target monthly price band**: "
            f"${revenue['target_monthly_price_band_usd']['low']:,}-"
            f"${revenue['target_monthly_price_band_usd']['high']:,}",
            f"- **Expansion trigger**: {revenue['expansion_trigger']}",
            f"- **Source ideas**: {', '.join(revenue['source_idea_ids']) or 'None'}",
            "",
            "## Acquisition Channels",
            "",
        ]
    )
    lines.extend(
        f"- **{item['channel']}**: {item['motion']} - {item['rationale']}"
        for item in report["acquisition_channels"]
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
    lines.extend(["", "## Gross Margin Risks", ""])
    lines.extend(
        f"- **{risk['severity']}**: {risk['note']} - {risk['watch_metric']}"
        for risk in report["gross_margin_risk_notes"]
    )
    lines.extend(["", "## Sensitivity Cases", ""])
    lines.extend(
        f"- **{case['case']}**: {case['payback_months']} months, "
        f"{case['gross_margin_band']} margin - {case['assumption_shift']}"
        for case in report["sensitivity_cases"]
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
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    brief_id = _filename_part(str(design_brief["id"]))
    title = _filename_part(str(design_brief.get("title") or ""))
    title_part = f"-{title}" if title else ""
    return f"{brief_id}{title_part}-unit-economics.{extension}"


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    revenue = report["revenue_model"]
    price_band = revenue["target_monthly_price_band_usd"]
    payback = report["payback_bands"]
    rows = [
        _csv_row(
            report,
            section="revenue_assumptions",
            row_id="revenue_packaging",
            label="Packaging",
            value=revenue["packaging"],
        ),
        _csv_row(
            report,
            section="revenue_assumptions",
            row_id="revenue_pricing_basis",
            label="Pricing basis",
            value=revenue["pricing_basis"],
        ),
        _csv_row(
            report,
            section="revenue_assumptions",
            row_id="revenue_buyer_budget_owner",
            label="Buyer budget owner",
            value=revenue["buyer_budget_owner"],
        ),
        _csv_row(
            report,
            section="revenue_assumptions",
            row_id="revenue_initial_customer_segment",
            label="Initial customer segment",
            value=revenue["initial_customer_segment"],
        ),
        _csv_row(
            report,
            section="revenue_assumptions",
            row_id="revenue_target_monthly_price_band_usd",
            label="Target monthly price band",
            metric="monthly_price_usd",
            low_usd=price_band["low"],
            high_usd=price_band["high"],
            value=f"${price_band['low']:,}-${price_band['high']:,}",
        ),
        _csv_row(
            report,
            section="revenue_assumptions",
            row_id="revenue_expected_conversion_rate_band",
            label="Expected conversion rate band",
            metric="conversion_rate",
            value=revenue["expected_conversion_rate_band"],
        ),
        _csv_row(
            report,
            section="revenue_assumptions",
            row_id="revenue_expansion_trigger",
            label="Expansion trigger",
            value=revenue["expansion_trigger"],
        ),
        _csv_row(
            report,
            section="revenue_assumptions",
            row_id="revenue_source_idea_ids",
            label="Source ideas",
            value=_csv_list(revenue["source_idea_ids"]),
            source_idea_ids=_csv_list(revenue["source_idea_ids"]),
        ),
    ]

    for assumption in report["assumptions"]:
        rows.append(
            _csv_row(
                report,
                section="revenue_assumptions",
                row_id=assumption["id"],
                label=assumption["label"],
                value=assumption["value"],
                basis=assumption["basis"],
            )
        )

    for channel in report["acquisition_channels"]:
        rows.append(
            _csv_row(
                report,
                section="acquisition_costs",
                row_id=channel["id"],
                label=channel["channel"],
                motion=channel["motion"],
                note=channel["rationale"],
                basis=_csv_list(channel.get("source_fields", [])),
            )
        )

    for driver in report["cost_drivers"]:
        rows.append(
            _csv_row(
                report,
                section="margin_drivers",
                row_id=driver["id"],
                label=driver["name"],
                direction=driver["direction"],
                note=driver["rationale"],
            )
        )

    for risk_note in report["gross_margin_risk_notes"]:
        rows.append(
            _csv_row(
                report,
                section="margin_drivers",
                row_id=risk_note["id"],
                label="Gross margin risk",
                severity=risk_note["severity"],
                note=risk_note["note"],
                metric=risk_note["watch_metric"],
            )
        )

    rows.extend(
        [
            _csv_row(
                report,
                section="payback_notes",
                row_id="payback_optimistic_months",
                label="Optimistic payback",
                metric="payback_months",
                months=payback["optimistic_months"],
                gross_margin_band=payback["gross_margin_band"],
            ),
            _csv_row(
                report,
                section="payback_notes",
                row_id="payback_expected_months",
                label="Expected payback",
                metric="payback_months",
                months=payback["expected_months"],
                gross_margin_band=payback["gross_margin_band"],
                basis=payback["basis"],
            ),
            _csv_row(
                report,
                section="payback_notes",
                row_id="payback_conservative_months",
                label="Conservative payback",
                metric="payback_months",
                months=payback["conservative_months"],
                gross_margin_band=payback["gross_margin_band"],
            ),
            _csv_row(
                report,
                section="payback_notes",
                row_id="payback_basis",
                label="Payback basis",
                value=payback["basis"],
            ),
        ]
    )

    for case in report["sensitivity_cases"]:
        rows.append(
            _csv_row(
                report,
                section="sensitivity_rows",
                row_id=f"sensitivity_{case['case']}",
                label=case["case"],
                metric="payback_months",
                months=case["payback_months"],
                gross_margin_band=case["gross_margin_band"],
                note=case["assumption_shift"],
            )
        )

    return rows


def _csv_row(report: dict[str, Any], **values: Any) -> dict[str, Any]:
    brief = report["design_brief"]
    row = {column: "" for column in CSV_COLUMNS}
    row.update(
        {
            "schema_version": report["schema_version"],
            "kind": report["kind"],
            "design_brief_id": brief["id"],
            "design_brief_title": brief["title"],
        }
    )
    row.update(values)
    return row


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
    buyer = _first_text(
        design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer"
    )
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


def _revenue_model(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    source_idea_ids = [
        str(idea["id"]) for idea in source_ideas if idea.get("id") and not idea.get("missing")
    ]
    buyer = _first_text(
        design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer"
    )
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
        "target workflow",
    )
    first_customers = _first_text(
        design_brief.get("first_10_customers"),
        _field_values(source_ideas, "first_10_customers"),
        "first 10 design partners",
    )
    scope_count = max(1, len(_string_list(design_brief.get("mvp_scope"))))
    readiness_score = float(design_brief.get("readiness_score") or 0.0)
    if confidence["score"] >= 75:
        low, high = 1200 + scope_count * 250, 3000 + scope_count * 500
        packaging = "paid pilot converting to per-team subscription"
    elif confidence["score"] >= 55:
        low, high = 600 + scope_count * 200, 1800 + scope_count * 400
        packaging = "validation pilot with conservative team subscription"
    else:
        low, high = 250 + scope_count * 100, 900 + scope_count * 250
        packaging = "concierge pilot before recurring pricing"

    return {
        "packaging": packaging,
        "pricing_basis": f"monthly subscription anchored to successful {workflow} outcomes",
        "buyer_budget_owner": buyer,
        "initial_customer_segment": first_customers,
        "target_monthly_price_band_usd": {
            "low": int(low),
            "high": int(high),
        },
        "expected_conversion_rate_band": "25-40%" if readiness_score >= 75 else "10-25%",
        "expansion_trigger": f"repeat usage across more {workflow} teams or higher workflow volume",
        "source_idea_ids": source_idea_ids or _string_list(design_brief.get("source_idea_ids")),
    }


def _acquisition_channels(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence_signal_ids: list[str],
) -> list[dict[str, Any]]:
    buyer = _first_text(
        design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer"
    )
    customer_segment = _first_text(
        design_brief.get("first_10_customers"),
        _field_values(source_ideas, "first_10_customers"),
        "first 10 design partners",
    )
    validation_plan = _first_text(
        design_brief.get("validation_plan"),
        *_field_values(source_ideas, "validation_plan"),
        "direct discovery with buyer-owned teams",
    )
    channels = [
        {
            "id": "channel_design_partner_outreach",
            "channel": "Design partner outreach",
            "motion": "founder-led",
            "rationale": f"Start with {customer_segment} and validate budget ownership with {buyer}.",
            "source_fields": ["first_10_customers", "buyer", "source_ideas"],
        },
        {
            "id": "channel_validation_interviews",
            "channel": "Validation interviews",
            "motion": "consultative",
            "rationale": validation_plan,
            "source_fields": ["validation_plan"],
        },
    ]
    if evidence_signal_ids:
        channels.append(
            {
                "id": "channel_evidence_followups",
                "channel": "Evidence follow-ups",
                "motion": "warm research-led",
                "rationale": "Use linked evidence signals to identify language, objections, and reachable communities.",
                "source_fields": ["evidence_signals"],
            }
        )
    else:
        channels.append(
            {
                "id": "channel_manual_research",
                "channel": "Manual market research",
                "motion": "cold discovery",
                "rationale": "No linked evidence signals exist, so acquisition assumptions require new market proof.",
                "source_fields": ["fallback_missing_evidence"],
            }
        )
    return channels


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
    revenue_model: dict[str, Any],
    cost_drivers: list[dict[str, str]],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    expected = 9 if confidence["score"] >= 75 else 12 if confidence["score"] >= 55 else 15
    if any(driver["direction"] == "high-touch" for driver in cost_drivers):
        expected += 2
    if revenue_model["target_monthly_price_band_usd"]["high"] < 1000:
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


def _gross_margin_risk_notes(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    revenue_model: dict[str, Any],
    cost_drivers: list[dict[str, str]],
    confidence: dict[str, Any],
    evidence_signal_ids: list[str],
) -> list[dict[str, str]]:
    notes = [
        {
            "id": "margin_risk_onboarding",
            "severity": "medium" if confidence["score"] >= 55 else "high",
            "note": "Manual onboarding or bespoke implementation can dilute gross margin.",
            "watch_metric": "implementation hours per activated customer",
        }
    ]
    if any(driver["direction"] == "usage-sensitive" for driver in cost_drivers):
        notes.append(
            {
                "id": "margin_risk_runtime_usage",
                "severity": "medium",
                "note": "Model, integration, or hosted runtime usage may scale with customer activity.",
                "watch_metric": "runtime cost as percent of monthly recurring revenue",
            }
        )
    if revenue_model["target_monthly_price_band_usd"]["low"] < 500:
        notes.append(
            {
                "id": "margin_risk_low_price",
                "severity": "high",
                "note": "Low starting price leaves little room for support-heavy pilots.",
                "watch_metric": "support tickets and success calls per account",
            }
        )
    if not evidence_signal_ids:
        notes.append(
            {
                "id": "margin_risk_missing_evidence",
                "severity": "high",
                "note": "Revenue and usage assumptions are not backed by linked evidence signals.",
                "watch_metric": "validated willingness-to-pay interviews",
            }
        )
    if _string_list(design_brief.get("risks")) or any(
        _string_list(idea.get("domain_risks")) for idea in source_ideas
    ):
        notes.append(
            {
                "id": "margin_risk_domain_constraints",
                "severity": "medium",
                "note": "Domain constraints may add review, compliance, or support burden.",
                "watch_metric": "non-product work required before each paid deployment",
            }
        )
    return notes


def _sensitivity_cases(
    payback_bands: dict[str, Any],
    revenue_model: dict[str, Any],
    cost_drivers: list[dict[str, str]],
    confidence: dict[str, Any],
) -> list[dict[str, Any]]:
    base = int(payback_bands["expected_months"])
    low_price = revenue_model["target_monthly_price_band_usd"]["low"]
    high_price = revenue_model["target_monthly_price_band_usd"]["high"]
    high_touch_penalty = (
        2 if any(driver["direction"] == "high-touch" for driver in cost_drivers) else 0
    )
    return [
        {
            "case": "conservative",
            "payback_months": base + 5 + high_touch_penalty,
            "gross_margin_band": "45-60%" if confidence["score"] < 55 else "55-68%",
            "assumption_shift": (
                f"price lands near ${low_price:,}/month and onboarding remains support-heavy"
            ),
        },
        {
            "case": "base",
            "payback_months": base,
            "gross_margin_band": payback_bands["gross_margin_band"],
            "assumption_shift": "price, conversion, and implementation effort match the current report assumptions",
        },
        {
            "case": "upside",
            "payback_months": max(3, base - 4),
            "gross_margin_band": "75-85%" if confidence["score"] >= 75 else "65-80%",
            "assumption_shift": (
                f"price lands near ${high_price:,}/month and onboarding becomes repeatable"
            ),
        },
    ]


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
            *[risk for idea in source_ideas for risk in _string_list(idea.get("domain_risks"))],
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
    revenue_model: dict[str, Any],
    acquisition_channels: list[dict[str, Any]],
    cost_drivers: list[dict[str, str]],
) -> list[str]:
    buyer = _first_text(design_brief.get("buyer"), "the target buyer")
    value_metric = next(
        (item["value"] for item in assumptions if item["id"] == "assumption_value_metric"),
        "the proposed value metric",
    )
    primary_cost = cost_drivers[0]["name"].lower()
    primary_channel = acquisition_channels[0]["channel"].lower()
    price_band = revenue_model["target_monthly_price_band_usd"]
    return [
        f"What budget line would {buyer} use for {value_metric}?",
        f"Would {buyer} accept a ${price_band['low']:,}-${price_band['high']:,}/month starting price for the first paid pilot?",
        f"Which proof point makes {primary_channel} convert without heavy discounting?",
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
            f"average_evaluation={average_evaluation:.1f}"
            if average_evaluation is not None
            else "average_evaluation=missing",
            f"evidence_signal_count={evidence_signal_count}",
        ],
    }


def _average_evaluation_score(evaluations: list[Any]) -> float | None:
    scores = [float(evaluation.overall_score or 0.0) for evaluation in evaluations]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    return [
        str(idea.get(field) or "") for idea in source_ideas if str(idea.get(field) or "").strip()
    ]


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


def _csv_list(values: Any) -> str:
    return ";".join(_string_list(values))


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")
