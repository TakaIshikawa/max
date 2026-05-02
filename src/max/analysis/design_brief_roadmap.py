"""Deterministic roadmap generation for persisted design briefs."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.roadmap.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "generated_at",
    "design_brief_id",
    "design_brief_title",
    "design_brief_domain",
    "design_brief_theme",
    "readiness_score",
    "design_status",
    "lead_idea_id",
    "design_brief_source_idea_ids",
    "row_type",
    "phase_order",
    "phase_id",
    "phase_title",
    "phase_goal",
    "milestone_order",
    "milestone_id",
    "milestone_title",
    "owner_role",
    "rationale",
    "dependency_ids",
    "exit_criteria",
    "risk_references",
    "source_idea_ids",
    "source_fields",
)

PHASES: tuple[dict[str, str], ...] = (
    {
        "id": "discovery",
        "title": "Discovery",
        "goal": "Validate the workflow, user, buyer, and highest-risk assumptions before prototyping.",
    },
    {
        "id": "prototype",
        "title": "Prototype",
        "goal": "Build the smallest demonstrable path through the MVP scope.",
    },
    {
        "id": "validation",
        "title": "Validation",
        "goal": "Run the persisted validation plan and convert results into build, revise, or stop decisions.",
    },
    {
        "id": "beta",
        "title": "Beta",
        "goal": "Ship the first milestones to a controlled set of qualified users.",
    },
    {
        "id": "launch",
        "title": "Launch",
        "goal": "Prepare the product, support model, and go-to-market handoff for broader availability.",
    },
)


def build_design_brief_roadmap(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build an actionable phased roadmap from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    all_source_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not all_source_ids:
        all_source_ids = list(design_brief.get("source_idea_ids") or [])

    items = _build_items(design_brief, source_ideas, lead_idea, all_source_ids)
    phase_payloads = []
    for phase in PHASES:
        phase_items = [item for item in items if item["phase"] == phase["id"]]
        phase_payloads.append({**phase, "items": phase_items})

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": all_source_ids,
        },
        "summary": {
            "phase_count": len(phase_payloads),
            "item_count": len(items),
            "source_idea_count": len(all_source_ids),
            "critical_dependency_ids": _critical_dependencies(items),
        },
        "phases": phase_payloads,
        "items": items,
        "source_ideas": source_ideas,
    }


def render_design_brief_roadmap(roadmap: dict[str, Any], fmt: str = "json") -> str:
    """Render a roadmap for MCP consumers."""
    if fmt == "json":
        return json.dumps(roadmap, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(roadmap)
    if fmt != "markdown":
        raise ValueError(f"Unsupported roadmap format: {fmt}")

    brief = roadmap["design_brief"]
    lines = [
        f"# Roadmap: {brief['title']}",
        "",
        f"Schema: `{roadmap['schema_version']}`",
        f"Items: {roadmap['summary']['item_count']}",
        "",
    ]
    for phase in roadmap["phases"]:
        lines.extend([f"## {phase['title']}", "", phase["goal"], ""])
        for item in phase["items"]:
            deps = ", ".join(item["dependency_ids"]) or "none"
            sources = ", ".join(item["source_idea_ids"]) or "design brief"
            lines.extend(
                [
                    f"### {item['id']}: {item['title']}",
                    "",
                    item["rationale"],
                    "",
                    f"- Owner role: {item['owner_role']}",
                    f"- Dependencies: {deps}",
                    f"- Source ideas: {sources}",
                    f"- Exit criteria: {item['exit_criteria']}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(roadmap: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(roadmap):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(roadmap: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    phases = [phase for phase in roadmap.get("phases", []) if isinstance(phase, dict)]
    if not phases:
        return rows

    items_by_phase = _items_by_phase(roadmap)
    for phase_order, phase in enumerate(phases, start=1):
        phase_items = _phase_items(phase, items_by_phase)
        rows.append(_csv_row(roadmap, phase, phase_order, row_type="phase", items=phase_items))
        for milestone_order, item in enumerate(phase_items, start=1):
            rows.append(
                _csv_row(
                    roadmap,
                    phase,
                    phase_order,
                    row_type="milestone",
                    item=item,
                    milestone_order=milestone_order,
                )
            )
    return rows


def _items_by_phase(roadmap: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    items_by_phase: dict[str, list[dict[str, Any]]] = {}
    for item in roadmap.get("items", []) or []:
        if isinstance(item, dict):
            items_by_phase.setdefault(str(item.get("phase", "")), []).append(item)
    return items_by_phase


def _phase_items(phase: dict[str, Any], items_by_phase: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    phase_items = [item for item in phase.get("items", []) or [] if isinstance(item, dict)]
    if phase_items:
        return phase_items
    return items_by_phase.get(str(phase.get("id", "")), [])


def _csv_row(
    roadmap: dict[str, Any],
    phase: dict[str, Any],
    phase_order: int,
    *,
    row_type: str,
    item: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
    milestone_order: int | None = None,
) -> dict[str, str]:
    brief = roadmap.get("design_brief", {})
    values: dict[str, Any] = {
        "schema_version": roadmap.get("schema_version", ""),
        "generated_at": (roadmap.get("source") or {}).get("generated_at", ""),
        "design_brief_id": brief.get("id", ""),
        "design_brief_title": brief.get("title", ""),
        "design_brief_domain": brief.get("domain", ""),
        "design_brief_theme": brief.get("theme", ""),
        "readiness_score": brief.get("readiness_score", ""),
        "design_status": brief.get("design_status", ""),
        "lead_idea_id": brief.get("lead_idea_id", ""),
        "design_brief_source_idea_ids": brief.get("source_idea_ids", []),
        "row_type": row_type,
        "phase_order": phase_order,
        "phase_id": phase.get("id", ""),
        "phase_title": phase.get("title", ""),
        "phase_goal": phase.get("goal", ""),
        "milestone_order": milestone_order or "",
        "milestone_id": item.get("id", "") if item else "",
        "milestone_title": item.get("title", "") if item else "",
        "owner_role": item.get("owner_role", "") if item else "",
        "rationale": item.get("rationale", "") if item else "",
        "dependency_ids": item.get("dependency_ids", []) if item else [],
        "exit_criteria": item.get("exit_criteria", "") if item else "",
        "risk_references": _risk_references(item=item, items=items),
        "source_idea_ids": item.get("source_idea_ids", []) if item else _phase_source_idea_ids(items or []),
        "source_fields": item.get("source_fields", []) if item else _phase_source_fields(items or []),
    }
    return {column: _csv_cell(values.get(column)) for column in CSV_COLUMNS}


def _risk_references(
    *,
    item: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
) -> list[str]:
    if item is not None:
        return _item_risk_references(item)

    risks: list[str] = []
    for phase_item in items or []:
        risks.extend(_item_risk_references(phase_item))
    return _dedupe_strings(risks)


def _item_risk_references(item: dict[str, Any]) -> list[str]:
    source_fields = set(_string_list(item.get("source_fields")))
    if "risks" in source_fields or "domain_risks" in source_fields:
        return _string_list(item.get("rationale"))
    return []


def _phase_source_idea_ids(items: list[dict[str, Any]]) -> list[str]:
    source_ids: list[str] = []
    for item in items:
        source_ids.extend(_string_list(item.get("source_idea_ids")))
    return list(dict.fromkeys(source_ids))


def _phase_source_fields(items: list[dict[str, Any]]) -> list[str]:
    source_fields: list[str] = []
    for item in items:
        source_fields.extend(_string_list(item.get("source_fields")))
    return list(dict.fromkeys(source_fields))


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return json.dumps([_csv_nested(item) for item in value], sort_keys=True, separators=(",", ":"))
    if isinstance(value, dict):
        return json.dumps(_csv_nested(value), sort_keys=True, separators=(",", ":"))
    return str(value)


def _csv_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _csv_nested(nested) for key, nested in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_csv_nested(item) for item in value]
    if value is None:
        return ""
    return str(value)


def _build_items(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
    all_source_ids: list[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    discovery_base = _add_item(
        items,
        phase="discovery",
        title="Confirm target workflow and buyer path",
        rationale=_first_text(
            design_brief.get("workflow_context"),
            lead_idea and lead_idea.get("workflow_context"),
            design_brief.get("why_this_now"),
            "The brief needs a confirmed workflow and buyer path before implementation scope is locked.",
        ),
        owner_role="Product lead",
        dependency_ids=[],
        exit_criteria="Primary user, buyer, workflow trigger, current workaround, and decision path are documented from discovery evidence.",
        source_idea_ids=_source_ids_for_lead(lead_idea, all_source_ids),
        source_fields=["specific_user", "buyer", "workflow_context", "why_this_now"],
    )

    risk_item_ids: list[str] = []
    for risk in _dedupe_strings([*design_brief.get("risks", []), *_source_risks(source_ideas)])[:3]:
        risk_item_ids.append(
            _add_item(
                items,
                phase="discovery",
                title=f"Probe risk: {_short_title(risk)}",
                rationale=risk,
                owner_role=_owner_for_risk(risk),
                dependency_ids=[discovery_base],
                exit_criteria="Risk has an explicit mitigation, owner, and kill or proceed threshold.",
                source_idea_ids=_source_ids_for_risk(risk, source_ideas, all_source_ids),
                source_fields=["risks", "domain_risks"],
            )
        )

    scope_item_ids: list[str] = []
    for scope in _string_list(design_brief.get("mvp_scope"))[:4]:
        scope_item_ids.append(
            _add_item(
                items,
                phase="prototype",
                title=f"Prototype {scope}",
                rationale=_scope_rationale(scope, source_ideas, design_brief),
                owner_role=_owner_for_scope(scope),
                dependency_ids=[discovery_base, *risk_item_ids[:1]],
                exit_criteria=f"{scope} is demonstrable in the target workflow with known gaps captured.",
                source_idea_ids=_source_ids_for_text(scope, source_ideas, all_source_ids),
                source_fields=["mvp_scope", "solution", "tech_approach", "suggested_stack"],
            )
        )
    if not scope_item_ids:
        scope_item_ids.append(
            _add_item(
                items,
                phase="prototype",
                title="Prototype core product concept",
                rationale=_first_text(
                    design_brief.get("merged_product_concept"),
                    lead_idea and lead_idea.get("solution"),
                    "Build the smallest artifact that makes the concept concrete.",
                ),
                owner_role="Prototype engineer",
                dependency_ids=[discovery_base],
                exit_criteria="A clickable or working prototype demonstrates the core workflow end to end.",
                source_idea_ids=_source_ids_for_lead(lead_idea, all_source_ids),
                source_fields=["merged_product_concept", "solution"],
            )
        )

    validation_item = _add_item(
        items,
        phase="validation",
        title="Run validation plan",
        rationale=_first_text(
            design_brief.get("validation_plan"),
            lead_idea and lead_idea.get("validation_plan"),
            "Validation should produce decision evidence before beta scope expands.",
        ),
        owner_role="Research lead",
        dependency_ids=scope_item_ids,
        exit_criteria="Validation results are compared against success metrics and the roadmap is updated with a build, revise, or stop decision.",
        source_idea_ids=all_source_ids,
        source_fields=["validation_plan"],
    )

    milestone_item_ids: list[str] = []
    for milestone in _string_list(design_brief.get("first_milestones"))[:4]:
        milestone_item_ids.append(
            _add_item(
                items,
                phase="beta",
                title=f"Beta milestone: {milestone}",
                rationale="This persisted first milestone is the next controlled-release increment after validation.",
                owner_role=_owner_for_scope(milestone),
                dependency_ids=[validation_item],
                exit_criteria=f"{milestone} is usable by beta participants with feedback, defects, and adoption signals logged.",
                source_idea_ids=_source_ids_for_text(milestone, source_ideas, all_source_ids),
                source_fields=["first_milestones"],
            )
        )
    if not milestone_item_ids:
        milestone_item_ids.append(
            _add_item(
                items,
                phase="beta",
                title="Run controlled beta",
                rationale="The brief needs a controlled user release before launch readiness is claimed.",
                owner_role="Product lead",
                dependency_ids=[validation_item],
                exit_criteria="A beta cohort completes the core workflow and gives enough signal to decide launch readiness.",
                source_idea_ids=all_source_ids,
                source_fields=["first_milestones"],
            )
        )

    _add_item(
        items,
        phase="launch",
        title="Prepare launch handoff",
        rationale="Launch requires packaging validated scope, unresolved risks, support expectations, and source traceability for the receiving team.",
        owner_role="Go-to-market lead",
        dependency_ids=[*milestone_item_ids, *risk_item_ids],
        exit_criteria="Launch checklist, positioning, support path, and unresolved-risk decisions are accepted by product, engineering, and go-to-market owners.",
        source_idea_ids=all_source_ids,
        source_fields=["readiness_score", "design_status", "source_idea_ids"],
    )

    return items


def _add_item(
    items: list[dict[str, Any]],
    *,
    phase: str,
    title: str,
    rationale: str,
    owner_role: str,
    dependency_ids: list[str],
    exit_criteria: str,
    source_idea_ids: list[str],
    source_fields: list[str],
) -> str:
    item_id = f"roadmap-{phase}-{sum(1 for item in items if item['phase'] == phase) + 1:02d}"
    items.append(
        {
            "id": item_id,
            "phase": phase,
            "title": title,
            "rationale": rationale,
            "owner_role": owner_role,
            "dependency_ids": list(dict.fromkeys(dependency_ids)),
            "exit_criteria": exit_criteria,
            "source_idea_ids": list(dict.fromkeys(source_idea_ids)),
            "source_fields": source_fields,
        }
    )
    return item_id


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
        data["role"] = source.get("role") or ("lead" if idea_id == design_brief.get("lead_idea_id") else "source")
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _source_ids_for_lead(lead_idea: dict[str, Any] | None, fallback: list[str]) -> list[str]:
    if lead_idea and not lead_idea.get("missing"):
        return [lead_idea["id"]]
    return fallback


def _source_ids_for_risk(
    risk: str,
    source_ideas: list[dict[str, Any]],
    fallback: list[str],
) -> list[str]:
    risk_key = _compact(risk)
    matches = [
        idea["id"]
        for idea in source_ideas
        if not idea.get("missing")
        and any(_compact(item) == risk_key for item in _string_list(idea.get("domain_risks")))
    ]
    return matches or fallback


def _source_ids_for_text(text: str, source_ideas: list[dict[str, Any]], fallback: list[str]) -> list[str]:
    haystack_fields = ("title", "one_liner", "problem", "solution", "tech_approach", "value_proposition")
    tokens = {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 3}
    matches: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        haystack = " ".join(str(idea.get(field) or "") for field in haystack_fields).lower()
        if tokens and tokens & set(re.findall(r"[a-z0-9]+", haystack)):
            matches.append(idea["id"])
    return matches or fallback


def _scope_rationale(scope: str, source_ideas: list[dict[str, Any]], design_brief: dict[str, Any]) -> str:
    matches = _source_ids_for_text(scope, source_ideas, [])
    if matches:
        return f"This MVP scope item is supported by source idea traceability: {', '.join(matches)}."
    return _first_text(design_brief.get("merged_product_concept"), "This MVP scope item is part of the persisted brief.")


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        risks.extend(_string_list(idea.get("domain_risks")))
    return risks


def _critical_dependencies(items: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for item in items:
        for dep in item["dependency_ids"]:
            counts[dep] = counts.get(dep, 0) + 1
    return [item_id for item_id, _count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:5]]


def _owner_for_risk(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("privacy", "legal", "compliance", "regulation", "pii", "security")):
        return "Risk lead"
    if any(word in lowered for word in ("api", "technical", "latency", "architecture", "integration", "data")):
        return "Engineering lead"
    if any(word in lowered for word in ("buyer", "market", "pricing", "adoption", "customer")):
        return "Product lead"
    return "Product lead"


def _owner_for_scope(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("api", "data", "integration", "backend", "service", "sync")):
        return "Engineering lead"
    if any(word in lowered for word in ("landing", "copy", "market", "pricing", "launch")):
        return "Go-to-market lead"
    if any(word in lowered for word in ("prototype", "ux", "flow", "workflow", "screen")):
        return "Design lead"
    return "Product engineer"


def _short_title(text: str) -> str:
    stripped = str(text).strip().rstrip(".")
    if len(stripped) <= 72:
        return stripped
    return stripped[:69].rstrip() + "..."


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = _compact(value)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value.strip())
    return deduped


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())
