"""Deterministic support handoff readiness plans for persisted design briefs."""

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

KIND = "max.design_brief.support_handoff_readiness_plan"
SCHEMA_VERSION = "max.design_brief.support_handoff_readiness_plan.v1"


def build_design_brief_support_handoff_readiness_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    refs = _refs(brief, context)
    gaps = _gaps(context, refs)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "specific_user": context["target_user"],
        },
        "summary": {
            "readiness_posture": "support_discovery_required"
            if gaps
            else "ready_for_support_handoff",
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "support_artifacts": _artifacts(context),
        "training_needs": _training(context),
        "known_issue_intake": _issues(context),
        "ownership_handoffs": _handoffs(context),
        "readiness_summary": {
            "status": "blocked_pending_support_evidence" if gaps else "ready",
            "owner": "Support owner",
            "rationale": f"{len(gaps)} support evidence gap(s) remain.",
        },
        "evidence_references": refs,
        "evidence_gaps": gaps,
        "open_questions": _questions(context, gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_support_handoff_readiness_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _render(report, fmt, "Support Handoff Readiness Plan")


def support_handoff_readiness_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _filename(
        design_brief, "Support Handoff Readiness Plan", "support-handoff-readiness-plan", fmt
    )


def _artifacts(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row(
            "A1", "Support runbook", "Support owner", f"Runbook for {context['workflow_context']}."
        ),
        _row(
            "A2",
            "Customer response snippets",
            "Customer success",
            f"Explain {context['product_concept']} to {context['target_user']}.",
        ),
    ]


def _training(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row("T1", "Workflow training", "Support owner", context["workflow_context"]),
        _row(
            "T2",
            "Known risk training",
            "Product owner",
            join_text(context["risks"], "No known issue evidence captured"),
        ),
    ]


def _issues(context: dict[str, Any]) -> list[dict[str, str]]:
    risks = context["risks"] or ["No known issue intake evidence captured."]
    return [
        _row(f"I{i}", "Known issue intake", "Support owner", risk)
        for i, risk in enumerate(risks, 1)
    ]


def _handoffs(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row(
            "H1",
            "Product to support",
            "Product owner",
            join_text(context["mvp_scope"], "MVP scope"),
        ),
        _row("H2", "Support to customer success", "Customer success", context["target_user"]),
    ]


def _gaps(context: dict[str, Any], refs: list[dict[str, str]]) -> list[dict[str, str]]:
    gaps = []
    if "buyer" in context["fallbacks_used"]:
        gaps.append(
            {"id": "missing_support_owner", "description": "Support owner evidence is missing."}
        )
    if not refs and not context["evidence"]:
        gaps.append(
            {
                "id": "missing_artifact_evidence",
                "description": "Support artifact evidence is missing.",
            }
        )
    if not context["risks"] and not context["evidence"]:
        gaps.append(
            {
                "id": "missing_training_validation",
                "description": "Training validation evidence is missing.",
            }
        )
    return gaps


def _questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "id": "Q1",
            "question": f"What support path should {context['target_user']} use during launch?",
        }
    ] + [{"id": f"QG{i}", "question": gap["description"]} for i, gap in enumerate(gaps, 1)]


def _refs(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs = _brief_refs(brief, ("validation_plan", "risks", "first_milestones"))
    refs.extend(_idea_refs(context, ("evidence_signals", "domain_risks", "workflow_context")))
    return refs


def _row(row_id: str, name: str, owner: str, evidence: str) -> dict[str, str]:
    return {"id": row_id, "name": name, "owner": owner, "evidence": evidence, "action": evidence}


def _blob(context: dict[str, Any]) -> str:
    return " ".join(
        [text(context["source_ideas"]), *context["risks"], *context["evidence"]]
    ).lower()


def _has(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)


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
        "support_artifacts",
        "training_needs",
        "known_issue_intake",
        "ownership_handoffs",
        "evidence_gaps",
    ):
        lines.extend(["", f"## {key.replace('_', ' ').title()}", ""])
        rows = report.get(key) or []
        lines.extend(
            f"- **{row['id']} {row.get('name', row['id'])}**: {row.get('action') or row.get('description')}"
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
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text(value))
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
