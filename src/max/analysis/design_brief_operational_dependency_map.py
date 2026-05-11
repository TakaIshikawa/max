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
CSV_COLUMNS = ("section", "item_id", "name", "owner", "dependency", "severity", "description", "evidence_refs")


def build_design_brief_operational_dependency_map(store: Store, brief_id: str) -> dict[str, Any] | None:
    brief = store.get_design_brief(brief_id)
    if not brief:
        return None
    source_ideas = _source_ideas(store, brief)
    context = _context(brief, source_ideas)
    dependency_groups = [
        _item("DG1", "Implementation dependencies", context["implementation_owner"], context["stack"], "medium", f"Delivery depends on {context['stack']} and scoped milestones.", ["design_brief.tech_approach", "source_ideas.tech_approach"]),
        _item("DG2", "Support dependencies", context["support_owner"], context["support_context"], "medium", f"Support must be ready for {context['workflow_context']}.", ["design_brief.workflow_context"]),
        _item("DG3", "Business dependencies", context["buyer"], context["buyer"], "high", "Launch decisions depend on buyer signoff and unresolved risk disposition.", ["design_brief.buyer", "design_brief.risks"]),
    ]
    owner_handoffs = [
        _item("OH1", "Brief to engineering", context["implementation_owner"], "approved scope", "medium", "Product hands scope, assumptions, and risk links to engineering.", ["design_brief.mvp_scope"]),
        _item("OH2", "Engineering to support", context["support_owner"], "runbook and known issues", "medium", "Engineering hands support owners launch notes and escalation triggers.", ["design_brief.risks"]),
    ]
    external_systems = [_item(f"ES{index}", system, context["implementation_owner"], system, "medium", f"External system required by the operational workflow: {system}.", ["source_ideas.suggested_stack"]) for index, system in enumerate(context["external_systems"], start=1)]
    if not external_systems:
        external_systems = [_item("ES1", "External systems to confirm", context["implementation_owner"], "unknown", "low", "No explicit external system was detected; confirm during delivery planning.", ["design_brief.tech_approach"])]
    risk_links = [_item(f"RL{index}", f"Risk {index}", context["risk_owner"], risk, "high", risk, ["design_brief.risks", "source_ideas.domain_risks"]) for index, risk in enumerate(context["risks"] or ["No explicit risk captured; confirm operational blockers."], start=1)]
    checkpoint_links = [
        _item("CL1", "Scope checkpoint", context["implementation_owner"], context["workflow_context"], "medium", "Confirm implementation dependencies before pilot entry.", ["design_brief.workflow_context"]),
        _item("CL2", "Support checkpoint", context["support_owner"], context["support_context"], "medium", "Confirm support readiness before customer expansion.", ["design_brief.validation_plan"]),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {"project": "max", "entity_type": "design_brief", "id": brief.get("id")},
        "design_brief": {"id": brief.get("id"), "title": brief.get("title", "Untitled"), "source_idea_ids": [idea["id"] for idea in source_ideas if not idea.get("missing")] or _list(brief.get("source_idea_ids"))},
        "summary": {"title": brief.get("title", "Untitled"), "buyer": context["buyer"], "implementation_owner": context["implementation_owner"], "support_owner": context["support_owner"], "dependency_group_count": len(dependency_groups), "external_system_count": len(external_systems), "risk_link_count": len(risk_links)},
        "dependency_groups": dependency_groups,
        "owner_handoffs": owner_handoffs,
        "external_systems": external_systems,
        "risk_links": risk_links,
        "checkpoint_links": checkpoint_links,
        "evidence_references": _evidence(brief, source_ideas),
    }


def render_design_brief_operational_dependency_map(report: dict[str, Any], fmt: str = "markdown") -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_operational_dependency_map_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported operational dependency map format: {fmt}")
    brief = report["design_brief"]
    lines = [f"# Operational Dependency Map: {brief['title']}", "", f"Schema: `{report['schema_version']}`", f"Design brief: `{brief['id']}`", ""]
    for section in ("dependency_groups", "owner_handoffs", "external_systems", "risk_links", "checkpoint_links"):
        lines.extend([f"## {section.replace('_', ' ').title()}", ""])
        for row in report.get(section, []):
            lines.append(f"- **{row['id']} {row['name']}** ({row['owner']}; {row['severity']}): {row['description']}")
        lines.append("")
    lines.extend(["## Evidence References", ""])
    lines.extend(f"- {ref['reference']}" for ref in report.get("evidence_references", []))
    if not report.get("evidence_references"):
        lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_operational_dependency_map_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for section in ("dependency_groups", "owner_handoffs", "external_systems", "risk_links", "checkpoint_links"):
        for row in report.get(section, []):
            writer.writerow({"section": section, "item_id": row["id"], "name": row["name"], "owner": row["owner"], "dependency": row["dependency"], "severity": row["severity"], "description": row["description"], "evidence_refs": json.dumps(row["evidence_refs"])})
    return output.getvalue()


def _context(brief: dict[str, Any], ideas: list[dict[str, Any]]) -> dict[str, Any]:
    risks = _dedupe([*_list(brief.get("risks")), *[risk for idea in ideas for risk in _list(idea.get("domain_risks"))]])
    stack = _first(brief.get("tech_approach"), *[idea.get("tech_approach") for idea in ideas], *[idea.get("suggested_stack") for idea in ideas]) or "implementation stack to confirm"
    return {
        "buyer": _first(brief.get("buyer"), *[idea.get("buyer") for idea in ideas]) or "launch sponsor",
        "workflow_context": _first(brief.get("workflow_context"), *[idea.get("workflow_context") for idea in ideas]) or "primary workflow",
        "support_context": _first(brief.get("support_context"), *[idea.get("support_context") for idea in ideas]) or "support handoff",
        "implementation_owner": _first(brief.get("implementation_owner")) or "Engineering lead",
        "support_owner": _first(brief.get("support_owner")) or "Support owner",
        "risk_owner": "Security/legal owner" if any("security" in risk.lower() or "privacy" in risk.lower() for risk in risks) else "Risk owner",
        "stack": stack,
        "external_systems": _systems(stack),
        "risks": risks,
    }


def _source_ideas(store: Any, brief: dict[str, Any]) -> list[dict[str, Any]]:
    ids = _list(brief.get("source_idea_ids"))
    if brief.get("lead_idea_id") and brief["lead_idea_id"] not in ids:
        ids.insert(0, brief["lead_idea_id"])
    ideas = []
    for idea_id in ids:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append({"id": idea_id, "missing": True})
            continue
        data = unit.model_dump(mode="json") if hasattr(unit, "model_dump") else dict(getattr(unit, "__dict__", {}))
        data["id"] = data.get("id") or idea_id
        ideas.append(data)
    return ideas


def _item(item_id: str, name: str, owner: str, dependency: str, severity: str, description: str, evidence_refs: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "dependency": dependency, "severity": severity, "description": description, "evidence_refs": evidence_refs}


def _evidence(brief: dict[str, Any], ideas: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs = [{"type": "design_brief_field", "reference": f"design_brief.{field}"} for field in ("buyer", "workflow_context", "risks", "tech_approach") if brief.get(field)]
    refs.extend({"type": "source_idea", "reference": f"idea:{idea['id']}"} for idea in ideas)
    return refs


def _systems(text: Any) -> list[str]:
    haystack = _first(text).lower()
    known = ("Slack", "Salesforce", "Stripe", "OpenAI", "GitHub", "Datadog", "HubSpot", "Twilio", "Postgres")
    return [name for name in known if name.lower() in haystack]


def _first(*values: Any) -> str:
    for value in values:
        if isinstance(value, dict):
            text = ", ".join(f"{key}={value[key]}" for key in sorted(value) if value[key])
        elif isinstance(value, (list, tuple, set)):
            text = ", ".join(str(item) for item in value if str(item).strip())
        else:
            text = str(value).strip() if value is not None else ""
        if text:
            return " ".join(text.split())
    return ""


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, (list, tuple, set)) else [str(value)]


def _dedupe(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
