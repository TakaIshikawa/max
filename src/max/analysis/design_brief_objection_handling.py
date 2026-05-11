"""Deterministic objection handling guides for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.objection_handling.v1"
KIND = "max.design_brief.objection_handling"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "perspective",
    "objection",
    "response",
    "proof_points",
    "evidence_gap",
    "next_action",
    "evidence_refs",
    "source_idea_ids",
)

PERSPECTIVES: tuple[str, ...] = (
    "buyer",
    "user",
    "security",
    "procurement",
    "implementation",
    "pricing",
    "executive",
)


def build_design_brief_objection_handling_guide(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build an objection handling guide from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    context = _context(design_brief, source_ideas)
    objections = [
        _objection(perspective, design_brief, context, source_idea_ids)
        for perspective in PERSPECTIVES
    ]

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
            "buyer": context["buyer"],
            "target_user": context["target_user"],
            "workflow_context": context["workflow_context"],
            "value_proposition": context["value_proposition"],
            "evidence_posture": context["evidence_posture"],
            "objection_count": len(objections),
            "fallbacks_used": context["fallbacks_used"],
        },
        "objections": objections,
        "evidence_references": _evidence_references(design_brief, source_ideas),
    }


def render_design_brief_objection_handling_guide(
    report: dict[str, Any], fmt: str = "markdown"
) -> str:
    """Render an objection handling guide as Markdown, JSON, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_objection_handling_guide_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported objection handling guide format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Objection Handling Guide: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Buyer: {summary['buyer']}",
        f"Target user: {summary['target_user']}",
        f"Workflow: {summary['workflow_context']}",
        f"Evidence posture: {summary['evidence_posture']}",
        "",
        "## Objections",
        "",
    ]
    for item in report["objections"]:
        lines.extend(
            [
                f"### {item['perspective'].title()}",
                "",
                f"- Objection: {item['objection']}",
                f"- Response: {item['response']}",
                f"- Proof points: {'; '.join(item['proof_points']) or 'None'}",
                f"- Evidence gap: {item['evidence_gap']}",
                f"- Next action: {item['next_action']}",
                "",
            ]
        )
    lines.extend(["## Evidence References", ""])
    references = report.get("evidence_references") or []
    lines.extend(f"- {item['reference']}" for item in references) if references else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_objection_handling_guide_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    brief = report.get("design_brief") or {}
    for item in report.get("objections") or []:
        writer.writerow(
            {
                "design_brief_id": brief.get("id", ""),
                "design_brief_title": brief.get("title", ""),
                "perspective": item.get("perspective", ""),
                "objection": item.get("objection", ""),
                "response": item.get("response", ""),
                "proof_points": json.dumps(item.get("proof_points") or [], sort_keys=True),
                "evidence_gap": item.get("evidence_gap", ""),
                "next_action": item.get("next_action", ""),
                "evidence_refs": json.dumps(item.get("evidence_refs") or [], sort_keys=True),
                "source_idea_ids": json.dumps(item.get("source_idea_ids") or [], sort_keys=True),
            }
        )
    return output.getvalue()


def _context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    fallbacks: list[str] = []
    buyer = _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"))
    target_user = _first_text(design_brief.get("specific_user"), _field_values(source_ideas, "specific_user"))
    workflow = _first_text(design_brief.get("workflow_context"), _field_values(source_ideas, "workflow_context"))
    value = _first_text(
        _field_values(source_ideas, "value_proposition"),
        design_brief.get("merged_product_concept"),
        design_brief.get("synthesis_rationale"),
    )
    validation = _first_text(design_brief.get("validation_plan"), _field_values(source_ideas, "validation_plan"))
    risks = _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    proof = _proof_points(design_brief, source_ideas)

    if not buyer:
        buyer = "economic sponsor"
        fallbacks.append("buyer")
    if not target_user:
        target_user = "primary user"
        fallbacks.append("specific_user")
    if not workflow:
        workflow = "target workflow"
        fallbacks.append("workflow_context")
    if not value:
        value = f"Improve {workflow} for {target_user}."
        fallbacks.append("value_proposition")
    if not validation:
        validation = "No validation plan captured."
        fallbacks.append("validation_plan")

    readiness = float(design_brief.get("readiness_score") or 0.0)
    evidence_posture = "high_readiness" if readiness >= 75 and len(proof) >= 3 else "low_evidence"
    return {
        "buyer": buyer,
        "target_user": target_user,
        "workflow_context": workflow,
        "value_proposition": value,
        "validation_plan": validation,
        "risks": risks,
        "proof_points": proof,
        "evidence_posture": evidence_posture,
        "fallbacks_used": fallbacks,
    }


def _objection(
    perspective: str,
    design_brief: dict[str, Any],
    context: dict[str, Any],
    source_idea_ids: list[str],
) -> dict[str, Any]:
    title = design_brief["title"]
    risks = context["risks"]
    risk = risks[0] if risks else "No explicit risk captured."
    proof = context["proof_points"][:3]
    if context["evidence_posture"] == "low_evidence":
        gap = f"Validate {perspective} proof for {title}; current guide relies on brief assumptions."
    else:
        gap = "No material gap; keep proof current during pilot."

    templates = {
        "buyer": (
            f"Why should {context['buyer']} prioritize {title} now?",
            f"Tie the decision to {context['workflow_context']} and the stated value: {context['value_proposition']}",
            "Run a sponsor review that confirms urgency, owner, and success threshold.",
            ["design_brief.buyer", "design_brief.why_this_now"],
        ),
        "user": (
            f"Will this disrupt how {context['target_user']} works today?",
            f"Anchor the response in the target workflow and show how the first milestone reduces day-to-day friction for {context['target_user']}.",
            "Capture one workflow walkthrough and one usability risk before launch.",
            ["design_brief.specific_user", "design_brief.workflow_context", "design_brief.first_milestones"],
        ),
        "security": (
            f"Can we approve {title} without creating security or privacy exposure?",
            f"Use the known risk record as the review checklist and require owner disposition for: {risk}",
            "Map data touched, controls required, and approval owner before procurement review.",
            ["design_brief.risks"],
        ),
        "procurement": (
            "How do we justify vendor, legal, and purchasing effort?",
            f"Position the request as scoped validation for {context['workflow_context']} with reversible milestones and named evidence.",
            "Prepare a lightweight intake packet with owner, scope, risks, and pilot exit criteria.",
            ["design_brief.mvp_scope", "design_brief.validation_plan"],
        ),
        "implementation": (
            "Will implementation drag beyond the approved scope?",
            f"Keep implementation bounded to the MVP scope and sequence it through the validation plan: {context['validation_plan']}",
            "Convert MVP scope and first milestones into owner-assigned delivery checkpoints.",
            ["design_brief.mvp_scope", "design_brief.first_milestones", "design_brief.validation_plan"],
        ),
        "pricing": (
            "How do we know the price or package will match value delivered?",
            f"Use {context['value_proposition']} as the value metric and test willingness-to-pay with {context['buyer']}.",
            "Add pricing discovery to the next buyer conversation and capture disqualifying thresholds.",
            ["design_brief.buyer", "source_ideas.value_proposition"],
        ),
        "executive": (
            "Why is this the right strategic bet compared with other priorities?",
            f"Frame {title} as a readiness-backed bet for {context['workflow_context']} with explicit evidence gaps and risk controls.",
            "Ask leadership to approve the next milestone only after evidence gaps are assigned.",
            ["design_brief.readiness_score", "design_brief.synthesis_rationale"],
        ),
    }
    objection, response, next_action, evidence_refs = templates[perspective]
    return {
        "perspective": perspective,
        "objection": objection,
        "response": response,
        "proof_points": proof or ["No direct proof point captured yet."],
        "evidence_gap": gap,
        "next_action": next_action,
        "evidence_refs": evidence_refs,
        "source_idea_ids": source_idea_ids,
    }


def _proof_points(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    points = [
        _first_text(design_brief.get("validation_plan")),
        *_field_values(source_ideas, "evidence_rationale"),
        *_field_values(source_ideas, "value_proposition"),
        *_string_list(design_brief.get("first_milestones")),
    ]
    return _dedupe([point for point in points if point])[:5]


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    relationships = list(design_brief.get("sources") or [])
    if not relationships:
        relationships = [
            {"idea_id": idea_id, "role": "source", "rank": rank}
            for rank, idea_id in enumerate(_string_list(design_brief.get("source_idea_ids")))
        ]
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relationship in sorted(relationships, key=lambda item: (item.get("rank", 0), item.get("idea_id", ""))):
        idea_id = relationship.get("idea_id")
        if not idea_id or idea_id in seen:
            continue
        seen.add(idea_id)
        unit = store.get_buildable_unit(idea_id)
        data = unit.model_dump(mode="json") if unit is not None else {"id": idea_id, "missing": True}
        data["role"] = "lead" if idea_id == design_brief.get("lead_idea_id") else relationship.get("role", "source")
        data["rank"] = relationship.get("rank", len(ideas))
        ideas.append(data)
    return ideas


def _evidence_references(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for field in ("buyer", "specific_user", "workflow_context", "validation_plan", "mvp_scope", "first_milestones", "risks"):
        if _has_value(design_brief.get(field)):
            refs.append({"type": "design_brief", "reference": f"design_brief.{field}"})
    for idea in source_ideas:
        if idea.get("id") and not idea.get("missing"):
            refs.append({"type": "source_idea", "reference": f"idea:{idea['id']}"})
    return refs


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        value = item.get(field)
        values.extend(_string_list(value) if isinstance(value, list) else [_compact(value)])
    return [value for value in values if value]


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            nested = _first_text(*value)
            if nested:
                return nested
            continue
        text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    text = _compact(value)
    return [text] if text else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _compact(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _has_value(value: Any) -> bool:
    return bool(_string_list(value))


def _compact(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
