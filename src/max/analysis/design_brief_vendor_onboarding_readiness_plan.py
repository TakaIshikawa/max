"""Deterministic vendor onboarding readiness plans for persisted design briefs."""

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

KIND = "max.design_brief.vendor_onboarding_readiness_plan"
SCHEMA_VERSION = "max.design_brief.vendor_onboarding_readiness_plan.v1"


def build_design_brief_vendor_onboarding_readiness_plan(
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
        "design_brief": {**design_brief_block(brief, context), "buyer": context["buyer"]},
        "summary": {
            "readiness_posture": _decision(context, gaps)["status"],
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "vendor_requirements": _requirements(context),
        "onboarding_steps": _steps(context),
        "dependency_checks": _dependencies(context),
        "owner_handoffs": _handoffs(context),
        "readiness_decision": _decision(context, gaps),
        "evidence_references": refs,
        "evidence_gaps": gaps,
        "open_questions": _questions(context, gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_vendor_onboarding_readiness_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _render(report, fmt, "Vendor Onboarding Readiness Plan")


def vendor_onboarding_readiness_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _filename(
        design_brief, "Vendor Onboarding Readiness Plan", "vendor-onboarding-readiness-plan", fmt
    )


def _requirements(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row("R1", "Vendor owner", context["buyer"], context["buyer"]),
        _row(
            "R2",
            "Integration scope",
            "Engineering owner",
            join_text(context["mvp_scope"], "Vendor integration scope missing"),
        ),
        _row(
            "R3",
            "Compliance review",
            "Procurement owner",
            join_text(context["risks"], "Compliance risk evidence missing"),
        ),
    ]


def _steps(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row(
            "S1",
            "Procurement intake",
            "Procurement owner",
            f"Open vendor intake for {context['product_concept']}.",
        ),
        _row(
            "S2",
            "Technical onboarding",
            "Engineering owner",
            f"Validate integration path for {context['workflow_context']}.",
        ),
        _row(
            "S3",
            "Support handoff",
            "Support owner",
            "Document vendor contacts, escalation, and outage expectations.",
        ),
    ]


def _dependencies(context: dict[str, Any]) -> list[dict[str, str]]:
    signals = context["risks"] or ["No dependency risk evidence captured."]
    return [
        _row(f"D{i}", "Dependency check", "Engineering owner", signal)
        for i, signal in enumerate(signals, 1)
    ]


def _handoffs(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row("H1", "Business owner handoff", context["buyer"], "Own vendor business approval."),
        _row(
            "H2",
            "Support handoff",
            "Support owner",
            "Own vendor support path and escalation contacts.",
        ),
    ]


def _decision(context: dict[str, Any], gaps: list[dict[str, str]]) -> dict[str, str]:
    blob = _blob(context)
    status = (
        "blocked_by_dependency_risk"
        if _has(blob, ("dependency", "integration", "vendor", "procurement")) and gaps
        else "ready_for_vendor_review"
    )
    if gaps and status == "ready_for_vendor_review":
        status = "blocked_pending_vendor_evidence"
    return {
        "status": status,
        "owner": context["buyer"],
        "rationale": f"{len(gaps)} vendor onboarding evidence gap(s) remain.",
    }


def _gaps(context: dict[str, Any], refs: list[dict[str, str]]) -> list[dict[str, str]]:
    gaps = []
    if "buyer" in context["fallbacks_used"]:
        gaps.append(
            {"id": "missing_vendor_owner", "description": "Vendor owner evidence is missing."}
        )
    if not context["risks"] and not context["evidence"]:
        gaps.append(
            {"id": "missing_dependency_evidence", "description": "Dependency evidence is missing."}
        )
    if not refs and not context["evidence"]:
        gaps.append(
            {
                "id": "missing_onboarding_validation",
                "description": "Onboarding validation evidence is missing.",
            }
        )
    return gaps


def _questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "id": "Q1",
            "question": f"Which vendor dependency blocks {context['workflow_context']} launch?",
        }
    ] + [{"id": f"QG{i}", "question": gap["description"]} for i, gap in enumerate(gaps, 1)]


def _refs(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs = _brief_refs(brief, ("validation_plan", "risks", "first_milestones"))
    refs.extend(
        _idea_refs(
            context, ("evidence_signals", "domain_risks", "tech_approach", "workflow_context")
        )
    )
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
        "vendor_requirements",
        "onboarding_steps",
        "dependency_checks",
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
