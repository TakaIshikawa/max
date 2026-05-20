"""Deterministic revenue-at-risk plans for persisted design briefs."""

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

KIND = "max.design_brief.revenue_at_risk_plan"
SCHEMA_VERSION = "max.design_brief.revenue_at_risk_plan.v1"


def build_design_brief_revenue_at_risk_plan(store: Store, brief_id: str) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    context = brief_context(store, brief)
    refs = _refs(brief, context)
    gaps = _gaps(context, refs)
    posture = _posture(context, gaps)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source_block(brief),
        "design_brief": {
            **design_brief_block(brief, context),
            "buyer": context["buyer"],
            "specific_user": context["target_user"],
        },
        "summary": {
            "revenue_posture": posture["status"],
            "evidence_gap_count": len(gaps),
            "fallbacks_used": context["fallbacks_used"],
        },
        "risk_drivers": _drivers(context),
        "affected_segments": _segments(context),
        "mitigation_actions": _mitigations(context),
        "owner_assignments": _owners(context),
        "revenue_posture": posture,
        "evidence_references": refs,
        "evidence_gaps": gaps,
        "open_questions": _questions(context, gaps),
        "source_ideas": context["source_ideas"],
    }


def render_design_brief_revenue_at_risk_plan(report: dict[str, Any], fmt: str = "markdown") -> str:
    return _render(report, fmt, "Revenue At Risk Plan")


def revenue_at_risk_plan_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    return _filename(design_brief, "Revenue At Risk Plan", "revenue-at-risk-plan", fmt)


def _drivers(context: dict[str, Any]) -> list[dict[str, str]]:
    signals = context["risks"] or context["evidence"] or ["No revenue risk evidence captured."]
    return [
        _row(f"R{i}", "Revenue risk driver", context["buyer"], signal)
        for i, signal in enumerate(signals, 1)
    ]


def _segments(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row(
            "S1",
            context["target_user"],
            context["buyer"],
            f"Customer segment operating in {context['workflow_context']}.",
        ),
        _row("S2", "Commercial sponsor", "Sales owner", context["buyer"]),
    ]


def _mitigations(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row(
            "M1",
            "Customer mitigation",
            "Customer success",
            f"Protect {context['target_user']} workflow continuity.",
        ),
        _row(
            "M2",
            "Commercial mitigation",
            context["buyer"],
            f"Review pricing, renewal, and expansion impact for {context['product_concept']}.",
        ),
    ]


def _owners(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _row("O1", "Business owner", context["buyer"], "Own revenue posture decision."),
        _row(
            "O2",
            "Customer owner",
            "Customer success",
            "Own account outreach and mitigation tracking.",
        ),
    ]


def _posture(context: dict[str, Any], gaps: list[dict[str, str]]) -> dict[str, str]:
    blob = _blob(context)
    status = (
        "revenue_at_risk"
        if _has(
            blob, ("churn", "renewal", "pricing", "expansion", "customer-impact", "customer impact")
        )
        else "monitor_revenue_risk"
    )
    if gaps:
        status = "blocked_pending_revenue_evidence"
    return {
        "status": status,
        "owner": context["buyer"],
        "rationale": f"{len(gaps)} revenue evidence gap(s) remain.",
    }


def _gaps(context: dict[str, Any], refs: list[dict[str, str]]) -> list[dict[str, str]]:
    gaps = []
    if "buyer" in context["fallbacks_used"]:
        gaps.append({"id": "missing_buyer", "description": "Buyer evidence is missing."})
    if "specific_user" in context["fallbacks_used"]:
        gaps.append(
            {
                "id": "missing_customer_segment",
                "description": "Customer segment evidence is missing.",
            }
        )
    if not refs and not context["evidence"]:
        gaps.append(
            {"id": "missing_mitigation_evidence", "description": "Mitigation evidence is missing."}
        )
    return gaps


def _questions(context: dict[str, Any], gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "id": "Q1",
            "question": f"Which accounts have renewal or expansion risk tied to {context['product_concept']}?",
        }
    ] + [{"id": f"QG{i}", "question": gap["description"]} for i, gap in enumerate(gaps, 1)]


def _refs(brief: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    refs = _brief_refs(brief, ("validation_plan", "risks", "synthesis_rationale"))
    refs.extend(_idea_refs(context, ("evidence_signals", "domain_risks", "buyer", "specific_user")))
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
        "risk_drivers",
        "affected_segments",
        "mitigation_actions",
        "owner_assignments",
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
