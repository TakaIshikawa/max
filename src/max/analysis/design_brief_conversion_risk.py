"""Deterministic pilot-to-paid conversion risk reports for design briefs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

KIND = "max.design_brief.conversion_risk"
SCHEMA_VERSION = "max.design_brief.conversion_risk.v1"

_VALIDATED_STATUSES = {"approved", "validated", "ready", "launched", "active"}
_WEAK_STATUSES = {"draft", "candidate", "proposed", "backlog", "new"}

_COMMERCIAL_FRICTION_TERMS = (
    "budget",
    "pricing",
    "procurement",
    "contract",
    "legal",
    "security",
    "compliance",
    "approval",
    "roi",
    "willingness",
)
_URGENCY_TERMS = ("urgent", "deadline", "now", "pressure", "initiative", "launch", "mandate")
_PROOF_TERMS = ("pilot", "validation", "evidence", "metric", "survey", "interview", "proof")


def build_design_brief_conversion_risk(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a pilot-to-paid conversion risk report from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = _source_idea_ids(design_brief, source_ideas)
    context = _conversion_context(design_brief, source_ideas, lead_idea)
    dimensions = _score_dimensions(design_brief, source_ideas, context)
    score = _risk_score(dimensions)
    risk_band = _risk_band(score)
    blockers = _conversion_blockers(dimensions, context, source_idea_ids, risk_band)
    proof_gaps = _proof_gaps(context, source_ideas, source_idea_ids)
    objections = _buyer_objections(context, dimensions, source_idea_ids)
    mitigations = _mitigation_actions(blockers, proof_gaps, objections, context)
    experiments = _validation_experiments(context, blockers, proof_gaps, source_idea_ids, risk_band)

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
            "score": score,
            "risk_band": risk_band,
            "target_buyer": context["buyer"],
            "target_user": context["target_user"],
            "workflow_context": context["workflow_context"],
            "primary_value": context["value_proposition"],
            "conversion_gate": _conversion_gate(risk_band, blockers),
            "blocker_count": len(blockers),
            "proof_gap_count": len(proof_gaps),
            "buyer_objection_count": len(objections),
            "experiment_count": len(experiments),
            "fallbacks_used": context["fallbacks_used"],
        },
        "conversion_context": context,
        "score_dimensions": dimensions,
        "conversion_blockers": blockers,
        "proof_gaps": proof_gaps,
        "buyer_objections": objections,
        "mitigation_actions": mitigations,
        "validation_experiments": experiments,
        "source_ideas": source_ideas,
    }


def render_design_brief_conversion_risk(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render a conversion risk report as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported conversion risk format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Conversion Risk Report: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        f"Design brief: `{brief['id']}`",
        f"Risk band: `{summary['risk_band']}`",
        f"Score: {summary['score']}/100",
        f"Conversion gate: {summary['conversion_gate']}",
        f"Source ideas: {_inline_ids(brief.get('source_idea_ids') or [])}",
        "",
        "## Conversion Context",
        "",
        f"- Target buyer: {summary['target_buyer']}",
        f"- Target user: {summary['target_user']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Primary value: {summary['primary_value']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Conversion Blockers",
        "",
    ]
    for blocker in report["conversion_blockers"]:
        lines.extend(
            [
                f"- **{blocker['label']}** ({blocker['severity']}): {blocker['summary']}",
                f"  Validation step: {blocker['validation_step']}",
                f"  Source references: {_inline_ids(blocker['source_reference_ids'])}",
            ]
        )

    lines.extend(["", "## Proof Gaps", ""])
    for gap in report["proof_gaps"]:
        lines.append(
            f"- **{gap['claim']}**: {gap['gap']} -> {gap['needed_evidence']}"
        )

    lines.extend(["", "## Buyer Objections", ""])
    for objection in report["buyer_objections"]:
        lines.extend(
            [
                f"- **{objection['objection']}**",
                f"  Response: {objection['response']}",
                f"  Proof needed: {objection['proof_needed']}",
            ]
        )

    lines.extend(["", "## Mitigation Actions", ""])
    for action in report["mitigation_actions"]:
        lines.append(f"- **{action['owner_role']}**: {action['action']} ({action['addresses']})")

    lines.extend(["", "## Validation Experiments", ""])
    for experiment in report["validation_experiments"]:
        lines.extend(
            [
                f"### {experiment['id']}: {experiment['name']}",
                "",
                f"- Hypothesis: {experiment['hypothesis']}",
                f"- Method: {experiment['method']}",
                f"- Success signal: {experiment['success_signal']}",
                f"- Kill signal: {experiment['kill_signal']}",
                "",
            ]
        )

    lines.extend(["## Score Dimensions", ""])
    for dimension in report["score_dimensions"]:
        lines.append(
            f"- **{dimension['label']}**: {dimension['points']} point(s), "
            f"{dimension['band']} - {dimension['summary']}"
        )

    return "\n".join(lines).rstrip() + "\n"


def conversion_risk_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return (
        f"{_filename_part(str(design_brief['id']))}-"
        f"{_filename_part(str(design_brief.get('title') or 'conversion-risk'))}-"
        f"conversion-risk.{extension}"
    )


def _conversion_context(
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
    workaround = _first_with_label(
        fallbacks,
        "current_workaround",
        (design_brief.get("current_workaround"), "design_brief.current_workaround"),
        (lead_idea and lead_idea.get("current_workaround"), "lead_idea.current_workaround"),
        (_field_values(source_ideas, "current_workaround"), "source_ideas.current_workaround"),
        ("manual process or fragmented tooling", "explicit_fallback"),
    )
    validation = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        *_field_values(source_ideas, "validation_plan"),
    )
    why_now = _first_text(
        design_brief.get("why_this_now"),
        lead_idea and lead_idea.get("why_now"),
        *_field_values(source_ideas, "why_now"),
    )
    first_customers = _first_text(
        design_brief.get("first_10_customers"),
        lead_idea and lead_idea.get("first_10_customers"),
        *_field_values(source_ideas, "first_10_customers"),
    )
    risks = _dedupe(
        [*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]
    )
    evidence_ids = _source_evidence_ids(source_ideas)
    text = " ".join(
        _string_list(
            [
                design_brief.get("title"),
                design_brief.get("domain"),
                design_brief.get("theme"),
                design_brief.get("why_this_now"),
                design_brief.get("merged_product_concept"),
                design_brief.get("synthesis_rationale"),
                design_brief.get("mvp_scope"),
                design_brief.get("first_milestones"),
                design_brief.get("validation_plan"),
                design_brief.get("risks"),
                *[
                    idea.get(field)
                    for idea in source_ideas
                    for field in (
                        "problem",
                        "solution",
                        "value_proposition",
                        "buyer",
                        "workflow_context",
                        "current_workaround",
                        "why_now",
                        "validation_plan",
                        "first_10_customers",
                        "domain_risks",
                        "evidence_rationale",
                    )
                ],
            ]
        )
    ).lower()
    return {
        "buyer": buyer,
        "target_user": target_user,
        "workflow_context": workflow,
        "value_proposition": value,
        "current_workaround": workaround,
        "why_now": why_now or "No explicit conversion urgency is documented.",
        "validation_plan": validation,
        "first_customers": first_customers,
        "risks": risks,
        "evidence_ids": evidence_ids,
        "text": text,
        "fallbacks_used": fallbacks,
    }


def _score_dimensions(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    status = str(design_brief.get("design_status") or "").lower()
    evidence_count = len(context["evidence_ids"])
    risk_count = len(context["risks"])
    source_count = len([idea for idea in source_ideas if not idea.get("missing")])
    commercial_terms = _matched_terms(context["text"], _COMMERCIAL_FRICTION_TERMS)
    urgency_terms = _matched_terms(context["text"], _URGENCY_TERMS)
    proof_terms = _matched_terms(context["text"], _PROOF_TERMS)

    return [
        {
            "id": "buyer_clarity",
            "label": "Buyer Clarity",
            "points": 4 if "buyer" not in context["fallbacks_used"] else 18,
            "band": "clear" if "buyer" not in context["fallbacks_used"] else "missing",
            "summary": f"Target buyer is {context['buyer']}.",
            "evidence_refs": ["design_brief.buyer"] if "buyer" not in context["fallbacks_used"] else [],
        },
        {
            "id": "proof_strength",
            "label": "Proof Strength",
            "points": -8 if evidence_count >= 3 and context["validation_plan"] else 16 if not context["validation_plan"] else 6,
            "band": "strong" if evidence_count >= 3 and context["validation_plan"] else "planned" if context["validation_plan"] else "missing",
            "summary": f"{evidence_count} linked evidence reference(s); validation plan {'exists' if context['validation_plan'] else 'is missing'}.",
            "evidence_refs": context["evidence_ids"][:4],
        },
        {
            "id": "urgency",
            "label": "Conversion Urgency",
            "points": -6 if urgency_terms and context["why_now"] else 10,
            "band": "clear" if urgency_terms and context["why_now"] else "weak",
            "summary": f"Matched urgency terms: {_inline_terms(urgency_terms)}.",
            "evidence_refs": ["design_brief.why_this_now"] if design_brief.get("why_this_now") else [],
        },
        {
            "id": "commercial_friction",
            "label": "Commercial Friction",
            "points": min(22, len(commercial_terms) * 3 + risk_count * 2),
            "band": "high" if len(commercial_terms) >= 4 or risk_count >= 3 else "medium" if commercial_terms or risk_count else "low",
            "summary": f"{risk_count} explicit risk item(s); matched terms: {_inline_terms(commercial_terms)}.",
            "evidence_refs": ["design_brief.risks"] if risk_count else [],
        },
        {
            "id": "readiness",
            "label": "Readiness and Status",
            "points": _readiness_points(readiness, status),
            "band": "ready" if readiness >= 75 and status in _VALIDATED_STATUSES else "early" if status in _WEAK_STATUSES else "partial",
            "summary": f"Readiness is {readiness:.1f}/100 and status is {status or 'unknown'}.",
            "evidence_refs": ["design_brief.readiness_score", "design_brief.design_status"],
        },
        {
            "id": "source_depth",
            "label": "Source Depth",
            "points": -4 if source_count >= 2 and proof_terms else 8 if source_count else 14,
            "band": "multi-source" if source_count >= 2 else "single-source" if source_count else "missing",
            "summary": f"{source_count} source idea(s); matched proof terms: {_inline_terms(proof_terms)}.",
            "evidence_refs": [idea["id"] for idea in source_ideas if not idea.get("missing")][:4],
        },
    ]


def _conversion_blockers(
    dimensions: list[dict[str, Any]],
    context: dict[str, Any],
    source_idea_ids: list[str],
    risk_band: str,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for dimension in dimensions:
        if dimension["points"] < 8:
            continue
        blockers.append(
            {
                "id": f"CB{len(blockers) + 1}",
                "label": dimension["label"],
                "severity": "high" if dimension["points"] >= 16 or risk_band == "high" else "medium",
                "summary": dimension["summary"],
                "validation_step": _blocker_validation_step(dimension["id"], context),
                "source_reference_ids": dimension["evidence_refs"] or source_idea_ids,
            }
        )
    if not blockers:
        blockers.append(
            {
                "id": "CB1",
                "label": "Conversion Gate",
                "severity": "low",
                "summary": "No major pilot-to-paid blocker is visible in the persisted brief.",
                "validation_step": "Run the planned pilot and confirm buyer, value metric, and paid next step in the recap.",
                "source_reference_ids": source_idea_ids,
            }
        )
    return blockers


def _proof_gaps(
    context: dict[str, Any], source_ideas: list[dict[str, Any]], source_idea_ids: list[str]
) -> list[dict[str, Any]]:
    gaps = [
        {
            "id": "PG1",
            "claim": "Buyer will sponsor paid conversion",
            "gap": "Budget owner and approval path need explicit confirmation.",
            "needed_evidence": f"Interview {context['buyer']} and capture budget, authority, need, and timeline.",
            "source_reference_ids": source_idea_ids,
        },
        {
            "id": "PG2",
            "claim": "Pilot value is measurable",
            "gap": "Paid conversion depends on a measurable before/after outcome.",
            "needed_evidence": context["validation_plan"] or "Define a pilot metric, baseline, target, and pass/fail threshold.",
            "source_reference_ids": context["evidence_ids"] or source_idea_ids,
        },
        {
            "id": "PG3",
            "claim": "Status quo is painful enough to replace",
            "gap": "Current workaround must be worse than adopting the new workflow.",
            "needed_evidence": f"Compare {context['current_workaround']} against {context['value_proposition']}.",
            "source_reference_ids": _source_ids_for_fields(source_ideas, ("current_workaround", "problem"), source_idea_ids),
        },
    ]
    if context["fallbacks_used"]:
        gaps.insert(
            0,
            {
                "id": "PG0",
                "claim": "Core conversion inputs are known",
                "gap": f"Missing persisted fields: {', '.join(context['fallbacks_used'])}.",
                "needed_evidence": "Complete the brief with buyer, user, workflow, value, workaround, and validation evidence before forecast use.",
                "source_reference_ids": source_idea_ids,
            },
        )
    return gaps


def _buyer_objections(
    context: dict[str, Any],
    dimensions: list[dict[str, Any]],
    source_idea_ids: list[str],
) -> list[dict[str, Any]]:
    primary_risk = context["risks"][0] if context["risks"] else "The pilot may not prove paid value."
    commercial = next(item for item in dimensions if item["id"] == "commercial_friction")
    return [
        {
            "id": "BO1",
            "objection": "Why pay instead of continuing the current workaround?",
            "likely_from": context["buyer"],
            "response": f"Quantify the cost of {context['current_workaround']} against {context['value_proposition']}.",
            "proof_needed": "Before/after metric from the pilot.",
            "source_reference_ids": source_idea_ids,
        },
        {
            "id": "BO2",
            "objection": "This is useful, but not urgent enough to buy now.",
            "likely_from": context["buyer"],
            "response": f"Tie the buying case to: {context['why_now']}",
            "proof_needed": "Deadline, initiative owner, or risk of delay.",
            "source_reference_ids": source_idea_ids,
        },
        {
            "id": "BO3",
            "objection": primary_risk,
            "likely_from": "approver",
            "response": "Convert the concern into a narrow proof requirement and explicit pilot exit criterion.",
            "proof_needed": commercial["summary"],
            "source_reference_ids": commercial["evidence_refs"] or source_idea_ids,
        },
    ]


def _mitigation_actions(
    blockers: list[dict[str, Any]],
    proof_gaps: list[dict[str, Any]],
    objections: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "id": "MA1",
            "owner_role": "Product lead",
            "action": f"Reduce the pilot to the first paid-value moment for {context['workflow_context']}.",
            "addresses": blockers[0]["label"],
        },
        {
            "id": "MA2",
            "owner_role": "Go-to-market owner",
            "action": f"Secure {context['buyer']} approval criteria before the pilot starts.",
            "addresses": proof_gaps[0]["claim"],
        },
        {
            "id": "MA3",
            "owner_role": "Customer success owner",
            "action": "Prepare objection responses, proof capture, and next-step handoff before pilot kickoff.",
            "addresses": objections[0]["objection"],
        },
    ]


def _validation_experiments(
    context: dict[str, Any],
    blockers: list[dict[str, Any]],
    proof_gaps: list[dict[str, Any]],
    source_idea_ids: list[str],
    risk_band: str,
) -> list[dict[str, Any]]:
    experiments = [
        {
            "id": "EXP1",
            "name": "Buyer Commitment Interview",
            "hypothesis": f"{context['buyer']} can name the paid conversion path after seeing the pilot scope.",
            "method": "Run three buyer interviews with pricing, approval path, and success metric prompts.",
            "success_signal": "At least two buyers state budget owner, approval step, and paid success threshold.",
            "kill_signal": "Buyers like the concept but cannot identify budget ownership or approval path.",
            "source_reference_ids": source_idea_ids,
        },
        {
            "id": "EXP2",
            "name": "Pilot Proof Sprint",
            "hypothesis": f"{context['target_user']} will produce measurable value in {context['workflow_context']}.",
            "method": context["validation_plan"] or "Run a five-account pilot with a baseline metric, target, and conversion ask.",
            "success_signal": "Pilot users hit the value metric and the buyer agrees to a paid next step.",
            "kill_signal": "Pilot activity does not change the buyer's willingness to pay.",
            "source_reference_ids": context["evidence_ids"] or source_idea_ids,
        },
    ]
    if risk_band != "low" or context["fallbacks_used"]:
        experiments.insert(
            0,
            {
                "id": "EXP0",
                "name": "Conversion Blocker Triage",
                "hypothesis": f"The top blocker can be resolved before the pilot-to-paid ask: {blockers[0]['label']}.",
                "method": f"Resolve {proof_gaps[0]['needed_evidence']} and rerun the conversion gate.",
                "success_signal": "Blocker severity drops and the paid conversion ask has a named owner.",
                "kill_signal": "The blocker remains unresolved after direct buyer validation.",
                "source_reference_ids": source_idea_ids,
            },
        )
    return experiments


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
    ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    return ids or _string_list(design_brief.get("source_idea_ids"))


def _source_ids_for_fields(
    source_ideas: list[dict[str, Any]], fields: tuple[str, ...], fallback: list[str]
) -> list[str]:
    ids = [
        idea["id"]
        for idea in source_ideas
        if not idea.get("missing") and any(_has_value(idea.get(field)) for field in fields)
    ]
    return list(dict.fromkeys(ids)) or fallback


def _source_evidence_ids(source_ideas: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        ids.extend(_string_list(idea.get("evidence_signals")))
        ids.extend(_string_list(idea.get("inspiring_insights")))
        if _has_value(idea.get("evidence_rationale")):
            ids.append(f"{idea['id']}.evidence_rationale")
    return sorted(dict.fromkeys(ids))


def _blocker_validation_step(dimension_id: str, context: dict[str, Any]) -> str:
    steps = {
        "buyer_clarity": f"Identify the economic buyer and confirm who can approve paid use of {context['workflow_context']}.",
        "proof_strength": "Attach validation evidence, a baseline metric, and a pass/fail threshold before asking for paid conversion.",
        "urgency": "Confirm why the buyer needs this solved now and what happens if the workflow does not change.",
        "commercial_friction": "Run pricing, procurement, security, and legal objection discovery before pilot kickoff.",
        "readiness": "Move the brief through validation or narrow scope until the paid pilot ask is credible.",
        "source_depth": "Add independent source ideas or evidence references for buyer, workflow, and value claims.",
    }
    return steps.get(dimension_id, "Validate the blocker with the buyer before advancing the pilot.")


def _conversion_gate(risk_band: str, blockers: list[dict[str, Any]]) -> str:
    if risk_band == "low":
        return "ready_for_paid_pilot"
    if any(blocker["severity"] == "high" for blocker in blockers):
        return "resolve_blockers_before_conversion_ask"
    return "run_targeted_validation_before_paid_ask"


def _risk_score(dimensions: list[dict[str, Any]]) -> int:
    return max(0, min(100, 34 + sum(int(item["points"]) for item in dimensions)))


def _risk_band(score: int) -> str:
    if score >= 65:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _readiness_points(readiness: float, status: str) -> int:
    if readiness >= 80 and status in _VALIDATED_STATUSES:
        return -10
    if readiness >= 65:
        return 0
    if readiness < 40 or status in _WEAK_STATUSES:
        return 16
    return 8


def _first_with_label(
    fallbacks: list[str],
    label: str,
    *candidates: tuple[Any, str],
) -> str:
    for value, source in candidates:
        text = _first_text(value)
        if text:
            if source == "explicit_fallback":
                fallbacks.append(label)
            return text
    fallbacks.append(label)
    return ""


def _first_text(*values: Any) -> str:
    for value in values:
        for item in _string_list(value):
            if item.strip():
                return item.strip()
    return ""


def _field_values(records: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for record in records:
        if record.get("missing"):
            continue
        values.extend(_string_list(record.get(field)))
    return values


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [json.dumps(value, sort_keys=True)]
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_string_list(item))
        return result
    return [str(value)]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _has_value(value: Any) -> bool:
    return bool(_string_list(value))


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def _inline_ids(ids: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in ids) if ids else "none"


def _inline_terms(terms: list[str]) -> str:
    return ", ".join(terms) if terms else "none"


def _filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return cleaned or "design-brief"
