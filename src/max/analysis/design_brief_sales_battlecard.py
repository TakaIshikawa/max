"""Deterministic sales battlecards for persisted design briefs."""

from __future__ import annotations

import json
import re
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.sales_battlecard.v1"


def build_design_brief_sales_battlecard(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a sales battlecard from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _sales_context(design_brief, source_ideas, lead_idea)
    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_source_risks(source_ideas)]
    )
    objections = _objection_handling(design_brief, context, risks, source_idea_ids)
    demo_beats = _demo_beats(design_brief, context, risks, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.sales_battlecard",
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
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "buyer": context["buyer"],
            "target_user": context["target_user"],
            "workflow_context": context["workflow_context"],
            "value_proposition": context["value_proposition"],
            "primary_pain": context["primary_pain"],
            "primary_outcome": context["primary_outcome"],
            "primary_risk": risks[0] if risks else "No explicit risk captured.",
            "fallbacks_used": context["fallbacks_used"],
            "objection_count": len(objections),
            "demo_beat_count": len(demo_beats),
        },
        "positioning": {
            "one_liner": context["one_liner"],
            "why_now": context["why_now"],
            "qualification_signal": context["workflow_context"],
            "disqualification_signal": context["current_workaround"],
        },
        "objection_handling": objections,
        "demo_beats": demo_beats,
        "proof_points": _proof_points(design_brief, context, source_idea_ids),
        "source_ideas": source_ideas,
    }


def render_design_brief_sales_battlecard(
    battlecard: dict[str, Any], fmt: str = "markdown"
) -> str:
    """Render the sales battlecard as Markdown or JSON."""
    if fmt == "json":
        return json.dumps(battlecard, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported sales battlecard format: {fmt}")

    brief = battlecard["design_brief"]
    summary = battlecard["summary"]
    positioning = battlecard["positioning"]
    lines = [
        f"# Sales Battlecard: {brief['title']}",
        "",
        f"Schema: `{battlecard['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Sales Context",
        "",
        f"- Buyer: {summary['buyer']}",
        f"- Target user: {summary['target_user']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Value proposition: {summary['value_proposition']}",
        f"- Primary pain: {summary['primary_pain']}",
        f"- Primary outcome: {summary['primary_outcome']}",
        f"- Primary risk: {summary['primary_risk']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Positioning",
        "",
        f"- One-liner: {positioning['one_liner']}",
        f"- Why now: {positioning['why_now']}",
        f"- Qualify on: {positioning['qualification_signal']}",
        f"- Disqualify on: {positioning['disqualification_signal']}",
        "",
        "## Objection Handling",
        "",
    ]

    for objection in battlecard["objection_handling"]:
        lines.extend(
            [
                f"### {objection['objection']}",
                "",
                f"- Response: {objection['response']}",
                f"- Proof point: {objection['proof_point']}",
                f"- Discovery follow-up: {objection['discovery_follow_up']}",
                "",
            ]
        )

    lines.extend(["## Demo Beats", ""])
    for beat in battlecard["demo_beats"]:
        lines.extend(
            [
                f"### {beat['name']}",
                "",
                f"- Setup: {beat['setup']}",
                f"- Show: {beat['show']}",
                f"- Outcome: {beat['outcome']}",
                f"- Ask: {beat['ask']}",
                "",
            ]
        )

    lines.extend(["## Proof Points", ""])
    for proof in battlecard["proof_points"]:
        lines.append(f"- **{proof['claim']}**: {proof['evidence']}")

    return "\n".join(lines).rstrip() + "\n"


def _sales_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("economic buyer", "explicit_fallback"),
    )
    target_user = _first_with_label(
        fallbacks,
        "target_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} workflow", "explicit_fallback"),
    )
    value = _first_with_label(
        fallbacks,
        "value_proposition",
        (design_brief.get("value_proposition"), "design_brief.value_proposition"),
        (lead_idea and lead_idea.get("value_proposition"), "lead_idea.value_proposition"),
        (_field_values(source_ideas, "value_proposition"), "source_ideas.value_proposition"),
        (design_brief.get("merged_product_concept"), "design_brief.merged_product_concept"),
        (f"Improve {workflow}", "explicit_fallback"),
    )
    current_workaround = _first_with_label(
        fallbacks,
        "current_workaround",
        (design_brief.get("current_workaround"), "design_brief.current_workaround"),
        (lead_idea and lead_idea.get("current_workaround"), "lead_idea.current_workaround"),
        (_field_values(source_ideas, "current_workaround"), "source_ideas.current_workaround"),
        ("manual process or fragmented tooling", "explicit_fallback"),
    )
    problem = _first_text(
        design_brief.get("problem"),
        lead_idea and lead_idea.get("problem"),
        *_field_values(source_ideas, "problem"),
        design_brief.get("why_this_now"),
    )
    solution = _first_text(
        design_brief.get("solution"),
        lead_idea and lead_idea.get("solution"),
        *_field_values(source_ideas, "solution"),
        design_brief.get("merged_product_concept"),
    )
    one_liner = _first_text(
        design_brief.get("one_liner"),
        lead_idea and lead_idea.get("one_liner"),
        *_field_values(source_ideas, "one_liner"),
        design_brief.get("merged_product_concept"),
        f"{title} helps {target_user} improve {workflow}.",
    )
    why_now = _first_text(
        design_brief.get("why_this_now"),
        lead_idea and lead_idea.get("why_now"),
        *_field_values(source_ideas, "why_now"),
        "The workflow is ready for a focused pilot conversation.",
    )
    return {
        "buyer": buyer,
        "target_user": target_user,
        "workflow_context": workflow,
        "value_proposition": value,
        "current_workaround": current_workaround,
        "primary_pain": problem or f"{target_user} lacks a reliable way to handle {workflow}.",
        "primary_outcome": solution or value,
        "one_liner": one_liner,
        "why_now": why_now,
        "fallbacks_used": fallbacks,
    }


def _objection_handling(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    risks: list[str],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    primary_risk = risks[0] if risks else "The team may need more proof before rollout."
    objections = [
        {
            "id": "status_quo",
            "objection": "We can keep using the current workaround.",
            "response": (
                f"Anchor on the cost of {context['current_workaround']} inside "
                f"{context['workflow_context']} and confirm what breaks at higher volume."
            ),
            "proof_point": context["value_proposition"],
            "discovery_follow_up": "What happens when this workflow doubles in volume?",
            "source_idea_ids": source_ids,
        },
        {
            "id": "priority",
            "objection": "This is not a priority right now.",
            "response": (
                f"Tie the decision to why now: {context['why_now']} Then ask what milestone "
                "would make the pain urgent."
            ),
            "proof_point": context["primary_outcome"],
            "discovery_follow_up": "Which initiative owns this workflow today?",
            "source_idea_ids": source_ids,
        },
        {
            "id": "risk_or_trust",
            "objection": primary_risk,
            "response": (
                "Treat the risk as a pilot design input, define a narrow success criterion, "
                "and agree on the stop condition before expansion."
            ),
            "proof_point": _first_text(design_brief.get("validation_plan"))
            or "Use validation evidence before asking for rollout.",
            "discovery_follow_up": "What proof would make this safe enough for a pilot?",
            "source_idea_ids": source_ids,
        },
    ]
    return objections


def _demo_beats(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    risks: list[str],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    scope = _string_list(design_brief.get("mvp_scope"))
    milestone = _string_list(design_brief.get("first_milestones"))
    return [
        {
            "id": "DB1",
            "name": "Frame the current workflow",
            "setup": f"Start with {context['target_user']} working through {context['workflow_context']}.",
            "show": f"Contrast the product path against {context['current_workaround']}.",
            "outcome": f"The buyer sees where {context['value_proposition']} changes the workflow.",
            "ask": "Does this match the real handoff you need to improve?",
            "source_idea_ids": source_ids,
        },
        {
            "id": "DB2",
            "name": "Show the first valuable action",
            "setup": f"Use the MVP slice: {scope[0] if scope else context['primary_outcome']}.",
            "show": f"Walk through {milestone[0] if milestone else context['primary_outcome']}.",
            "outcome": "The prospect can describe the concrete before-and-after.",
            "ask": "Who would need to see this result before approving a pilot?",
            "source_idea_ids": source_ids,
        },
        {
            "id": "DB3",
            "name": "Close on proof and risk",
            "setup": f"Name the top risk: {risks[0] if risks else 'pilot proof is still needed'}.",
            "show": _first_text(design_brief.get("validation_plan"))
            or "Show the validation plan and the first decision checkpoint.",
            "outcome": "The buyer knows what evidence the pilot will produce.",
            "ask": "What proof would let you move from evaluation to rollout?",
            "source_idea_ids": source_ids,
        },
    ]


def _proof_points(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    validation = _first_text(design_brief.get("validation_plan"))
    return [
        {
            "claim": "Business value",
            "evidence": context["value_proposition"],
            "source_idea_ids": source_ids,
        },
        {
            "claim": "Urgency",
            "evidence": context["why_now"],
            "source_idea_ids": source_ids,
        },
        {
            "claim": "Pilot proof",
            "evidence": validation or "Validation plan should confirm pilot success criteria.",
            "source_idea_ids": source_ids,
        },
    ]


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
                sources.append({"idea_id": idea_id, "role": "supporting", "rank": rank})

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


def _first_with_label(fallbacks: list[str], field: str, *candidates: tuple[Any, str]) -> str:
    for value, label in candidates:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    return [str(idea.get(field) or "") for idea in source_ideas if not idea.get("missing")]


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        if not idea.get("missing"):
            risks.extend(_string_list(idea.get("domain_risks")))
    return risks


def _first_text(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = _compact(value)
        key = re.sub(r"\s+", " ", text.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
