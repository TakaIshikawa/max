"""Deterministic stakeholder approval gate plans for persisted design briefs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from max.analysis._design_brief_plan_common import (
    brief_context,
    design_brief_block,
    join_text,
    list_values,
    source_block,
    text,
)

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.stakeholder_approval_gate_plan"
SCHEMA_VERSION = "max.design_brief.stakeholder_approval_gate_plan.v1"


def build_design_brief_stakeholder_approval_gate_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build approval gates from a persisted design brief."""
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None

    context = brief_context(store, brief)
    evidence_references = _evidence_references(brief, context)
    blockers = _blocker_register(context)
    gaps = _evidence_gaps(context, evidence_references, blockers)
    gates = _approval_gates(context, blockers, gaps)
    decisions = _stakeholder_decisions(context, gates)

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
            "approval_posture": "blocked_pending_evidence" if gaps else "ready_for_gate_review",
            "primary_approver": context["buyer"],
            "decision_criteria": _decision_criteria(context),
            "approval_gate_count": len(gates),
            "blocker_count": len(blockers),
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "approval_gates": gates,
        "stakeholder_decisions": decisions,
        "blocker_register": blockers,
        "evidence_references": evidence_references,
        "evidence_gaps": gaps,
        "open_questions": _open_questions(context, gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_stakeholder_approval_gate_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    """Render a stakeholder approval gate plan as deterministic Markdown or JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported stakeholder approval gate plan format: {fmt}")
    brief = report["design_brief"]
    lines = [
        f"# Stakeholder Approval Gate Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
    ]
    for key, title in (
        ("approval_gates", "Approval Gates"),
        ("stakeholder_decisions", "Stakeholder Decisions"),
        ("blocker_register", "Blocker Register"),
        ("evidence_references", "Evidence References"),
        ("evidence_gaps", "Evidence Gaps"),
        ("open_questions", "Open Questions"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report.get(key) or []
        if not rows:
            lines.append("- None")
            continue
        for row in rows:
            label = row.get("name") or row.get("question") or row.get("description") or row["id"]
            detail = (
                row.get("action")
                or row.get("decision")
                or row.get("description")
                or row.get("evidence", "")
            )
            lines.append(f"- **{row['id']} {label}**: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def stakeholder_approval_gate_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-"
        f"{_filename_part(str(design_brief.get('title') or 'Stakeholder Approval Gate Plan'))}-"
        f"stakeholder-approval-gate-plan.{extension}"
    )


def _approval_gates(
    context: dict[str, Any], blockers: list[dict[str, str]], gaps: list[dict[str, str]]
) -> list[dict[str, str]]:
    criteria = _decision_criteria(context)
    return [
        {
            "id": "G1",
            "name": "Business sponsor approval",
            "owner": context["buyer"],
            "criteria": criteria,
            "action": f"Confirm {context['product_concept']} is worth pursuing for {context['target_user']}.",
            "evidence": join_text(context["evidence"], "approval evidence missing"),
            "status": "needs_evidence"
            if any(gap["id"] == "missing_buyer_or_stakeholder" for gap in gaps)
            else "ready",
        },
        {
            "id": "G2",
            "name": "Decision criteria review",
            "owner": "Product owner",
            "criteria": criteria,
            "action": f"Accept, revise, or reject the MVP scope: {join_text(context['mvp_scope'], 'scope missing')}.",
            "evidence": criteria,
            "status": "needs_evidence"
            if any(gap["id"] == "missing_decision_criteria" for gap in gaps)
            else "ready",
        },
        {
            "id": "G3",
            "name": "Blocker disposition",
            "owner": "Delivery owner",
            "criteria": f"{len(blockers)} blocker(s) reviewed with owners and next actions.",
            "action": "Resolve or explicitly accept blockers before implementation starts.",
            "evidence": blockers[0]["evidence"],
            "status": "blocked" if blockers else "ready",
        },
    ]


def _stakeholder_decisions(
    context: dict[str, Any], gates: list[dict[str, str]]
) -> list[dict[str, str]]:
    return [
        {
            "id": "D1",
            "stakeholder": context["buyer"],
            "decision": f"Approve business priority for {context['workflow_context']}.",
            "gate_id": gates[0]["id"],
            "source_idea_id": context["primary_source_idea_id"],
        },
        {
            "id": "D2",
            "stakeholder": "Product owner",
            "decision": f"Approve decision criteria and MVP scope for {context['target_user']}.",
            "gate_id": gates[1]["id"],
            "source_idea_id": context["primary_source_idea_id"],
        },
    ]


def _blocker_register(context: dict[str, Any]) -> list[dict[str, str]]:
    risks = context["risks"] or ["No explicit blocker evidence captured."]
    return [
        {
            "id": f"B{idx}",
            "name": "Approval blocker" if idx == 1 else f"Approval blocker {idx}",
            "owner": "Delivery owner",
            "severity": "high"
            if _contains(risk, ("security", "privacy", "compliance", "block"))
            else "medium",
            "description": risk,
            "evidence": risk,
            "source_idea_id": context["primary_source_idea_id"],
        }
        for idx, risk in enumerate(risks, start=1)
    ]


def _decision_criteria(context: dict[str, Any]) -> str:
    if context["evidence"]:
        return join_text(context["evidence"], "validation evidence")
    if context["readiness_score"]:
        return f"Readiness score {context['readiness_score']:.1f} and MVP scope review."
    return ""


def _evidence_references(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs = []
    for field in ("validation_plan", "risks", "synthesis_rationale", "why_this_now"):
        values = list_values(brief.get(field))
        if values:
            refs.append(
                {"id": f"design_brief.{field}", "type": field, "description": join_text(values, "")}
            )
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        for field in ("buyer", "specific_user", "evidence_signals", "domain_risks"):
            values = list_values(idea.get(field))
            if values:
                refs.append(
                    {
                        "id": f"{idea['id']}.{field}",
                        "type": field,
                        "description": join_text(values, ""),
                    }
                )
    return refs


def _evidence_gaps(
    context: dict[str, Any], refs: list[dict[str, str]], blockers: list[dict[str, str]]
) -> list[dict[str, str]]:
    gaps = []
    if "buyer" in context["fallbacks_used"] and "specific_user" in context["fallbacks_used"]:
        gaps.append(
            {
                "id": "missing_buyer_or_stakeholder",
                "description": "Buyer or stakeholder approver evidence is missing.",
            }
        )
    if not _decision_criteria(context):
        gaps.append(
            {
                "id": "missing_decision_criteria",
                "description": "Decision criteria evidence is missing.",
            }
        )
    if not context["risks"] and not any("risk" in ref["type"] for ref in refs):
        gaps.append(
            {
                "id": "missing_blocker_evidence",
                "description": "Blocker and risk evidence is missing.",
            }
        )
    if blockers and blockers[0]["evidence"] == "No explicit blocker evidence captured.":
        gaps.append(
            {
                "id": "missing_blocker_register",
                "description": "Blocker register needs source evidence.",
            }
        )
    return gaps


def _open_questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    questions = [
        {
            "id": "Q1",
            "question": f"Who has final approval authority for {context['product_concept']}?",
        },
        {
            "id": "Q2",
            "question": "What evidence threshold turns each gate from pending to approved?",
        },
    ]
    questions.extend(
        {"id": f"QG{idx}", "question": gap["description"]} for idx, gap in enumerate(gaps, start=1)
    )
    return questions


def _contains(value: str, keywords: tuple[str, ...]) -> bool:
    lower = text(value).lower()
    return any(keyword in lower for keyword in keywords)


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
