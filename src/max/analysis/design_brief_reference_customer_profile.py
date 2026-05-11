"""Deterministic reference customer profiles for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.reference_customer_profile.v1"
KIND = "max.design_brief.reference_customer_profile"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "name",
    "description",
    "owner",
    "evidence_refs",
    "source_idea_ids",
)


def build_design_brief_reference_customer_profile(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a reference customer profile from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    context = _context(design_brief, source_ideas)
    attributes = _attributes(context, source_idea_ids)
    disqualifiers = _disqualifiers(context, source_idea_ids)
    milestones = _milestones(context, source_idea_ids)
    prompts = _prompts(context, source_idea_ids)
    readiness = _readiness_score(design_brief, context, attributes, milestones)

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
            "reference_posture": readiness["posture"],
        },
        "ideal_customer_attributes": attributes,
        "disqualifiers": disqualifiers,
        "proof_milestones": milestones,
        "testimonial_prompts": prompts,
        "readiness_score": readiness,
        "evidence_references": _evidence_references(design_brief, source_ideas),
    }


def render_design_brief_reference_customer_profile(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_reference_customer_profile_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported reference customer profile format: {fmt}")

    brief = report["design_brief"]
    readiness = report["readiness_score"]
    lines = [
        f"# Reference Customer Profile: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Readiness score: {readiness['score']}/100 ({readiness['posture']})",
        "",
    ]
    for section, title in (
        ("ideal_customer_attributes", "Ideal Customer Attributes"),
        ("disqualifiers", "Disqualifiers"),
        ("proof_milestones", "Proof Milestones"),
        ("testimonial_prompts", "Testimonial Prompts"),
    ):
        lines.extend([f"## {title}", ""])
        for item in report.get(section) or []:
            lines.append(f"- **{item['name']}**: {item['description']}")
        lines.append("")
    lines.extend(["## Readiness Factors", ""])
    lines.extend(f"- {factor}" for factor in readiness.get("factors") or [])
    lines.extend(["", "## Evidence References", ""])
    refs = report.get("evidence_references") or []
    lines.extend(f"- {item['reference']}" for item in refs) if refs else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_reference_customer_profile_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    brief = report.get("design_brief") or {}
    for section in ("ideal_customer_attributes", "disqualifiers", "proof_milestones", "testimonial_prompts"):
        for item in report.get(section) or []:
            writer.writerow(
                {
                    "design_brief_id": brief.get("id", ""),
                    "design_brief_title": brief.get("title", ""),
                    "section": section,
                    "item_id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "description": item.get("description", ""),
                    "owner": item.get("owner", ""),
                    "evidence_refs": json.dumps(item.get("evidence_refs") or [], sort_keys=True),
                    "source_idea_ids": json.dumps(item.get("source_idea_ids") or [], sort_keys=True),
                }
            )
    return output.getvalue()


def _context(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer")) or "economic sponsor",
        "target_user": _first_text(design_brief.get("specific_user"), _field_values(source_ideas, "specific_user")) or "primary user",
        "workflow_context": _first_text(design_brief.get("workflow_context"), _field_values(source_ideas, "workflow_context")) or "target workflow",
        "value": _first_text(_field_values(source_ideas, "value_proposition"), design_brief.get("merged_product_concept")) or "validated customer value",
        "validation": _first_text(design_brief.get("validation_plan"), _field_values(source_ideas, "validation_plan")),
        "customers": _first_text(_field_values(source_ideas, "first_10_customers")),
        "risks": _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")]),
        "milestones": _string_list(design_brief.get("first_milestones")),
    }


def _attributes(context: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    customer = context["customers"] or f"Teams where {context['buyer']} owns {context['workflow_context']}"
    return [
        _item("RCA1", "Economic sponsor fit", f"{context['buyer']} can approve access, success criteria, and reference participation.", "product_owner", ["design_brief.buyer"], ids),
        _item("RCA2", "Workflow fit", f"{context['target_user']} actively performs {context['workflow_context']}.", "research_owner", ["design_brief.specific_user", "design_brief.workflow_context"], ids),
        _item("RCA3", "Customer segment", customer, "customer_owner", ["source_ideas.first_10_customers"], ids),
    ]


def _disqualifiers(context: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    risk = context["risks"][0] if context["risks"] else "No owner can confirm reference permissions."
    return [
        _item("RCD1", "No sponsor access", f"Disqualify accounts without access to {context['buyer']} or a delegated decision owner.", "customer_owner", ["design_brief.buyer"], ids),
        _item("RCD2", "Workflow mismatch", f"Disqualify accounts where {context['workflow_context']} is not a current priority.", "research_owner", ["design_brief.workflow_context"], ids),
        _item("RCD3", "Unresolved risk", risk, "risk_owner", ["design_brief.risks"], ids),
    ]


def _milestones(context: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    milestone = context["milestones"][0] if context["milestones"] else "complete one validated pilot workflow"
    validation = context["validation"] or "confirm measurable value with the target user"
    return [
        _item("RCM1", "Pilot proof", milestone, "product_owner", ["design_brief.first_milestones"], ids),
        _item("RCM2", "Value proof", validation, "research_owner", ["design_brief.validation_plan"], ids),
        _item("RCM3", "Reference approval", f"Confirm {context['buyer']} approves logo, quote, or private reference use.", "customer_owner", ["design_brief.buyer"], ids),
    ]


def _prompts(context: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    return [
        _item("RCT1", "Before state", f"What made {context['workflow_context']} painful before this product?", "customer_owner", ["design_brief.workflow_context"], ids),
        _item("RCT2", "Value received", f"Which outcome best proves {context['value']}?", "customer_owner", ["source_ideas.value_proposition"], ids),
        _item("RCT3", "Recommendation", f"What would you tell another {context['buyer']} evaluating this?", "customer_owner", ["design_brief.buyer"], ids),
    ]


def _readiness_score(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    attributes: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
) -> dict[str, Any]:
    score = 20
    factors: list[str] = []
    for field, label, points in (
        ("buyer", "buyer identified", 15),
        ("specific_user", "target user identified", 15),
        ("workflow_context", "workflow identified", 15),
        ("validation_plan", "validation plan captured", 15),
    ):
        if _string_list(design_brief.get(field)):
            score += points
            factors.append(label)
    if context["customers"]:
        score += 10
        factors.append("reference segment described")
    if context["risks"]:
        score -= 10
        factors.append("risk requires reference approval")
    if len(attributes) >= 3 and len(milestones) >= 3:
        score += 10
        factors.append("profile and proof milestones complete")
    score = max(0, min(100, score))
    posture = "reference_ready" if score >= 75 else "needs_more_evidence"
    return {"score": score, "posture": posture, "factors": factors or ["sparse brief defaults used"]}


def _item(id: str, name: str, description: str, owner: str, refs: list[str], ids: list[str]) -> dict[str, Any]:
    return {"id": id, "name": name, "description": description, "owner": owner, "evidence_refs": refs, "source_idea_ids": ids}


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas = []
    for rank, idea_id in enumerate(_string_list(design_brief.get("source_idea_ids"))):
        unit = store.get_buildable_unit(idea_id)
        data = unit.model_dump(mode="json") if unit is not None else {"id": idea_id, "missing": True}
        data["rank"] = rank
        ideas.append(data)
    return ideas


def _evidence_references(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs = [{"type": "design_brief", "reference": f"design_brief.{field}"} for field in ("buyer", "specific_user", "workflow_context", "validation_plan", "first_milestones", "risks") if _string_list(design_brief.get(field))]
    refs.extend({"type": "source_idea", "reference": f"idea:{idea['id']}"} for idea in source_ideas if idea.get("id") and not idea.get("missing"))
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


def _compact(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
