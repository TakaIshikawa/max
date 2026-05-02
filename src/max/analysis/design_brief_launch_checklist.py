"""Deterministic launch checklist export for persisted design briefs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.launch_checklist.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "kind",
    "design_brief_id",
    "design_brief_title",
    "section_id",
    "section_title",
    "section_owner_role",
    "item_id",
    "task",
    "status",
    "owner",
    "required",
    "rationale",
    "exit_criteria",
    "source_idea_ids",
    "source_fields",
)


def build_design_brief_launch_checklist(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a launch readiness checklist from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    sections = _sections(design_brief, source_ideas, lead_idea, source_idea_ids)
    checklist_items = _flatten_items(sections)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.launch_checklist",
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
            "title": design_brief["title"],
            "target_user": _first_text(
                design_brief.get("specific_user"),
                lead_idea and lead_idea.get("specific_user"),
                lead_idea and lead_idea.get("target_users"),
                "TBD user",
            ),
            "buyer": _first_text(
                design_brief.get("buyer"),
                lead_idea and lead_idea.get("buyer"),
                "TBD buyer",
            ),
            "workflow_context": _first_text(
                design_brief.get("workflow_context"),
                lead_idea and lead_idea.get("workflow_context"),
                "target workflow",
            ),
            "launch_gate": _launch_gate(design_brief),
            "section_count": len(sections),
            "item_count": len(checklist_items),
            "source_idea_count": len(source_idea_ids),
        },
        "sections": sections,
        "checklist_items": checklist_items,
        "source_ideas": source_ideas,
    }


def render_design_brief_launch_checklist(checklist: dict[str, Any], fmt: str = "json") -> str:
    """Render the design brief launch checklist as JSON, CSV, or Markdown."""
    if fmt == "json":
        return json.dumps(checklist, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(checklist)
    if fmt != "markdown":
        raise ValueError(f"Unsupported launch checklist format: {fmt}")

    brief = checklist["design_brief"]
    summary = checklist["summary"]
    lines = [
        f"# Launch Checklist: {brief['title']}",
        "",
        f"Schema: `{checklist['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Launch gate: {summary['launch_gate']}",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
    ]

    for section in checklist["sections"]:
        lines.extend([f"## {section['title']}", "", section["description"], ""])
        lines.extend(
            [
                f"- Owner role: {section['owner_role']}",
                f"- Exit criteria: {section['exit_criteria']}",
                "",
            ]
        )
        for item in section["items"]:
            sources = ", ".join(item["source_idea_ids"]) or "design brief"
            fields = ", ".join(item["source_fields"]) or "design brief"
            lines.extend(
                [
                    f"### {item['id']}: {item['task']}",
                    "",
                    f"- Status: {item['status']}",
                    f"- Owner: {item['owner']}",
                    f"- Required: {item['required']}",
                    f"- Rationale: {item['rationale']}",
                    f"- Exit criteria: {item['exit_criteria']}",
                    f"- Source ideas: {sources}",
                    f"- Source fields: {fields}",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def launch_checklist_filename(design_brief: dict[str, Any], fmt: str = "markdown") -> str:
    """Return a stable filename for a launch checklist export."""
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    brief_id = _filename_part(str(design_brief.get("id") or "design-brief"))
    return f"{brief_id}-launch-checklist.{extension}"


def _render_csv(checklist: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for item in checklist.get("checklist_items", []):
        writer.writerow(_csv_row(checklist, item))
    return output.getvalue()


def _csv_row(checklist: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    brief = checklist["design_brief"]
    return {
        "schema_version": str(checklist["schema_version"]),
        "kind": str(checklist["kind"]),
        "design_brief_id": str(brief["id"]),
        "design_brief_title": str(brief["title"]),
        "section_id": str(item.get("section_id", "")),
        "section_title": str(item.get("section_title", "")),
        "section_owner_role": str(item.get("section_owner_role", "")),
        "item_id": str(item.get("id", "")),
        "task": str(item.get("task", "")),
        "status": str(item.get("status", "")),
        "owner": str(item.get("owner", "")),
        "required": _csv_bool(item.get("required")),
        "rationale": str(item.get("rationale", "")),
        "exit_criteria": str(item.get("exit_criteria", "")),
        "source_idea_ids": _csv_list(item.get("source_idea_ids", [])),
        "source_fields": _csv_list(item.get("source_fields", [])),
    }


def _sections(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
    all_source_ids: list[str],
) -> list[dict[str, Any]]:
    item_number = 1

    def items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal item_number
        rendered = []
        for raw in raw_items:
            rendered.append({"id": f"DBLC{item_number}", "status": "pending", **raw})
            item_number += 1
        return rendered

    return [
        {
            "id": "readiness",
            "title": "Readiness",
            "description": "Confirm the persisted brief is ready to enter execution.",
            "owner_role": "Product lead",
            "exit_criteria": "Scope, owners, risks, and launch decision gates are accepted.",
            "items": items(_readiness_items(design_brief, source_ideas, lead_idea, all_source_ids)),
        },
        {
            "id": "instrumentation",
            "title": "Instrumentation",
            "description": "Prepare the minimum measurement surface for launch learning.",
            "owner_role": "Engineering lead",
            "exit_criteria": "Launch telemetry, adoption metrics, and evidence capture paths exist.",
            "items": items(_instrumentation_items(design_brief, lead_idea, all_source_ids)),
        },
        {
            "id": "validation",
            "title": "Validation",
            "description": "Run the planned validation before broad rollout.",
            "owner_role": "Research lead",
            "exit_criteria": "Validation produces an explicit build, revise, or stop decision.",
            "items": items(_validation_items(design_brief, source_ideas, all_source_ids)),
        },
        {
            "id": "rollout",
            "title": "Rollout",
            "description": "Coordinate the first controlled release and recovery path.",
            "owner_role": "Go-to-market lead",
            "exit_criteria": "First launch cohort, communications, and rollback triggers are approved.",
            "items": items(_rollout_items(design_brief, lead_idea, all_source_ids)),
        },
        {
            "id": "follow_up",
            "title": "Follow-up",
            "description": "Close the post-launch loop with evidence and next decisions.",
            "owner_role": "Product lead",
            "exit_criteria": "Post-launch evidence is reviewed and the next decision is recorded.",
            "items": items(_follow_up_items(design_brief, source_ideas, all_source_ids)),
        },
    ]


def _readiness_items(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
    all_source_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        _item(
            task="Confirm launch scope from the persisted MVP scope.",
            rationale="; ".join(_string_list(design_brief.get("mvp_scope")))
            or _first_text(design_brief.get("merged_product_concept"), "No MVP scope is captured yet."),
            owner="product_owner",
            exit_criteria="MVP scope and explicit non-goals are approved for execution.",
            source_idea_ids=_source_ids_for_fields(
                source_ideas,
                ("solution", "tech_approach"),
                all_source_ids,
            ),
            source_fields=["mvp_scope", "merged_product_concept"],
        ),
        _item(
            task="Assign launch owners for product, engineering, validation, and support.",
            rationale=_first_text(
                design_brief.get("workflow_context"),
                lead_idea and lead_idea.get("workflow_context"),
                "Launch needs accountable handoff owners.",
            ),
            owner="product_owner",
            exit_criteria="Named owners and backup contacts are recorded in the launch handoff.",
            source_idea_ids=_source_ids_for_lead(lead_idea, all_source_ids),
            source_fields=["buyer", "specific_user", "workflow_context"],
        ),
        _item(
            task="Resolve or explicitly accept launch-blocking risks.",
            rationale="; ".join(_risk_texts(design_brief, source_ideas)) or "No launch risks are captured yet.",
            owner="product_owner",
            exit_criteria="Each high-priority risk has mitigation, owner, and accept or defer decision.",
            source_idea_ids=_source_ids_for_risks(source_ideas, all_source_ids),
            source_fields=["risks", "domain_risks"],
        ),
    ]


def _instrumentation_items(
    design_brief: dict[str, Any],
    lead_idea: dict[str, Any] | None,
    all_source_ids: list[str],
) -> list[dict[str, Any]]:
    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
        "primary workflow",
    )
    return [
        _item(
            task="Define activation, completion, failure, and latency events for the launch workflow.",
            rationale=workflow,
            owner="engineering_owner",
            exit_criteria="Event names, properties, and review dashboard location are documented.",
            source_idea_ids=_source_ids_for_lead(lead_idea, all_source_ids),
            source_fields=["workflow_context"],
        ),
        _item(
            task="Create an adoption metric tied to the value proposition.",
            rationale=_first_text(
                lead_idea and lead_idea.get("value_proposition"),
                design_brief.get("merged_product_concept"),
                "Launch needs a measurable adoption signal.",
            ),
            owner="product_owner",
            exit_criteria="Metric definition includes numerator, denominator, target, and review cadence.",
            source_idea_ids=_source_ids_for_lead(lead_idea, all_source_ids),
            source_fields=["value_proposition", "merged_product_concept"],
        ),
        _item(
            task="Prepare evidence capture for support requests, defects, and user feedback.",
            rationale="Follow-up decisions should be traceable to launch evidence.",
            owner="support_owner",
            exit_criteria="Feedback, defect, and support channels are linked from the launch handoff.",
            source_idea_ids=all_source_ids,
            source_fields=["source_idea_ids"],
        ),
    ]


def _validation_items(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    all_source_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        _item(
            task="Run the persisted validation plan before expanding launch scope.",
            rationale=_first_text(design_brief.get("validation_plan"), "No validation plan is captured yet."),
            owner="research_owner",
            exit_criteria="Validation notes include participants or fixtures, observed results, and decision.",
            source_idea_ids=all_source_ids,
            source_fields=["validation_plan"],
        ),
        _item(
            task="Validate the target user and buyer path for the launch cohort.",
            rationale=_first_text(
                design_brief.get("specific_user"),
                design_brief.get("buyer"),
                "Target user and buyer are not fully specified.",
            ),
            owner="research_owner",
            exit_criteria="Launch cohort matches the named user, buyer, and workflow assumptions.",
            source_idea_ids=_source_ids_for_fields(
                source_ideas,
                ("specific_user", "buyer"),
                all_source_ids,
            ),
            source_fields=["specific_user", "buyer"],
        ),
        _item(
            task="Convert validation gaps into launch non-goals or follow-up tasks.",
            rationale="Validation should prevent silent scope expansion.",
            owner="product_owner",
            exit_criteria="Known gaps are captured as non-goals, blockers, or dated follow-up work.",
            source_idea_ids=all_source_ids,
            source_fields=["mvp_scope", "validation_plan", "risks"],
        ),
    ]


def _rollout_items(
    design_brief: dict[str, Any],
    lead_idea: dict[str, Any] | None,
    all_source_ids: list[str],
) -> list[dict[str, Any]]:
    return [
        _item(
            task="Select the first controlled launch cohort.",
            rationale=_first_text(
                lead_idea and lead_idea.get("first_10_customers"),
                design_brief.get("specific_user"),
                "First launch cohort is not specified yet.",
            ),
            owner="go_to_market_owner",
            exit_criteria="Cohort list includes user segment, contact path, and inclusion criteria.",
            source_idea_ids=_source_ids_for_lead(lead_idea, all_source_ids),
            source_fields=["first_10_customers", "specific_user"],
        ),
        _item(
            task="Publish launch notes covering setup, expected behavior, and known limits.",
            rationale=_first_text(
                design_brief.get("merged_product_concept"),
                lead_idea and lead_idea.get("one_liner"),
                "Launch needs a clear handoff artifact.",
            ),
            owner="product_owner",
            exit_criteria="Launch notes are reviewed by product, engineering, and support owners.",
            source_idea_ids=all_source_ids,
            source_fields=["merged_product_concept", "mvp_scope", "risks"],
        ),
        _item(
            task="Define rollback, pause, or escalation triggers for the first release.",
            rationale="A controlled launch needs a fast recovery path.",
            owner="engineering_owner",
            exit_criteria="Rollback trigger, owner, action, and communication path are documented.",
            source_idea_ids=all_source_ids,
            source_fields=["risks", "domain_risks"],
        ),
    ]


def _follow_up_items(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    all_source_ids: list[str],
) -> list[dict[str, Any]]:
    milestones = _string_list(design_brief.get("first_milestones"))
    return [
        _item(
            task="Review launch evidence against success metrics and first milestones.",
            rationale="; ".join(milestones) or "No first milestones are captured yet.",
            owner="product_owner",
            exit_criteria="Launch review records met, missed, and inconclusive launch outcomes.",
            source_idea_ids=all_source_ids,
            source_fields=["first_milestones"],
        ),
        _item(
            task="Update source idea status and design brief status after launch review.",
            rationale="Preserve portfolio traceability from design brief back to source ideas.",
            owner="product_owner",
            exit_criteria="Source ideas and the design brief reflect publish, revise, archive, or reject status.",
            source_idea_ids=all_source_ids,
            source_fields=["design_status", "source_idea_ids"],
        ),
        _item(
            task="Create the next iteration plan from unresolved risks and feedback.",
            rationale="; ".join(_risk_texts(design_brief, source_ideas)) or "Use launch feedback for iteration.",
            owner="product_owner",
            exit_criteria="Next iteration has owner, priority, target date, and evidence link.",
            source_idea_ids=_source_ids_for_risks(source_ideas, all_source_ids),
            source_fields=["risks", "domain_risks", "validation_plan"],
        ),
    ]


def _item(
    *,
    task: str,
    rationale: str,
    owner: str,
    exit_criteria: str,
    source_idea_ids: list[str],
    source_fields: list[str],
) -> dict[str, Any]:
    return {
        "task": task,
        "rationale": _compact(rationale),
        "owner": owner,
        "required": True,
        "exit_criteria": exit_criteria,
        "source_idea_ids": list(dict.fromkeys(source_idea_ids)),
        "source_fields": source_fields,
    }


def _flatten_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened = []
    for section in sections:
        for item in section["items"]:
            flattened.append(
                {
                    **item,
                    "section_id": section["id"],
                    "section_title": section["title"],
                    "section_owner_role": section["owner_role"],
                }
            )
    return flattened


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


def _launch_gate(design_brief: dict[str, Any]) -> str:
    status = design_brief.get("design_status")
    readiness = float(design_brief.get("readiness_score") or 0.0)
    if status in {"approved", "published"} and readiness >= 75:
        return "ready_for_launch_review"
    if status in {"approved", "published"}:
        return "approved_needs_readiness_review"
    return "needs_design_approval"


def _source_ids_for_lead(
    lead_idea: dict[str, Any] | None,
    fallback: list[str],
) -> list[str]:
    if lead_idea and not lead_idea.get("missing"):
        return [lead_idea["id"]]
    return fallback


def _source_ids_for_fields(
    source_ideas: list[dict[str, Any]],
    fields: tuple[str, ...],
    fallback: list[str],
) -> list[str]:
    ids = [
        idea["id"]
        for idea in source_ideas
        if not idea.get("missing") and any(_compact(idea.get(field)) for field in fields)
    ]
    return list(dict.fromkeys(ids)) or fallback


def _source_ids_for_risks(
    source_ideas: list[dict[str, Any]],
    fallback: list[str],
) -> list[str]:
    return _source_ids_for_fields(source_ideas, ("domain_risks", "risks"), fallback)


def _risk_texts(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    risks = _string_list(design_brief.get("risks"))
    for idea in source_ideas:
        risks.extend(_string_list(idea.get("domain_risks")))
    return _dedupe_strings(risks)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _first_text(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(_compact(value) for value in values if _compact(value)))


def _csv_list(values: Any) -> str:
    return ";".join(_string_list(values))


def _csv_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value) if value is not None else ""


def _filename_part(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in cleaned.split("-") if part)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
