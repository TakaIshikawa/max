"""Executive memo exports for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from max.analysis.design_brief_evidence_matrix import build_design_brief_evidence_matrix
from max.analysis.design_brief_prd import build_design_brief_prd
from max.analysis.design_brief_risk_register import build_design_brief_risk_register
from max.analysis.design_validation import build_validation_plan
from max.analysis.market_sizing import build_market_sizing_report
from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.executive_memo.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "item_title",
    "priority",
    "severity",
    "owner",
    "recommendation",
    "detail",
    "source_idea_ids",
)


def build_design_brief_executive_memo(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a concise, approval-ready memo from persisted design brief artifacts."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    prd = build_design_brief_prd(store, brief_id)
    evidence_matrix = build_design_brief_evidence_matrix(store, design_brief)
    risk_register = build_design_brief_risk_register(store, brief_id)
    market_sizing = build_market_sizing_report(store, design_brief)
    validation_plan = build_validation_plan(store, design_brief)

    source_idea_ids = _source_idea_ids(design_brief, prd)
    decision = _decision(design_brief, market_sizing, risk_register)
    validation_next_step = _validation_next_step(design_brief, validation_plan, risk_register)
    owner_ask = _owner_ask(decision, validation_next_step)
    top_risks = _top_risks(risk_register)

    return {
        "schema_version": SCHEMA_VERSION,
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
        },
        "decision_summary": decision,
        "target_segment": {
            "buyer": _first_text(design_brief.get("buyer"), "TBD buyer"),
            "specific_user": _first_text(design_brief.get("specific_user"), "TBD user"),
            "workflow_context": _first_text(design_brief.get("workflow_context"), "TBD workflow"),
            "source_idea_ids": source_idea_ids,
        },
        "problem": _problem(design_brief, prd),
        "proposed_product": _proposed_product(design_brief, prd),
        "evidence_highlights": _evidence_highlights(evidence_matrix),
        "market_size_confidence": {
            "level": market_sizing["confidence"]["level"],
            "score": market_sizing["confidence"]["score"],
            "drivers": list(market_sizing["confidence"].get("drivers", [])),
            "primary_segment": market_sizing["segments"][0] if market_sizing["segments"] else None,
            "recommendations": list(market_sizing.get("recommendations", []))[:3],
        },
        "top_risks": top_risks,
        "decisions_needed": _decisions_needed(decision, top_risks, source_idea_ids),
        "milestones": _milestones(design_brief, source_idea_ids),
        "validation_next_step": validation_next_step,
        "next_actions": _next_actions(decision, validation_next_step, owner_ask, source_idea_ids),
        "owner_ask": owner_ask,
        "artifact_refs": {
            "prd_schema_version": prd["schema_version"] if prd else None,
            "evidence_matrix_schema_version": evidence_matrix["schema_version"],
            "risk_register_schema_version": (
                risk_register["schema_version"] if risk_register else None
            ),
            "market_sizing_schema_version": market_sizing["schema_version"],
            "validation_plan_schema_version": validation_plan["schema_version"],
        },
    }


def render_design_brief_executive_memo(memo: dict[str, Any], fmt: str = "json") -> str:
    """Render an executive memo as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(memo, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(memo)
    if fmt != "markdown":
        raise ValueError(f"Unsupported executive memo format: {fmt}")

    brief = memo["design_brief"]
    decision = memo["decision_summary"]
    segment = memo["target_segment"]
    market = memo["market_size_confidence"]
    lines = [
        f"# Executive Memo: {brief['title']}",
        "",
        f"Schema: `{memo['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        "",
        "## Decision Summary",
        "",
        f"- **Recommendation**: {decision['recommendation']}",
        f"- **Decision**: {decision['summary']}",
        f"- **Readiness**: {decision['readiness_score']:.1f}/100",
        f"- **Market confidence**: {market['level']} ({market['score']:.2f})",
        f"- **Owner ask**: {memo['owner_ask']}",
        "",
        "## Target Segment",
        "",
        f"- **Buyer**: {segment['buyer']}",
        f"- **User**: {segment['specific_user']}",
        f"- **Workflow**: {segment['workflow_context']}",
        "",
        "## Problem",
        "",
        memo["problem"],
        "",
        "## Proposed Product",
        "",
        memo["proposed_product"],
        "",
        "## Evidence Highlights",
        "",
    ]
    lines.extend(f"- {highlight['summary']}" for highlight in memo["evidence_highlights"])
    lines.extend(["", "## Risks", ""])
    lines.extend(
        f"- **{risk['severity']} / {risk['likelihood']}**: {risk['title']} - {risk['mitigation']}"
        for risk in memo["top_risks"]
    )
    lines.extend(
        [
            "",
            "## Validation Next Step",
            "",
            memo["validation_next_step"]["action"],
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(memo: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(memo):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(memo: dict[str, Any]) -> list[dict[str, str]]:
    brief = memo.get("design_brief") or {}
    source_idea_ids = brief.get("source_idea_ids") or []
    decision = memo.get("decision_summary") or {}
    rows = [
        _csv_row(
            memo,
            section="summary",
            item_id="recommendation",
            item_title="Recommendation",
            priority=decision.get("recommendation"),
            owner="business owner",
            recommendation=decision.get("recommendation"),
            detail=decision.get("summary"),
            source_idea_ids=source_idea_ids,
        )
    ]
    rows.extend(
        _csv_row(
            memo,
            section="evidence",
            item_id=highlight.get("claim_area"),
            item_title=highlight.get("claim_area"),
            priority=highlight.get("evidence_strength"),
            recommendation=highlight.get("summary"),
            detail={
                "claim": highlight.get("claim"),
                "supporting_signal_ids": highlight.get("supporting_signal_ids") or [],
            },
            source_idea_ids=highlight.get("supporting_source_idea_ids") or [],
        )
        for highlight in memo.get("evidence_highlights", [])
    )
    rows.extend(
        _csv_row(
            memo,
            section="risks",
            item_id=risk.get("id"),
            item_title=risk.get("title"),
            priority=risk.get("priority"),
            severity=risk.get("severity"),
            owner="validation owner",
            recommendation=risk.get("mitigation"),
            detail={
                "description": risk.get("description"),
                "likelihood": risk.get("likelihood"),
                "validation_action": risk.get("validation_action"),
            },
            source_idea_ids=risk.get("source_idea_ids") or [],
        )
        for risk in memo.get("top_risks", [])
    )
    rows.extend(
        _csv_row(
            memo,
            section="decisions_needed",
            item_id=item.get("id"),
            item_title=item.get("title"),
            priority=item.get("priority"),
            owner=item.get("owner"),
            recommendation=item.get("recommendation"),
            detail=item.get("detail"),
            source_idea_ids=item.get("source_idea_ids") or source_idea_ids,
        )
        for item in memo.get("decisions_needed", [])
    )
    rows.extend(
        _csv_row(
            memo,
            section="milestones",
            item_id=item.get("id"),
            item_title=item.get("title"),
            priority=item.get("priority"),
            owner=item.get("owner"),
            recommendation=item.get("recommendation"),
            detail=item.get("detail"),
            source_idea_ids=item.get("source_idea_ids") or source_idea_ids,
        )
        for item in memo.get("milestones", [])
    )
    rows.extend(
        _csv_row(
            memo,
            section="next_actions",
            item_id=item.get("id"),
            item_title=item.get("title"),
            priority=item.get("priority"),
            owner=item.get("owner"),
            recommendation=item.get("recommendation"),
            detail=item.get("detail"),
            source_idea_ids=item.get("source_idea_ids") or source_idea_ids,
        )
        for item in memo.get("next_actions", [])
    )
    return rows


def _csv_row(memo: dict[str, Any], **values: Any) -> dict[str, str]:
    brief = memo.get("design_brief") or {}
    row = {
        "design_brief_id": _csv_cell(brief.get("id")),
        "design_brief_title": _csv_cell(brief.get("title")),
        "section": "",
        "item_id": "",
        "item_title": "",
        "priority": "",
        "severity": "",
        "owner": "",
        "recommendation": "",
        "detail": "",
        "source_idea_ids": _csv_cell(brief.get("source_idea_ids") or []),
    }
    for column in CSV_COLUMNS:
        if column in values:
            row[column] = _csv_cell(values[column])
    return row


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _decision(
    design_brief: dict[str, Any],
    market_sizing: dict[str, Any],
    risk_register: dict[str, Any] | None,
) -> dict[str, Any]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    confidence_level = str(market_sizing["confidence"]["level"])
    high_risks = int((risk_register or {}).get("summary", {}).get("high_risk_count", 0))
    if readiness >= 80.0 and confidence_level in {"medium", "high"} and high_risks <= 2:
        recommendation = "approve-validation"
    elif readiness >= 60.0:
        recommendation = "revise-before-build"
    else:
        recommendation = "hold"

    summary = (
        f"{recommendation}: validate {design_brief['title']} for "
        f"{_first_text(design_brief.get('buyer'), 'the target buyer')} before build commitment."
    )
    return {
        "recommendation": recommendation,
        "summary": summary,
        "readiness_score": readiness,
        "design_status": design_brief.get("design_status", ""),
        "market_confidence": confidence_level,
        "high_risk_count": high_risks,
    }


def _problem(design_brief: dict[str, Any], prd: dict[str, Any] | None) -> str:
    section = (prd or {}).get("sections", {}).get("problem", {})
    return _first_text(
        section.get("content"),
        design_brief.get("why_this_now"),
        design_brief.get("synthesis_rationale"),
        "TBD problem",
    )


def _proposed_product(design_brief: dict[str, Any], prd: dict[str, Any] | None) -> str:
    section = (prd or {}).get("sections", {}).get("proposed_workflow", {})
    return _first_text(
        section.get("content"),
        design_brief.get("merged_product_concept"),
        "TBD product concept",
    )


def _evidence_highlights(evidence_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = sorted(
        evidence_matrix["rows"],
        key=lambda row: (_strength_rank(row["evidence_strength"]), row["claim_area"]),
    )
    highlights = []
    for row in ranked[:4]:
        signal_count = len(row["supporting_signal_ids"])
        source_count = len(row["supporting_source_idea_ids"])
        highlights.append(
            {
                "claim_area": row["claim_area"],
                "evidence_strength": row["evidence_strength"],
                "claim": row["claim"],
                "supporting_signal_ids": row["supporting_signal_ids"],
                "supporting_source_idea_ids": row["supporting_source_idea_ids"],
                "summary": (
                    f"{row['claim_area']}: {row['evidence_strength']} support from "
                    f"{signal_count} signal(s) and {source_count} source idea(s). {row['claim']}"
                ),
            }
        )
    return highlights


def _top_risks(risk_register: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not risk_register:
        return []
    return [
        {
            "id": risk["id"],
            "title": risk["title"],
            "description": risk["description"],
            "category": risk["category"],
            "severity": risk["severity"],
            "likelihood": risk["likelihood"],
            "priority": risk["priority"],
            "mitigation": risk["mitigation"],
            "validation_action": risk["validation_action"],
            "source_idea_ids": risk["source_idea_ids"],
        }
        for risk in risk_register["risks"][:3]
    ]


def _decisions_needed(
    decision: dict[str, Any],
    top_risks: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    decisions = [
        {
            "id": "DEC1",
            "title": "Validation approval",
            "priority": "high",
            "owner": "business owner",
            "recommendation": decision["recommendation"],
            "detail": decision["summary"],
            "source_idea_ids": source_idea_ids,
        }
    ]
    if top_risks:
        decisions.append(
            {
                "id": "DEC2",
                "title": "Risk owner assignment",
                "priority": top_risks[0]["priority"],
                "owner": "validation owner",
                "recommendation": top_risks[0]["mitigation"],
                "detail": f"Assign accountable owner for top risk: {top_risks[0]['title']}.",
                "source_idea_ids": top_risks[0]["source_idea_ids"],
            }
        )
    return decisions


def _milestones(design_brief: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"M{index}",
            "title": milestone,
            "priority": "medium",
            "owner": "product owner",
            "recommendation": "track",
            "detail": f"Complete milestone: {milestone}",
            "source_idea_ids": source_idea_ids,
        }
        for index, milestone in enumerate(
            _string_list(design_brief.get("first_milestones"))[:5],
            start=1,
        )
    ]


def _next_actions(
    decision: dict[str, Any],
    validation_next_step: dict[str, Any],
    owner_ask: str,
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "ACT1",
            "title": "Validation next step",
            "priority": "high",
            "owner": "assigned owner",
            "recommendation": decision["recommendation"],
            "detail": validation_next_step["action"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "ACT2",
            "title": "Owner ask",
            "priority": "high",
            "owner": "business owner",
            "recommendation": "assign-owner",
            "detail": owner_ask,
            "source_idea_ids": source_idea_ids,
        },
    ]


def _validation_next_step(
    design_brief: dict[str, Any],
    validation_plan: dict[str, Any],
    risk_register: dict[str, Any] | None,
) -> dict[str, Any]:
    if risk_register and risk_register.get("risks"):
        top = risk_register["risks"][0]
        return {
            "action": top["validation_action"],
            "rationale": f"De-risks top priority risk: {top['title']}.",
            "source": "risk_register",
        }

    timeline = validation_plan.get("two_week_timeline", [])
    if timeline:
        step = timeline[0]
        return {
            "action": _first_text(
                step.get("activity"),
                step.get("task"),
                design_brief.get("validation_plan"),
            ),
            "rationale": "Starts the persisted validation plan.",
            "source": "validation_plan",
        }

    return {
        "action": _first_text(
            design_brief.get("validation_plan"),
            "Run three target-user discovery interviews.",
        ),
        "rationale": "Confirms whether the brief should move into implementation.",
        "source": "design_brief",
    }


def _owner_ask(decision: dict[str, Any], validation_next_step: dict[str, Any]) -> str:
    return (
        f"Assign an owner to {decision['recommendation']} and complete the validation next step: "
        f"{validation_next_step['action']}"
    )


def _source_idea_ids(design_brief: dict[str, Any], prd: dict[str, Any] | None) -> list[str]:
    ids = list((prd or {}).get("design_brief", {}).get("source_idea_ids") or [])
    if not ids:
        ids = list(design_brief.get("source_idea_ids") or [])
    return [str(item) for item in dict.fromkeys(ids)]


def _strength_rank(value: str) -> int:
    return {"strong": 0, "moderate": 1, "weak": 2}.get(value, 3)


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
