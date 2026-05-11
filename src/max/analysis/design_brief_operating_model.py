"""Deterministic operating model analysis for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.operating_model.v1"
KIND = "max.design_brief.operating_model"

CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "name",
    "owner",
    "cadence",
    "trigger",
    "decision",
    "approver",
    "checkpoint",
    "metric",
    "target",
    "description",
    "evidence_refs",
    "source_idea_ids",
)


def build_design_brief_operating_model(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a deterministic operating model from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = _string_list(design_brief.get("source_idea_ids"))

    context = _operating_context(design_brief, source_ideas)
    operating_rituals = _operating_rituals(context, source_idea_ids)
    decision_rights = _decision_rights(context, source_idea_ids)
    escalation_paths = _escalation_paths(context, source_idea_ids)
    handoff_checkpoints = _handoff_checkpoints(context, source_idea_ids)
    operating_metrics = _operating_metrics(context, source_idea_ids)
    evidence_references = _evidence_references(design_brief, source_ideas)

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
            "title": design_brief["title"],
            "operating_owner": context["operating_owner"],
            "buyer": context["buyer"],
            "primary_user": context["primary_user"],
            "workflow_context": context["workflow_context"],
            "implementation_owner": context["implementation_owner"],
            "support_owner": context["support_owner"],
            "risk_owner": context["risk_owner"],
            "operating_posture": _operating_posture(design_brief, context),
            "ritual_count": len(operating_rituals),
            "decision_right_count": len(decision_rights),
            "escalation_path_count": len(escalation_paths),
            "handoff_checkpoint_count": len(handoff_checkpoints),
            "operating_metric_count": len(operating_metrics),
            "fallbacks_used": context["fallbacks_used"],
        },
        "operating_rituals": operating_rituals,
        "decision_rights": decision_rights,
        "escalation_paths": escalation_paths,
        "handoff_checkpoints": handoff_checkpoints,
        "operating_metrics": operating_metrics,
        "evidence_references": evidence_references,
    }


def render_design_brief_operating_model(report: dict[str, Any], fmt: str = "markdown") -> str:
    """Render an operating model as Markdown, deterministic JSON, or parseable CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_design_brief_operating_model_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported operating model format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Operating Model: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Operating owner: {summary['operating_owner']}",
        f"Buyer: {summary['buyer']}",
        f"Primary user: {summary['primary_user']}",
        f"Workflow: {summary['workflow_context']}",
        f"Posture: {summary['operating_posture']}",
        "",
        "## Operating Rituals",
        "",
    ]
    for ritual in report["operating_rituals"]:
        lines.append(
            f"- **{ritual['id']} {ritual['name']}** ({ritual['cadence']}; owner: {ritual['owner']}): {ritual['purpose']}"
        )

    lines.extend(["", "## Decision Rights", ""])
    for decision in report["decision_rights"]:
        lines.append(
            f"- **{decision['id']} {decision['decision']}**: {decision['approver']} approves; {decision['owner']} prepares."
        )

    lines.extend(["", "## Escalation Paths", ""])
    for path in report["escalation_paths"]:
        lines.append(
            f"- **{path['id']} {path['trigger']}** ({path['severity']}): {path['route']} within {path['response_time']}."
        )

    lines.extend(["", "## Handoff Checkpoints", ""])
    for checkpoint in report["handoff_checkpoints"]:
        lines.append(
            f"- **{checkpoint['id']} {checkpoint['checkpoint']}** ({checkpoint['owner']}): {checkpoint['exit_criteria']}"
        )

    lines.extend(["", "## Operating Metrics", ""])
    for metric in report["operating_metrics"]:
        lines.append(
            f"- **{metric['id']} {metric['metric']}** ({metric['owner']}): target {metric['target']}; review {metric['review_cadence']}."
        )

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for item in report["evidence_references"]:
            lines.append(f"- {item['reference']}")
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_operating_model_csv(report: dict[str, Any]) -> str:
    """Render one CSV row per operating model item."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _operating_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    fallbacks: list[str] = []
    buyer = _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"))
    primary_user = _first_text(
        design_brief.get("specific_user"),
        _field_values(source_ideas, "specific_user"),
    )
    workflow = _first_text(
        design_brief.get("workflow_context"),
        _field_values(source_ideas, "workflow_context"),
    )
    validation = _first_text(
        design_brief.get("validation_plan"),
        _field_values(source_ideas, "validation_plan"),
    )
    concept = _first_text(
        design_brief.get("merged_product_concept"),
        design_brief.get("synthesis_rationale"),
        _field_values(source_ideas, "solution"),
    )
    risks = _dedupe([*_string_list(design_brief.get("risks")), *_field_values(source_ideas, "domain_risks")])
    milestones = _string_list(design_brief.get("first_milestones"))
    mvp_scope = _string_list(design_brief.get("mvp_scope"))
    stack = _first_text(design_brief.get("tech_approach"), _joined_fields(source_ideas, ("tech_approach", "suggested_stack")))

    if not buyer:
        buyer = "launch sponsor"
        fallbacks.append("buyer")
    if not primary_user:
        primary_user = "primary workflow owner"
        fallbacks.append("specific_user")
    if not workflow:
        workflow = "primary workflow"
        fallbacks.append("workflow_context")
    if not validation:
        validation = "Confirm pilot success criteria with the launch sponsor."
        fallbacks.append("validation_plan")
    if not concept:
        concept = f"Operationalize {design_brief['title']} for the approved workflow."
        fallbacks.append("product_concept")
    if not milestones:
        milestones = ["Complete pilot handoff", "Review launch readiness"]
        fallbacks.append("first_milestones")
    if not mvp_scope:
        mvp_scope = ["Approved brief scope"]
        fallbacks.append("mvp_scope")
    if not stack:
        stack = "implementation stack to be confirmed"
        fallbacks.append("tech_approach")

    risk_text = " ".join(risks).lower()
    risk_owner = (
        "Security/legal owner"
        if any(term in risk_text for term in ("security", "privacy", "legal", "compliance"))
        else "Risk owner"
    )
    return {
        "buyer": buyer,
        "primary_user": primary_user,
        "workflow_context": workflow,
        "validation_plan": validation,
        "product_concept": concept,
        "risks": risks,
        "first_milestones": milestones,
        "mvp_scope": mvp_scope,
        "stack": stack,
        "operating_owner": "Product lead",
        "implementation_owner": "Engineering lead",
        "support_owner": "Support owner",
        "risk_owner": risk_owner,
        "fallbacks_used": fallbacks,
    }


def _operating_rituals(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "OMR1",
            "name": "Operating review",
            "cadence": "weekly during pilot",
            "owner": context["operating_owner"],
            "participants": [context["buyer"], context["primary_user"], context["implementation_owner"]],
            "purpose": f"Review {context['workflow_context']} progress, open decisions, and metric movement.",
            "evidence_refs": ["design_brief.workflow_context", "design_brief.validation_plan"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OMR2",
            "name": "Delivery standup",
            "cadence": "twice weekly until launch readiness",
            "owner": context["implementation_owner"],
            "participants": [context["operating_owner"], context["support_owner"]],
            "purpose": f"Sequence scope items and unblock {context['stack']}.",
            "evidence_refs": ["design_brief.mvp_scope", "source_ideas.tech_approach"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OMR3",
            "name": "Pilot support review",
            "cadence": "weekly after first pilot user",
            "owner": context["support_owner"],
            "participants": [context["primary_user"], context["risk_owner"]],
            "purpose": "Review support load, workflow interruptions, and escalation patterns.",
            "evidence_refs": ["design_brief.risks", "source_ideas.domain_risks"],
            "source_idea_ids": source_idea_ids,
        },
    ]


def _decision_rights(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "OMD1",
            "decision": "Pilot entry",
            "owner": context["operating_owner"],
            "approver": context["buyer"],
            "inputs": [context["validation_plan"], context["first_milestones"][0]],
            "default_rule": "Enter pilot only when validation owner and support owner confirm readiness.",
            "evidence_refs": ["design_brief.validation_plan", "design_brief.first_milestones"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OMD2",
            "decision": "Scope change",
            "owner": context["implementation_owner"],
            "approver": context["operating_owner"],
            "inputs": context["mvp_scope"],
            "default_rule": "Defer scope that does not protect the approved workflow outcome.",
            "evidence_refs": ["design_brief.mvp_scope", "design_brief.merged_product_concept"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OMD3",
            "decision": "Launch expansion",
            "owner": context["operating_owner"],
            "approver": context["buyer"],
            "inputs": [context["validation_plan"], "operating metrics trend"],
            "default_rule": "Expand only after pilot metrics and unresolved escalations are reviewed.",
            "evidence_refs": ["design_brief.validation_plan", "design_brief.readiness_score"],
            "source_idea_ids": source_idea_ids,
        },
    ]


def _escalation_paths(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    top_risk = context["risks"][0] if context["risks"] else "No explicit risk captured; escalate unknown blockers."
    return [
        {
            "id": "OME1",
            "trigger": "Pilot workflow blocked",
            "severity": "high",
            "route": f"{context['primary_user']} -> {context['operating_owner']} -> {context['buyer']}",
            "response_time": "1 business day",
            "action": "Decide whether to pause pilot usage or narrow scope.",
            "evidence_refs": ["design_brief.workflow_context", "design_brief.buyer"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OME2",
            "trigger": "Implementation dependency at risk",
            "severity": "medium",
            "route": f"{context['implementation_owner']} -> {context['operating_owner']}",
            "response_time": "2 business days",
            "action": "Re-sequence milestone ownership and update the operating review.",
            "evidence_refs": ["design_brief.first_milestones", "source_ideas.tech_approach"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OME3",
            "trigger": top_risk,
            "severity": "high" if context["risks"] else "medium",
            "route": f"{context['risk_owner']} -> {context['operating_owner']} -> {context['buyer']}",
            "response_time": "same business day for high-severity issues",
            "action": "Document mitigation, owner, and launch impact before expansion.",
            "evidence_refs": ["design_brief.risks", "source_ideas.domain_risks"],
            "source_idea_ids": source_idea_ids,
        },
    ]


def _handoff_checkpoints(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "OMH1",
            "checkpoint": "Brief to delivery",
            "owner": context["operating_owner"],
            "receiver": context["implementation_owner"],
            "exit_criteria": f"Scope, milestones, and {context['workflow_context']} acceptance path are confirmed.",
            "evidence_refs": ["design_brief.mvp_scope", "design_brief.first_milestones"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OMH2",
            "checkpoint": "Delivery to pilot",
            "owner": context["implementation_owner"],
            "receiver": context["primary_user"],
            "exit_criteria": f"Pilot users can complete {context['workflow_context']} and support owner is briefed.",
            "evidence_refs": ["design_brief.workflow_context", "design_brief.validation_plan"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OMH3",
            "checkpoint": "Pilot to launch decision",
            "owner": context["operating_owner"],
            "receiver": context["buyer"],
            "exit_criteria": "Validation evidence, escalations, and operating metrics are reviewed in one decision record.",
            "evidence_refs": ["design_brief.validation_plan", "design_brief.risks"],
            "source_idea_ids": source_idea_ids,
        },
    ]


def _operating_metrics(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "OMM1",
            "metric": "Pilot workflow completion",
            "owner": context["primary_user"],
            "target": "80% of pilot attempts complete without owner intervention",
            "review_cadence": "weekly",
            "source": context["validation_plan"],
            "evidence_refs": ["design_brief.validation_plan", "design_brief.workflow_context"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OMM2",
            "metric": "Decision aging",
            "owner": context["operating_owner"],
            "target": "No launch-blocking decision remains open longer than 5 business days",
            "review_cadence": "weekly",
            "source": "operating review decision log",
            "evidence_refs": ["design_brief.buyer", "design_brief.first_milestones"],
            "source_idea_ids": source_idea_ids,
        },
        {
            "id": "OMM3",
            "metric": "Escalation resolution",
            "owner": context["support_owner"],
            "target": "High-severity pilot escalations have an owner and next action within 1 business day",
            "review_cadence": "weekly",
            "source": "support and risk review",
            "evidence_refs": ["design_brief.risks", "source_ideas.domain_risks"],
            "source_idea_ids": source_idea_ids,
        },
    ]


def _operating_posture(design_brief: dict[str, Any], context: dict[str, Any]) -> str:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if design_brief.get("design_status") != "approved":
        return "planning"
    if readiness >= 80 and not context["fallbacks_used"]:
        return "ready_for_pilot_operations"
    if readiness >= 60:
        return "needs_owner_confirmation"
    return "needs_operating_design"


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section, items in (
        ("operating_rituals", report.get("operating_rituals") or []),
        ("decision_rights", report.get("decision_rights") or []),
        ("escalation_paths", report.get("escalation_paths") or []),
        ("handoff_checkpoints", report.get("handoff_checkpoints") or []),
        ("operating_metrics", report.get("operating_metrics") or []),
    ):
        rows.extend(_csv_row(report, section, item) for item in items)
    return rows


def _csv_row(report: dict[str, Any], section: str, item: dict[str, Any]) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    values = {
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "section": section,
        "item_id": item.get("id"),
        "name": item.get("name") or item.get("decision") or item.get("checkpoint") or item.get("metric") or item.get("trigger"),
        "owner": item.get("owner"),
        "cadence": item.get("cadence") or item.get("review_cadence"),
        "trigger": item.get("trigger"),
        "decision": item.get("decision") or item.get("default_rule"),
        "approver": item.get("approver"),
        "checkpoint": item.get("checkpoint"),
        "metric": item.get("metric"),
        "target": item.get("target"),
        "description": item.get("purpose") or item.get("action") or item.get("exit_criteria") or item.get("source"),
        "evidence_refs": item.get("evidence_refs") or [],
        "source_idea_ids": item.get("source_idea_ids") or [],
    }
    return {column: _csv_cell(values.get(column)) for column in CSV_COLUMNS}


def _evidence_references(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for field in (
        "buyer",
        "specific_user",
        "workflow_context",
        "validation_plan",
        "mvp_scope",
        "first_milestones",
        "risks",
    ):
        if _has_value(design_brief.get(field)):
            references.append({"type": "design_brief_field", "reference": f"design_brief.{field}"})
    for idea in source_ideas:
        if idea.get("missing"):
            references.append({"type": "missing_source_idea", "reference": f"idea:{idea['id']}"})
        else:
            references.append({"type": "source_idea", "reference": f"idea:{idea['id']}"})
    return references


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = list(design_brief.get("sources") or [])
    if not sources:
        lead_id = design_brief.get("lead_idea_id")
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        for rank, idea_id in enumerate(design_brief.get("source_idea_ids") or [], start=1):
            if idea_id != lead_id:
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

    for source in sources:
        idea_id = str(source.get("idea_id") or "")
        if not idea_id or idea_id in seen:
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


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for idea in source_ideas:
        if not idea.get("missing"):
            values.extend(_string_list(idea.get(field)))
    return _dedupe(values)


def _joined_fields(source_ideas: list[dict[str, Any]], fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for field in fields:
        values.extend(_field_values(source_ideas, field))
    return "; ".join(_dedupe(values))


def _first_text(*values: Any) -> str:
    for value in values:
        text = "; ".join(_string_list(value))
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        compact = value.strip()
        return [compact] if compact else []
    if isinstance(value, dict):
        values: list[str] = []
        for key, item in sorted(value.items()):
            text = _csv_scalar(item)
            if text:
                values.append(f"{key}={text}")
        return values
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return values
    compact = str(value).strip()
    return [compact] if compact else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        compact = str(value).strip()
        if compact and compact not in seen:
            seen.add(compact)
            result.append(compact)
    return result


def _has_value(value: Any) -> bool:
    return bool(_string_list(value))


def _csv_cell(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), separators=(",", ":"), sort_keys=True)
    return _csv_scalar(value)


def _csv_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)
