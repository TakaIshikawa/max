"""Deterministic customer advisory board plans for persisted design briefs."""

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

KIND = "max.design_brief.customer_advisory_board_plan"
SCHEMA_VERSION = "max.design_brief.customer_advisory_board_plan.v1"


def build_design_brief_customer_advisory_board_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    refs = _evidence_references(brief, context)
    gaps = _evidence_gaps(context, refs)
    agenda = _session_agenda(context, gaps)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "specific_user": context["target_user"],
        },
        "summary": {
            "cab_posture": "recruitment_discovery_required" if gaps else "ready_for_cab_review",
            "participant_segment_count": 2,
            "feedback_theme_count": len(_feedback_themes(context)),
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "participant_segments": _participant_segments(context),
        "feedback_themes": _feedback_themes(context),
        "session_agenda": agenda,
        "follow_up_decisions": _follow_up_decisions(context),
        "evidence_references": refs,
        "evidence_gaps": gaps,
        "open_questions": _open_questions(context, gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_customer_advisory_board_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _render(report, fmt, "Customer Advisory Board Plan")


def customer_advisory_board_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _filename(
        design_brief, "Customer Advisory Board Plan", "customer-advisory-board-plan", fmt
    )


def _participant_segments(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "P1",
            "name": context["target_user"],
            "owner": context["buyer"],
            "evidence": context["target_user"],
        },
        {
            "id": "P2",
            "name": "Customer sponsor",
            "owner": "Customer success",
            "evidence": context["buyer"],
        },
    ]


def _feedback_themes(context: dict[str, Any]) -> list[dict[str, str]]:
    themes = [
        ("F1", "Workflow fit", context["workflow_context"]),
        ("F2", "MVP usefulness", join_text(context["mvp_scope"], "MVP scope")),
        ("F3", "Risk and objections", join_text(context["risks"], "No explicit risk evidence")),
    ]
    return [
        {"id": theme_id, "name": name, "owner": "Product owner", "evidence": evidence}
        for theme_id, name, evidence in themes
    ]


def _session_agenda(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "id": "A1",
            "name": "Problem framing",
            "owner": "Research owner",
            "action": context["workflow_context"],
        },
        {
            "id": "A2",
            "name": "Concept walkthrough",
            "owner": "Product owner",
            "action": context["product_concept"],
        },
        {
            "id": "A3",
            "name": "Decision review",
            "owner": context["buyer"],
            "action": f"Resolve {len(gaps)} evidence gap(s).",
        },
    ]


def _follow_up_decisions(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "D1",
            "name": "Proceed decision",
            "owner": context["buyer"],
            "action": "Choose proceed, revise, or stop after CAB feedback.",
        },
        {
            "id": "D2",
            "name": "Scope adjustment",
            "owner": "Product owner",
            "action": join_text(context["mvp_scope"], "Confirm MVP scope."),
        },
    ]


def _evidence_references(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs = _brief_refs(brief, ("validation_plan", "synthesis_rationale", "why_this_now"))
    refs.extend(
        _idea_refs(context, ("specific_user", "buyer", "evidence_signals", "inspiring_insights"))
    )
    return refs


def _evidence_gaps(context: dict[str, Any], refs: list[dict[str, str]]) -> list[dict[str, str]]:
    gaps = []
    if "specific_user" in context["fallbacks_used"]:
        gaps.append(
            {
                "id": "missing_target_user",
                "description": "Target user participant evidence is missing.",
            }
        )
    if not refs:
        gaps.append(
            {"id": "missing_customer_evidence", "description": "Customer evidence is missing."}
        )
    if not context["evidence"]:
        gaps.append(
            {
                "id": "missing_validation_agenda",
                "description": "Validation agenda evidence is missing.",
            }
        )
    return gaps


def _open_questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"id": "Q1", "question": f"Which {context['target_user']} accounts should join the CAB?"}
    ] + [
        {"id": f"QG{idx}", "question": gap["description"]} for idx, gap in enumerate(gaps, start=1)
    ]


def _render(report: dict[str, Any], fmt: str, title: str) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported {title.lower()} format: {fmt}")
    brief = report["design_brief"]
    lines = [
        f"# {title}: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
    ]
    for key in (
        "participant_segments",
        "feedback_themes",
        "session_agenda",
        "follow_up_decisions",
        "evidence_gaps",
    ):
        lines.extend(["", f"## {key.replace('_', ' ').title()}", ""])
        rows = report.get(key) or []
        lines.extend(
            f"- **{row['id']} {row.get('name', row['id'])}**: {row.get('action') or row.get('evidence') or row.get('description')}"
            for row in rows
        ) if rows else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _brief_refs(brief: dict[str, Any], fields: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {
            "id": f"design_brief.{field}",
            "type": field,
            "description": join_text(list_values(brief.get(field)), ""),
        }
        for field in fields
        if list_values(brief.get(field))
    ]


def _idea_refs(context: dict[str, Any], fields: tuple[str, ...]) -> list[dict[str, str]]:
    refs = []
    for idea in context["source_ideas"]:
        if idea.get("missing"):
            continue
        refs.extend(
            {
                "id": f"{idea['id']}.{field}",
                "type": field,
                "description": join_text(list_values(idea.get(field)), ""),
            }
            for field in fields
            if list_values(idea.get(field))
        )
    return refs


def _filename(design_brief: dict[str, Any], default_title: str, suffix: str, fmt: str) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return f"{_part(str(design_brief.get('id') or 'design-brief'))}-{_part(str(design_brief.get('title') or default_title))}-{suffix}.{extension}"


def _part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text(value).strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
