"""Deterministic data deletion readiness plans for persisted design briefs."""

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

KIND = "max.design_brief.data_deletion_readiness_plan"
SCHEMA_VERSION = "max.design_brief.data_deletion_readiness_plan.v1"


def build_design_brief_data_deletion_readiness_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    refs = _refs(brief, context)
    categories = _data_categories(context)
    gaps = _gaps(context, refs)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {**design_brief_block(brief, context), "buyer": context["buyer"]},
        "summary": {
            "readiness_posture": "deletion_discovery_required"
            if gaps
            else "ready_for_deletion_review",
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "deletion_triggers": _deletion_triggers(context),
        "data_categories": categories,
        "verification_checks": _verification_checks(context),
        "owner_handoffs": _owner_handoffs(context),
        "readiness_decision": _decision(context, gaps),
        "evidence_references": refs,
        "evidence_gaps": gaps,
        "open_questions": _questions(context, gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_data_deletion_readiness_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _render(report, fmt, "Data Deletion Readiness Plan")


def data_deletion_readiness_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _filename(
        design_brief, "Data Deletion Readiness Plan", "data-deletion-readiness-plan", fmt
    )


def _deletion_triggers(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row(
            "T1",
            "Customer request",
            context["buyer"],
            f"Delete records when {context['target_user']} or sponsor requests removal.",
        ),
        _row(
            "T2",
            "Retention expiry",
            "Data owner",
            "Delete or anonymize records at the approved retention boundary.",
        ),
    ]


def _data_categories(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row("C1", "Customer identity", context["buyer"], context["target_user"]),
        _row("C2", "Workflow content", "Product owner", context["workflow_context"]),
        _row(
            "C3",
            "Validation evidence",
            "Research owner",
            join_text(context["evidence"], "No validation evidence attached"),
        ),
    ]


def _verification_checks(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row(
            "V1",
            "Deletion job evidence",
            "Engineering owner",
            "Deletion run records object counts and failures.",
        ),
        _row(
            "V2",
            "Customer-visible verification",
            context["buyer"],
            f"{context['target_user']} can verify deleted records no longer appear in the workflow.",
        ),
    ]


def _owner_handoffs(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row("H1", "Data owner handoff", context["buyer"], "Own customer-facing deletion policy."),
        _row(
            "H2",
            "Engineering handoff",
            "Engineering owner",
            "Own deletion execution, logs, and retry path.",
        ),
    ]


def _decision(context: dict[str, Any], gaps: list[dict[str, str]]) -> dict[str, str]:
    blob = _blob(context)
    posture = (
        "privacy_review_required"
        if _has(blob, ("privacy", "retention", "deletion", "residency", "compliance"))
        else "standard_review"
    )
    if gaps:
        posture = "blocked_pending_evidence"
    return {
        "status": posture,
        "owner": context["buyer"],
        "rationale": f"{len(gaps)} deletion evidence gap(s) remain.",
    }


def _gaps(context: dict[str, Any], refs: list[dict[str, str]]) -> list[dict[str, str]]:
    gaps = []
    if "mvp_scope" in context["fallbacks_used"]:
        gaps.append(
            {"id": "missing_data_category", "description": "Data category evidence is missing."}
        )
    if "buyer" in context["fallbacks_used"]:
        gaps.append(
            {"id": "missing_deletion_owner", "description": "Deletion owner evidence is missing."}
        )
    if not refs and not context["evidence"]:
        gaps.append(
            {
                "id": "missing_verification_evidence",
                "description": "Deletion verification evidence is missing.",
            }
        )
    return gaps


def _questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"id": "Q1", "question": f"What retention window applies to {context['workflow_context']}?"}
    ] + [{"id": f"QG{i}", "question": gap["description"]} for i, gap in enumerate(gaps, 1)]


def _refs(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs = _brief_refs(
        brief, ("validation_plan", "risks", "synthesis_rationale", "first_milestones")
    )
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
        "deletion_triggers",
        "data_categories",
        "verification_checks",
        "owner_handoffs",
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
