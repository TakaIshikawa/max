"""Deterministic security exception review plans for persisted design briefs."""

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

KIND = "max.design_brief.security_exception_review_plan"
SCHEMA_VERSION = "max.design_brief.security_exception_review_plan.v1"


def build_design_brief_security_exception_review_plan(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    refs = _refs(brief, context)
    exceptions = _exceptions(context)
    gaps = _gaps(context, refs)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {**design_brief_block(brief, context), "buyer": context["buyer"]},
        "summary": {
            "high_risk_exception_count": sum(1 for row in exceptions if row["severity"] == "high"),
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "exception_candidates": exceptions,
        "compensating_controls": _controls(context),
        "approval_requirements": _approvals(context),
        "review_cadence": _cadence(context, gaps),
        "evidence_references": refs,
        "evidence_gaps": gaps,
        "open_questions": _questions(context, gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_security_exception_review_plan(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _render(report, fmt, "Security Exception Review Plan")


def security_exception_review_plan_filename(
    design_brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    return _filename(
        design_brief, "Security Exception Review Plan", "security-exception-review-plan", fmt
    )


def _exceptions(context: dict[str, Any]) -> list[dict[str, str]]:
    signals = (
        context["risks"]
        or context["evidence"]
        or ["No explicit security exception evidence captured."]
    )
    rows = []
    for idx, signal in enumerate(signals, 1):
        high = _has(
            text(signal).lower(),
            ("security", "privacy", "data", "access", "compliance", "exception"),
        )
        rows.append(
            {
                "id": f"E{idx}",
                "name": "Security exception candidate",
                "owner": "Security owner",
                "severity": "high" if high else "medium",
                "evidence": signal,
                "action": f"Review exception need for {signal}",
            }
        )
    return rows


def _controls(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "C1",
            "name": "Access minimization",
            "owner": "Security owner",
            "evidence": context["workflow_context"],
            "action": "Limit access until exception expires.",
        },
        {
            "id": "C2",
            "name": "Audit trail",
            "owner": "Engineering owner",
            "evidence": join_text(context["evidence"], "Audit evidence missing"),
            "action": "Log exception use and review outcomes.",
        },
    ]


def _approvals(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "A1",
            "name": "Security approval",
            "owner": "Security owner",
            "evidence": context["buyer"],
            "action": "Security owner approves exception scope and expiry.",
        },
        {
            "id": "A2",
            "name": "Business acceptance",
            "owner": context["buyer"],
            "evidence": context["product_concept"],
            "action": "Business owner accepts residual risk.",
        },
    ]


def _cadence(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    timing = "weekly until gaps close" if gaps else "monthly until exception expires"
    return [
        {
            "id": "R1",
            "name": "Exception review cadence",
            "owner": "Security owner",
            "timing": timing,
            "evidence": context["primary_source_idea_id"],
            "action": f"Review {context['product_concept']} exception {timing}.",
        }
    ]


def _gaps(context: dict[str, Any], refs: list[dict[str, str]]) -> list[dict[str, str]]:
    gaps = []
    if "buyer" in context["fallbacks_used"]:
        gaps.append(
            {
                "id": "missing_security_owner",
                "description": "Security or business owner evidence is missing.",
            }
        )
    if not refs and not context["evidence"]:
        gaps.append(
            {"id": "missing_control_evidence", "description": "Control evidence is missing."}
        )
    if not _has(_blob(context), ("review", "cadence", "expiry", "expiration", "exception")):
        gaps.append(
            {"id": "missing_review_cadence", "description": "Review cadence evidence is missing."}
        )
    return gaps


def _questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "id": "Q1",
            "question": f"When should the exception for {context['product_concept']} expire?",
        }
    ] + [{"id": f"QG{i}", "question": gap["description"]} for i, gap in enumerate(gaps, 1)]


def _refs(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs = _brief_refs(brief, ("validation_plan", "risks", "synthesis_rationale"))
    refs.extend(_idea_refs(context, ("evidence_signals", "domain_risks", "workflow_context")))
    return refs


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
        "exception_candidates",
        "compensating_controls",
        "approval_requirements",
        "review_cadence",
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
