"""Operational dependency map for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.operational_dependency_map.v1"
KIND = "max.design_brief.operational_dependency_map"
CSV_COLUMNS = ("design_brief_id", "design_brief_title", "section", "item_id", "name", "owner", "dependency", "status", "description", "evidence_refs", "source_idea_ids")


def build_design_brief_operational_dependency_map(store: Store, brief_id: str) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    ideas = _source_ideas(store, brief)
    source_ids = [idea["id"] for idea in ideas if not idea.get("missing")] or _string_list(brief.get("source_idea_ids"))
    context = _context(brief, ideas)
    groups = [
        _item("DEP1", "implementation_path", "implementation", context["implementation_owner"], context["stack"], "active", f"Implementation dependency for {context['workflow_context']}.", ["design_brief.tech_approach"], source_ids),
        _item("DEP2", "support_path", "support", context["support_owner"], context["support_model"], "needs_review" if context["support_model"].startswith("Confirm") else "active", "Support ownership and escalation dependency.", ["design_brief.validation_plan"], source_ids),
    ]
    owner_handoffs = [
        _item("HOF1", "product_to_engineering", "handoff", "Product lead", context["workflow_context"], "required", "Transfer scope, risks, and launch evidence to implementation owner.", ["design_brief.mvp_scope"], source_ids),
        _item("HOF2", "engineering_to_support", "handoff", context["implementation_owner"], context["support_model"], "required", "Transfer operational runbook and known risks to support owner.", ["design_brief.risks"], source_ids),
    ]
    external_systems = [_item(f"EXT{idx}", system, "external_system", context["implementation_owner"], system, "needs_owner", f"External system dependency detected for {brief['title']}.", ["source_ideas.tech_approach"], source_ids) for idx, system in enumerate(context["external_systems"], start=1)]
    risk_links = [_item(f"RSK{idx}", f"risk_{idx}", "risk", context["risk_owner"], risk, "open", risk, ["design_brief.risks", "source_ideas.domain_risks"], source_ids) for idx, risk in enumerate(context["risks"] or ["No explicit risk captured; confirm launch blockers."], start=1)]
    checkpoint_links = [
        _item("CHK1", "readiness_review", "checkpoint", "Product lead", context["validation_plan"], "required", "Confirm dependencies, owners, risks, and evidence before pilot.", ["design_brief.validation_plan"], source_ids),
        _item("CHK2", "support_handoff", "checkpoint", context["support_owner"], context["support_model"], "required", "Confirm support handoff before customer exposure.", ["design_brief.specific_user"], source_ids),
    ]
    evidence = _evidence_references(brief, ideas)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {"project": "max", "entity_type": "design_brief", "id": brief["id"], "generated_at": brief.get("updated_at") or brief.get("created_at")},
        "design_brief": {"id": brief["id"], "title": brief["title"], "domain": brief.get("domain", ""), "theme": brief.get("theme", ""), "readiness_score": float(brief.get("readiness_score") or 0.0), "design_status": brief.get("design_status", ""), "lead_idea_id": brief.get("lead_idea_id", ""), "source_idea_ids": source_ids},
        "summary": {"title": brief["title"], "dependency_group_count": len(groups), "owner_handoff_count": len(owner_handoffs), "external_system_count": len(external_systems), "risk_link_count": len(risk_links), "checkpoint_link_count": len(checkpoint_links), "fallbacks_used": context["fallbacks"]},
        "dependency_groups": groups,
        "owner_handoffs": owner_handoffs,
        "external_systems": external_systems,
        "risk_links": risk_links,
        "checkpoint_links": checkpoint_links,
        "evidence_references": evidence,
    }


def render_design_brief_operational_dependency_map(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_operational_dependency_map_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported dependency map format: {fmt}")
    brief = report["design_brief"]
    lines = [f"# Operational Dependency Map: {brief['title']}", "", f"Schema: `{report['schema_version']}`", f"Design brief: `{brief['id']}`", ""]
    for title, key in (("Dependency Groups", "dependency_groups"), ("Owner Handoffs", "owner_handoffs"), ("External Systems", "external_systems"), ("Risk Links", "risk_links"), ("Checkpoint Links", "checkpoint_links"), ("Evidence References", "evidence_references")):
        lines.extend([f"## {title}", ""])
        items = report.get(key) or []
        if not items:
            lines.append("- None")
        elif key == "evidence_references":
            lines.extend(f"- {item['reference']}" for item in items)
        else:
            lines.extend(f"- **{item['id']} {item['name']}** ({item['owner']}): {item['description']}" for item in items)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_operational_dependency_map_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    brief = report.get("design_brief") or {}
    for section in ("dependency_groups", "owner_handoffs", "external_systems", "risk_links", "checkpoint_links"):
        for item in report.get(section) or []:
            writer.writerow({
                "design_brief_id": brief.get("id"),
                "design_brief_title": brief.get("title"),
                "section": section,
                "item_id": item.get("id"),
                "name": item.get("name"),
                "owner": item.get("owner"),
                "dependency": item.get("dependency"),
                "status": item.get("status"),
                "description": item.get("description"),
                "evidence_refs": json.dumps(item.get("evidence_refs") or []),
                "source_idea_ids": json.dumps(item.get("source_idea_ids") or []),
            })
    return output.getvalue()


def _context(brief: dict[str, Any], ideas: list[dict[str, Any]]) -> dict[str, Any]:
    fallbacks = []
    workflow = _first(brief.get("workflow_context"), _field_values(ideas, "workflow_context")) or "primary workflow"
    validation = _first(brief.get("validation_plan"), _field_values(ideas, "validation_plan")) or "Confirm launch dependency readiness."
    stack = _first(brief.get("tech_approach"), _field_values(ideas, "tech_approach"), _field_values(ideas, "suggested_stack")) or "implementation stack to confirm"
    risks = _dedupe([*_string_list(brief.get("risks")), *_field_values(ideas, "domain_risks")])
    if workflow == "primary workflow":
        fallbacks.append("workflow_context")
    if validation == "Confirm launch dependency readiness.":
        fallbacks.append("validation_plan")
    if stack == "implementation stack to confirm":
        fallbacks.append("tech_approach")
    text = " ".join([stack, _first(brief.get("merged_product_concept"), "")]).lower()
    systems = [name for name in ("OpenAI", "Slack", "Stripe", "Salesforce", "GitHub", "Jira", "Linear") if name.lower() in text]
    if not systems and "integrat" in text:
        systems = ["Primary external system"]
    return {"workflow_context": workflow, "validation_plan": validation, "stack": stack, "risks": risks, "external_systems": systems, "implementation_owner": "Engineering lead", "support_owner": "Support owner", "support_model": "Confirm support model" if not _first(brief.get("specific_user"), _field_values(ideas, "specific_user")) else "Pilot support workflow", "risk_owner": "Risk owner", "fallbacks": fallbacks}


def _source_ideas(store: Store, brief: dict[str, Any]) -> list[dict[str, Any]]:
    ids = _dedupe([brief.get("lead_idea_id"), *_string_list(brief.get("source_idea_ids")), *[source.get("idea_id") for source in brief.get("sources", []) if isinstance(source, dict)]])
    ideas = []
    for idea_id in ids:
        unit = store.get_buildable_unit(str(idea_id))
        ideas.append(_unit_dict(unit) if unit else {"id": str(idea_id), "missing": True})
    return ideas


def _unit_dict(unit: Any) -> dict[str, Any]:
    return {field: getattr(unit, field, "") for field in ("id", "title", "buyer", "specific_user", "workflow_context", "validation_plan", "domain_risks", "tech_approach", "suggested_stack", "evidence_signals", "inspiring_insights")}


def _evidence_references(brief: dict[str, Any], ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs = [{"type": "design_brief", "reference": f"design_brief.{field}"} for field in ("workflow_context", "validation_plan", "risks") if brief.get(field)]
    refs.extend({"type": "source_idea", "reference": f"idea:{idea['id']}"} for idea in ideas if idea.get("id") and not idea.get("missing"))
    return refs


def _item(item_id: str, name: str, dependency_type: str, owner: str, dependency: str, status: str, description: str, evidence_refs: list[str], source_ids: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "type": dependency_type, "owner": owner, "dependency": dependency, "status": status, "description": description, "evidence_refs": evidence_refs, "source_idea_ids": source_ids}


def _field_values(ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in ideas:
        raw = idea.get(field)
        values.extend(_string_list(raw))
    return values


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [f"{key}={item}" for key, item in sorted(value.items()) if str(item).strip()]
    return [str(value)] if str(value or "").strip() else []


def _first(*values: Any) -> str:
    for value in values:
        items = _string_list(value)
        if items:
            return items[0]
    return ""


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        for item in _string_list(value):
            if item not in seen:
                seen.add(item)
                result.append(item)
    return result
