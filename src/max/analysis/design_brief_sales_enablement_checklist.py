"""Deterministic sales enablement checklists for persisted design briefs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.sales_enablement_checklist"
SCHEMA_VERSION = "max.design_brief.sales_enablement_checklist.v1"

SECTION_CONFIGS: tuple[dict[str, Any], ...] = (
    {
        "id": "qualification",
        "title": "Qualification",
        "owner_role": "Account executive",
        "source_fields": ["buyer", "specific_user", "workflow_context", "first_10_customers"],
    },
    {
        "id": "discovery",
        "title": "Discovery",
        "owner_role": "Sales engineer",
        "source_fields": ["problem", "current_workaround", "workflow_context", "why_this_now"],
    },
    {
        "id": "proof",
        "title": "Proof",
        "owner_role": "Product marketing",
        "source_fields": ["value_proposition", "validation_plan", "evidence_signals"],
    },
    {
        "id": "demo_readiness",
        "title": "Demo Readiness",
        "owner_role": "Sales engineer",
        "source_fields": ["mvp_scope", "first_milestones", "solution", "suggested_stack"],
    },
    {
        "id": "objection_handling",
        "title": "Objection Handling",
        "owner_role": "Account executive",
        "source_fields": ["risks", "domain_risks", "current_workaround", "validation_plan"],
    },
    {
        "id": "handoff",
        "title": "Handoff",
        "owner_role": "Customer success owner",
        "source_fields": ["buyer", "specific_user", "validation_plan", "first_milestones"],
    },
)

REQUIRED_EVIDENCE: tuple[dict[str, str], ...] = (
    {
        "field": "buyer",
        "label": "Economic buyer",
        "action": "Confirm the economic buyer, budget owner, and signing path before qualification.",
    },
    {
        "field": "target_buyer",
        "label": "Target buyer and user",
        "action": "Add buyer and target-user evidence from the lead idea or discovery notes.",
    },
    {
        "field": "qualification_signals",
        "label": "Qualification signals",
        "action": "Capture fit signals that distinguish qualified prospects from low-fit accounts.",
    },
    {
        "field": "discovery_questions",
        "label": "Discovery questions",
        "action": "Add discovery prompts tied to the workflow, current workaround, and buyer pain.",
    },
    {
        "field": "proof_points",
        "label": "Proof points",
        "action": "Attach validation, evidence signals, or customer-segment proof before seller use.",
    },
    {
        "field": "demo_prep",
        "label": "Demo preparation",
        "action": "Define the demo scope, milestone path, and success proof for the first call.",
    },
    {
        "field": "handoff_criteria",
        "label": "Handoff criteria",
        "action": "Name the handoff criteria for customer success, implementation, or product follow-up.",
    },
)


def build_design_brief_sales_enablement_checklist(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a seller preparation checklist from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    context = _sales_enablement_context(design_brief, source_ideas, lead_idea)
    qualification_signals = _qualification_signals(context, source_ideas, source_idea_ids)
    discovery_questions = _discovery_questions(context, source_idea_ids)
    proof_points = _proof_points(design_brief, context, source_ideas, source_idea_ids)
    demo_prep = _demo_prep(design_brief, context, source_idea_ids)
    objection_assets = _objection_assets(design_brief, context, source_idea_ids)
    handoff_criteria = _handoff_criteria(context, source_idea_ids)
    missing_actions = _missing_evidence_actions(
        context,
        qualification_signals,
        discovery_questions,
        proof_points,
        demo_prep,
        handoff_criteria,
    )
    sections = _sections(
        context,
        qualification_signals,
        discovery_questions,
        proof_points,
        demo_prep,
        objection_assets,
        handoff_criteria,
        missing_actions,
    )
    checklist_items = _flatten_items(sections)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
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
        "summary": {
            "target_buyer": context["buyer"],
            "target_user": context["target_user"],
            "workflow_context": context["workflow_context"],
            "primary_value": context["value_proposition"],
            "sales_readiness_gate": _sales_readiness_gate(design_brief, missing_actions),
            "section_count": len(sections),
            "checklist_item_count": len(checklist_items),
            "missing_evidence_count": len(missing_actions),
            "fallbacks_used": context["fallbacks_used"],
        },
        "sales_context": context,
        "qualification_signals": qualification_signals,
        "discovery_questions": discovery_questions,
        "proof_points": proof_points,
        "demo_prep": demo_prep,
        "objection_handling_assets": objection_assets,
        "handoff_criteria": handoff_criteria,
        "sections": sections,
        "checklist_items": checklist_items,
        "missing_evidence_actions": missing_actions,
        "source_ideas": source_ideas,
    }


def render_design_brief_sales_enablement_checklist(
    checklist: dict[str, Any], fmt: str = "markdown"
) -> str:
    """Render the sales enablement checklist as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(checklist, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported sales enablement checklist format: {fmt}")

    brief = checklist["design_brief"]
    summary = checklist["summary"]
    lines = [
        f"# Sales Enablement Checklist: {brief['title']}",
        "",
        f"Schema: `{checklist['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {_inline_ids(brief.get('source_idea_ids') or [])}",
        "",
        "## Sales Context",
        "",
        f"- Target buyer: {summary['target_buyer']}",
        f"- Target user: {summary['target_user']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Primary value: {summary['primary_value']}",
        f"- Sales readiness gate: {summary['sales_readiness_gate']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
    ]

    for section in checklist["sections"]:
        lines.extend(
            [
                f"## {section['title']}",
                "",
                f"- Owner role: {section['owner_role']}",
                f"- Source fields: {', '.join(section['source_fields'])}",
                "",
            ]
        )
        for item in section["items"]:
            lines.extend(
                [
                    f"### {item['id']}: {item['task']}",
                    "",
                    f"- Owner role: {item['owner_role']}",
                    f"- Rationale: {item['rationale']}",
                    f"- Completion evidence: {item['completion_evidence']}",
                    f"- Source references: {_inline_ids(item['source_reference_ids'])}",
                    f"- Status: {item['status']}",
                    "",
                ]
            )

    lines.extend(["## Missing Evidence Actions", ""])
    if checklist["missing_evidence_actions"]:
        for action in checklist["missing_evidence_actions"]:
            lines.append(f"- **{action['field']}** ({action['owner_role']}): {action['action']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def sales_enablement_checklist_filename(
    design_brief: dict[str, Any], *, fmt: str = "markdown"
) -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief['title']))}-sales-enablement-checklist.{extension}"
    )


def _sales_enablement_context(
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
        (_field_values(source_ideas, "target_users"), "source_ideas.target_users"),
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
        f"{target_user} needs a better way to manage {workflow}.",
    )
    solution = _first_text(
        design_brief.get("solution"),
        lead_idea and lead_idea.get("solution"),
        *_field_values(source_ideas, "solution"),
        design_brief.get("merged_product_concept"),
        value,
    )
    why_now = _first_text(
        design_brief.get("why_this_now"),
        lead_idea and lead_idea.get("why_now"),
        *_field_values(source_ideas, "why_now"),
        "The account is ready for a focused qualification and proof conversation.",
    )
    risks = _dedupe(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
    )
    validation = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        *_field_values(source_ideas, "validation_plan"),
    )
    first_customers = _first_text(
        design_brief.get("first_10_customers"),
        lead_idea and lead_idea.get("first_10_customers"),
        *_field_values(source_ideas, "first_10_customers"),
    )
    return {
        "buyer": buyer,
        "target_user": target_user,
        "workflow_context": workflow,
        "value_proposition": value,
        "current_workaround": current_workaround,
        "problem": problem,
        "solution": solution,
        "why_now": why_now,
        "risks": risks,
        "validation_plan": validation,
        "first_customers": first_customers,
        "fallbacks_used": fallbacks,
    }


def _qualification_signals(
    context: dict[str, Any], source_ideas: list[dict[str, Any]], source_ids: list[str]
) -> list[dict[str, Any]]:
    segment = context["first_customers"] or f"teams managing {context['workflow_context']}"
    evidence = _source_evidence_ids(source_ideas)
    return [
        {
            "id": "QS1",
            "signal": f"Prospect owns {context['workflow_context']}.",
            "qualification_prompt": "Where does this workflow break today, and who owns fixing it?",
            "positive_evidence": context["problem"],
            "disqualification_signal": f"No active ownership of {context['workflow_context']}.",
            "source_reference_ids": source_ids,
        },
        {
            "id": "QS2",
            "signal": f"{context['buyer']} can sponsor a pilot or buying conversation.",
            "qualification_prompt": "Who controls budget, success criteria, and approval for this workflow?",
            "positive_evidence": segment,
            "disqualification_signal": "No buyer, sponsor, or approval path is available.",
            "source_reference_ids": source_ids,
        },
        {
            "id": "QS3",
            "signal": f"Account can supply proof for {context['value_proposition']}.",
            "qualification_prompt": "What metric would prove this is worth rolling out?",
            "positive_evidence": ", ".join(evidence) if evidence else context["validation_plan"],
            "disqualification_signal": "No measurable success criterion or evidence source is available.",
            "source_reference_ids": evidence or source_ids,
        },
    ]


def _discovery_questions(context: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "DQ1",
            "question": f"How does {context['target_user']} handle {context['workflow_context']} today?",
            "listen_for": context["current_workaround"],
            "follow_up": "Which step creates the most delay, rework, or risk?",
            "source_reference_ids": source_ids,
        },
        {
            "id": "DQ2",
            "question": f"Why is solving this now important for {context['buyer']}?",
            "listen_for": context["why_now"],
            "follow_up": "What deadline, metric, or initiative makes this urgent?",
            "source_reference_ids": source_ids,
        },
        {
            "id": "DQ3",
            "question": f"What would make {context['value_proposition']} credible enough for a pilot?",
            "listen_for": context["validation_plan"] or "named pilot success criteria",
            "follow_up": "Who needs to approve the proof plan before handoff?",
            "source_reference_ids": source_ids,
        },
    ]


def _proof_points(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    evidence = _source_evidence_ids(source_ideas)
    return [
        {
            "id": "PP1",
            "claim": "Buyer value",
            "evidence": context["value_proposition"],
            "seller_use": "Use this as the value anchor in qualification and recap notes.",
            "source_reference_ids": source_ids,
        },
        {
            "id": "PP2",
            "claim": "Urgency",
            "evidence": context["why_now"],
            "seller_use": "Use this to connect the conversation to an active business moment.",
            "source_reference_ids": source_ids,
        },
        {
            "id": "PP3",
            "claim": "Pilot proof",
            "evidence": context["validation_plan"]
            or _first_text(design_brief.get("synthesis_rationale"))
            or "Pilot proof still needs validation evidence.",
            "seller_use": "Use this to define the proof threshold before implementation handoff.",
            "source_reference_ids": evidence or source_ids,
        },
    ]


def _demo_prep(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))
    return [
        {
            "id": "DP1",
            "step": "Frame the workflow and current workaround.",
            "prep": f"Prepare a before-state using {context['current_workaround']}.",
            "demo_asset": f"Opening narrative for {context['workflow_context']}.",
            "success_check": "Prospect confirms the workflow and pain are accurate.",
            "source_reference_ids": source_ids,
        },
        {
            "id": "DP2",
            "step": "Show the first valuable product path.",
            "prep": scope[0] if scope else context["solution"],
            "demo_asset": milestones[0] if milestones else context["solution"],
            "success_check": "Prospect can name the before-and-after improvement.",
            "source_reference_ids": source_ids,
        },
        {
            "id": "DP3",
            "step": "Close the demo on proof and handoff.",
            "prep": context["validation_plan"] or "Define pilot success criteria before demo.",
            "demo_asset": "Proof plan, next-step owner, and handoff checklist.",
            "success_check": "Prospect agrees on success criteria and next owner.",
            "source_reference_ids": source_ids,
        },
    ]


def _objection_assets(
    design_brief: dict[str, Any], context: dict[str, Any], source_ids: list[str]
) -> list[dict[str, Any]]:
    primary_risk = context["risks"][0] if context["risks"] else "Pilot proof is not yet established."
    return [
        {
            "id": "OA1",
            "objection": "We can keep using the current workaround.",
            "response_asset": (
                f"Compare the cost of {context['current_workaround']} against "
                f"{context['value_proposition']}."
            ),
            "proof_asset": context["problem"],
            "source_reference_ids": source_ids,
        },
        {
            "id": "OA2",
            "objection": "This is not urgent.",
            "response_asset": f"Anchor urgency to: {context['why_now']}",
            "proof_asset": context["validation_plan"] or context["solution"],
            "source_reference_ids": source_ids,
        },
        {
            "id": "OA3",
            "objection": primary_risk,
            "response_asset": "Convert the concern into a narrow pilot proof requirement.",
            "proof_asset": _first_text(design_brief.get("validation_plan"))
            or "Define the validation evidence before advancing the opportunity.",
            "source_reference_ids": source_ids,
        },
    ]


def _handoff_criteria(context: dict[str, Any], source_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "HC1",
            "criterion": f"{context['buyer']} confirms budget authority or sponsor path.",
            "owner_role": "Account executive",
            "handoff_evidence": "Buyer, budget owner, and decision process captured in opportunity notes.",
            "source_reference_ids": source_ids,
        },
        {
            "id": "HC2",
            "criterion": f"{context['target_user']} validates the workflow and demo relevance.",
            "owner_role": "Sales engineer",
            "handoff_evidence": "Discovery recap includes workflow pain, current workaround, and demo feedback.",
            "source_reference_ids": source_ids,
        },
        {
            "id": "HC3",
            "criterion": "Pilot success criteria and next owner are explicit.",
            "owner_role": "Customer success owner",
            "handoff_evidence": context["validation_plan"] or "Named success metric, next owner, and date.",
            "source_reference_ids": source_ids,
        },
    ]


def _sections(
    context: dict[str, Any],
    qualification_signals: list[dict[str, Any]],
    discovery_questions: list[dict[str, Any]],
    proof_points: list[dict[str, Any]],
    demo_prep: list[dict[str, Any]],
    objection_assets: list[dict[str, Any]],
    handoff_criteria: list[dict[str, Any]],
    missing_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    section_payloads = {
        "qualification": [
            _item(
                task="Confirm the prospect matches target buyer and workflow fit.",
                owner_role="Account executive",
                rationale=qualification_signals[0]["signal"],
                completion_evidence="Qualified account notes include buyer, user, workflow, and disqualification signal.",
                source_reference_ids=qualification_signals[0]["source_reference_ids"],
            ),
            _item(
                task="Validate budget sponsor, decision path, and proof metric.",
                owner_role="Account executive",
                rationale=qualification_signals[1]["signal"],
                completion_evidence="Opportunity record names sponsor, approval path, and success metric.",
                source_reference_ids=qualification_signals[1]["source_reference_ids"],
            ),
        ],
        "discovery": [
            _item(
                task="Ask workflow and current-workaround discovery questions.",
                owner_role="Sales engineer",
                rationale=discovery_questions[0]["listen_for"],
                completion_evidence="Discovery notes capture workflow steps, pain, workaround, and follow-up owner.",
                source_reference_ids=discovery_questions[0]["source_reference_ids"],
            ),
            _item(
                task="Capture why-now pressure and buyer priority.",
                owner_role="Account executive",
                rationale=context["why_now"],
                completion_evidence="Recap includes urgency trigger, initiative owner, and decision deadline.",
                source_reference_ids=discovery_questions[1]["source_reference_ids"],
            ),
        ],
        "proof": [
            _item(
                task="Attach value, urgency, and pilot proof points to seller notes.",
                owner_role="Product marketing",
                rationale=proof_points[0]["evidence"],
                completion_evidence="Seller notes include approved claims and supporting evidence references.",
                source_reference_ids=proof_points[0]["source_reference_ids"],
            ),
            _item(
                task="Define the proof threshold required to advance the opportunity.",
                owner_role="Sales engineer",
                rationale=proof_points[2]["evidence"],
                completion_evidence="Pilot proof threshold is documented with metric, owner, and acceptance date.",
                source_reference_ids=proof_points[2]["source_reference_ids"],
            ),
        ],
        "demo_readiness": [
            _item(
                task="Prepare the workflow demo path and first valuable action.",
                owner_role="Sales engineer",
                rationale=demo_prep[1]["prep"],
                completion_evidence="Demo script includes before-state, product path, and buyer-facing outcome.",
                source_reference_ids=demo_prep[1]["source_reference_ids"],
            ),
            _item(
                task="Prepare demo close, proof plan, and next-step owner.",
                owner_role="Sales engineer",
                rationale=demo_prep[2]["prep"],
                completion_evidence="Demo close includes success criteria, proof asset, and handoff owner.",
                source_reference_ids=demo_prep[2]["source_reference_ids"],
            ),
        ],
        "objection_handling": [
            _item(
                task="Prepare current-workaround and urgency objection responses.",
                owner_role="Account executive",
                rationale=objection_assets[0]["response_asset"],
                completion_evidence="Seller prep includes response assets for status quo and urgency objections.",
                source_reference_ids=objection_assets[0]["source_reference_ids"],
            ),
            _item(
                task="Prepare risk objection response and proof asset.",
                owner_role="Sales engineer",
                rationale=objection_assets[2]["response_asset"],
                completion_evidence="Risk objection has proof asset, mitigation owner, and pilot stop condition.",
                source_reference_ids=objection_assets[2]["source_reference_ids"],
            ),
        ],
        "handoff": [
            _item(
                task="Confirm handoff criteria before customer success or implementation transfer.",
                owner_role="Customer success owner",
                rationale=handoff_criteria[2]["criterion"],
                completion_evidence="Handoff record includes buyer, user, workflow, success criteria, and next owner.",
                source_reference_ids=handoff_criteria[2]["source_reference_ids"],
            ),
            _item(
                task="Resolve or explicitly accept missing evidence before handoff.",
                owner_role="Product lead",
                rationale=_missing_summary(missing_actions),
                completion_evidence="Missing evidence actions are resolved, accepted, or assigned with dates.",
                source_reference_ids=[],
            ),
        ],
    }

    sections: list[dict[str, Any]] = []
    item_number = 1
    for config in SECTION_CONFIGS:
        items = []
        for item in section_payloads[config["id"]]:
            items.append({"id": f"DBSE{item_number}", "status": "pending", **item})
            item_number += 1
        sections.append({**config, "items": items})
    return sections


def _item(
    *,
    task: str,
    owner_role: str,
    rationale: str,
    completion_evidence: str,
    source_reference_ids: list[str],
) -> dict[str, Any]:
    return {
        "task": task,
        "owner_role": owner_role,
        "rationale": _compact(rationale),
        "completion_evidence": completion_evidence,
        "source_reference_ids": list(dict.fromkeys(source_reference_ids)),
    }


def _missing_evidence_actions(
    context: dict[str, Any],
    qualification_signals: list[dict[str, Any]],
    discovery_questions: list[dict[str, Any]],
    proof_points: list[dict[str, Any]],
    demo_prep: list[dict[str, Any]],
    handoff_criteria: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fallbacks = set(context["fallbacks_used"])
    values = {
        "buyer": context["buyer"] if "buyer" not in fallbacks else "",
        "target_buyer": (
            context["buyer"]
            and context["target_user"]
            and not {"buyer", "target_user"} & fallbacks
        ),
        "qualification_signals": (
            qualification_signals[0]["positive_evidence"]
            if not {"buyer", "workflow_context"} & fallbacks
            else ""
        ),
        "discovery_questions": (
            discovery_questions[0]["listen_for"]
            if "current_workaround" not in fallbacks
            else ""
        ),
        "proof_points": proof_points[2]["evidence"]
        if context["validation_plan"]
        and "still needs validation evidence" not in proof_points[2]["evidence"]
        else "",
        "demo_prep": demo_prep[1]["prep"] if "value_proposition" not in fallbacks else "",
        "handoff_criteria": handoff_criteria[2]["handoff_evidence"]
        if handoff_criteria[2]["handoff_evidence"] != "Named success metric, next owner, and date."
        else "",
    }
    actions: list[dict[str, Any]] = []
    for item in REQUIRED_EVIDENCE:
        if _has_value(values.get(item["field"])):
            continue
        actions.append(
            {
                "field": item["field"],
                "label": item["label"],
                "owner_role": _missing_owner(item["field"]),
                "action": item["action"],
            }
        )
    return actions


def _sales_readiness_gate(
    design_brief: dict[str, Any], missing_actions: list[dict[str, Any]]
) -> str:
    status = design_brief.get("design_status")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if missing_actions:
        return "needs_sales_evidence"
    if status in {"approved", "published"} and readiness >= 75:
        return "ready_for_seller_use"
    if status in {"approved", "published"}:
        return "approved_needs_sales_readiness"
    return "needs_design_approval"


def _flatten_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "section_id": section["id"],
            "section_title": section["title"],
            "section_owner_role": section["owner_role"],
        }
        for section in sections
        for item in section["items"]
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
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

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


def _source_idea_ids(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])
    return list(dict.fromkeys(source_idea_ids))


def _source_evidence_ids(source_ideas: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get("evidence_signals")))
        values.extend(_string_list(idea.get("inspiring_insights")))
    return sorted(_dedupe(values))


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _first_with_label(fallbacks: list[str], field: str, *candidates: tuple[Any, str]) -> str:
    for value, label in candidates:
        text = _first_text(*value) if isinstance(value, list) else _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = _compact("; ".join(value))
        else:
            text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, dict):
        return [_compact(f"{key}: {item}") for key, item in value.items() if _compact(key)]
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe(values: list[str]) -> list[str]:
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


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _missing_owner(field: str) -> str:
    owners = {
        "buyer": "Account executive",
        "target_buyer": "Account executive",
        "qualification_signals": "Account executive",
        "discovery_questions": "Sales engineer",
        "proof_points": "Product marketing",
        "demo_prep": "Sales engineer",
        "handoff_criteria": "Customer success owner",
    }
    return owners[field]


def _missing_summary(missing_actions: list[dict[str, Any]]) -> str:
    if not missing_actions:
        return "No missing evidence actions remain."
    fields = ", ".join(action["field"] for action in missing_actions)
    return f"Missing sales enablement evidence: {fields}."


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
