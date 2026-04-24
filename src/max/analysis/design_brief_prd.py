"""Deterministic one-page PRD export for persisted design briefs."""

from __future__ import annotations

import json
import re
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.prd.v1"


def build_design_brief_prd(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a concise PRD from a persisted design brief and source ideas."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    all_source_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not all_source_ids:
        all_source_ids = list(design_brief.get("source_idea_ids") or [])

    sections = {
        "title": _section(
            "Title",
            design_brief["title"],
            ["design_brief.title"],
            all_source_ids,
        ),
        "user_buyer": _section(
            "User / Buyer",
            _user_buyer_text(design_brief, lead_idea),
            ["specific_user", "buyer"],
            _source_ids_for_fields(source_ideas, ("specific_user", "buyer"), all_source_ids),
        ),
        "problem": _section(
            "Problem",
            _first_text(
                lead_idea and lead_idea.get("problem"),
                design_brief.get("why_this_now"),
                design_brief.get("synthesis_rationale"),
                "The brief does not include a specific problem statement yet.",
            ),
            ["problem", "why_this_now", "synthesis_rationale"],
            _source_ids_for_fields(source_ideas, ("problem", "value_proposition"), all_source_ids),
        ),
        "proposed_workflow": _section(
            "Proposed Workflow",
            _workflow_text(design_brief, lead_idea),
            ["workflow_context", "merged_product_concept", "solution"],
            _source_ids_for_fields(
                source_ideas,
                ("workflow_context", "solution", "tech_approach"),
                all_source_ids,
            ),
        ),
        "non_goals": _section(
            "Non-Goals",
            _non_goals(design_brief, source_ideas),
            ["risks", "domain_risks"],
            _source_ids_for_risks(source_ideas, all_source_ids),
        ),
        "success_metrics": _section(
            "Success Metrics",
            _success_metrics(design_brief, source_ideas),
            ["validation_plan", "first_milestones"],
            all_source_ids,
        ),
        "mvp_scope": _section(
            "MVP Scope",
            _string_list(design_brief.get("mvp_scope"))
            or ["Define the smallest workflow slice before implementation."],
            ["mvp_scope"],
            _source_ids_for_fields(source_ideas, ("solution", "tech_approach"), all_source_ids),
        ),
        "dependencies": _section(
            "Dependencies",
            _dependencies(design_brief, source_ideas),
            ["suggested_stack", "tech_approach", "validation_plan"],
            _source_ids_for_fields(
                source_ideas,
                ("suggested_stack", "tech_approach", "validation_plan"),
                all_source_ids,
            ),
        ),
        "risks": _section(
            "Risks",
            _risks(design_brief, source_ideas),
            ["risks", "domain_risks"],
            _source_ids_for_risks(source_ideas, all_source_ids),
        ),
        "evidence_links": _section(
            "Evidence Links",
            _evidence_links(store, source_ideas),
            ["evidence_signals", "inspiring_insights", "evidence_rationale"],
            all_source_ids,
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
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
            "source_idea_ids": all_source_ids,
        },
        "summary": {
            "section_count": len(sections),
            "source_idea_count": len(all_source_ids),
            "evidence_link_count": len(sections["evidence_links"]["content"]),
        },
        "sections": sections,
        "source_ideas": source_ideas,
    }


def render_design_brief_prd(prd: dict[str, Any], fmt: str = "json") -> str:
    """Render the design brief PRD as JSON or Markdown."""
    if fmt == "json":
        return json.dumps(prd, indent=2) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported PRD format: {fmt}")

    brief = prd["design_brief"]
    sections = prd["sections"]
    lines = [
        f"# PRD: {brief['title']}",
        "",
        f"Schema: `{prd['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        "",
    ]
    for key in (
        "user_buyer",
        "problem",
        "proposed_workflow",
        "non_goals",
        "success_metrics",
        "mvp_scope",
        "dependencies",
        "risks",
        "evidence_links",
    ):
        section = sections[key]
        lines.extend([f"## {section['heading']}", ""])
        content = section["content"]
        if isinstance(content, list):
            lines.extend(f"- {item}" for item in content)
        else:
            lines.append(str(content))
        source_ids = ", ".join(section["source_idea_ids"]) or "design brief"
        lines.extend(["", f"Source ideas: {source_ids}", ""])

    return "\n".join(lines).rstrip() + "\n"


def _section(
    heading: str,
    content: str | list[str],
    source_fields: list[str],
    source_idea_ids: list[str],
) -> dict[str, Any]:
    return {
        "heading": heading,
        "content": content,
        "source_fields": source_fields,
        "source_idea_ids": list(dict.fromkeys(source_idea_ids)),
    }


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


def _user_buyer_text(design_brief: dict[str, Any], lead_idea: dict[str, Any] | None) -> str:
    user = _first_text(design_brief.get("specific_user"), lead_idea and lead_idea.get("specific_user"), "TBD user")
    buyer = _first_text(design_brief.get("buyer"), lead_idea and lead_idea.get("buyer"), "TBD buyer")
    return f"Primary user: {user}. Buyer or sponsor: {buyer}."


def _workflow_text(design_brief: dict[str, Any], lead_idea: dict[str, Any] | None) -> str:
    workflow = _first_text(
        design_brief.get("workflow_context"),
        lead_idea and lead_idea.get("workflow_context"),
        "the target workflow",
    )
    concept = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("solution"),
        "the proposed product concept",
    )
    return f"In {workflow}, introduce {concept}"


def _non_goals(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    non_goals = [
        "Do not expand beyond the persisted MVP scope before validation evidence is reviewed.",
        "Do not treat this PRD as a launch plan; it is a one-page product handoff.",
    ]
    if _risks(design_brief, source_ideas):
        non_goals.append("Do not defer known high-risk assumptions without an owner and validation action.")
    return non_goals


def _success_metrics(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    metrics = [
        "Target users can complete the proposed workflow with the MVP scope.",
        "Validation produces an explicit build, revise, or stop decision.",
    ]
    for milestone in _string_list(design_brief.get("first_milestones"))[:3]:
        metrics.append(f"First milestone accepted: {milestone}.")
    plan = _first_text(design_brief.get("validation_plan"), *_field_values(source_ideas, "validation_plan"))
    if plan:
        metrics.append(f"Validation plan executed: {plan}")
    return _dedupe_strings(metrics)


def _dependencies(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    deps = []
    for idea in source_ideas:
        if idea.get("missing"):
            deps.append(f"Resolve missing source idea `{idea['id']}`.")
            continue
        stack = idea.get("suggested_stack") or {}
        if stack:
            deps.append(f"{idea['id']} suggested stack: {_format_stack(stack)}.")
        if _compact(idea.get("tech_approach")):
            deps.append(f"{idea['id']} technical approach: {idea['tech_approach']}")
    if _compact(design_brief.get("validation_plan")):
        deps.append("Validation plan must be run before expanding scope.")
    return _dedupe_strings(deps) or ["No explicit external dependencies are captured yet."]


def _risks(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> list[str]:
    risks = [*_string_list(design_brief.get("risks"))]
    for idea in source_ideas:
        risks.extend(_string_list(idea.get("domain_risks")))
    return _dedupe_strings(risks) or ["No explicit risks are captured yet."]


def _evidence_links(store: Store, source_ideas: list[dict[str, Any]]) -> list[str]:
    links: list[str] = []
    for idea in source_ideas:
        if idea.get("missing"):
            continue
        if _compact(idea.get("evidence_rationale")):
            links.append(f"{idea['id']} rationale: {idea['evidence_rationale']}")
        for signal_id in _string_list(idea.get("evidence_signals")):
            signal = store.get_signal(signal_id)
            if signal:
                links.append(f"{signal.id}: {signal.title} ({signal.url})")
            else:
                links.append(f"{signal_id}: signal reference")
        for insight_id in _string_list(idea.get("inspiring_insights")):
            links.append(f"{insight_id}: insight reference")
    return _dedupe_strings(links) or ["No source evidence links are captured yet."]


def _source_ids_for_fields(
    source_ideas: list[dict[str, Any]],
    fields: tuple[str, ...],
    fallback: list[str],
) -> list[str]:
    matches = [
        idea["id"]
        for idea in source_ideas
        if not idea.get("missing") and any(_has_value(idea.get(field)) for field in fields)
    ]
    return matches or fallback


def _source_ids_for_risks(source_ideas: list[dict[str, Any]], fallback: list[str]) -> list[str]:
    matches = [
        idea["id"]
        for idea in source_ideas
        if not idea.get("missing") and _string_list(idea.get("domain_risks"))
    ]
    return matches or fallback


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    return [str(idea.get(field) or "") for idea in source_ideas if not idea.get("missing")]


def _format_stack(stack: Any) -> str:
    if isinstance(stack, dict):
        return ", ".join(f"{key}={value}" for key, value in sorted(stack.items()))
    return str(stack)


def _has_value(value: Any) -> bool:
    if isinstance(value, list):
        return bool(_string_list(value))
    if isinstance(value, dict):
        return bool(value)
    return bool(_compact(value))


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
        return [value.strip()] if value.strip() else []
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
        deduped.append(str(value).strip())
    return deduped


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())
