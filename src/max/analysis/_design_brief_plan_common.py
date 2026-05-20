"""Shared helpers for deterministic design brief analysis reports."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

DEFAULT_CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "section",
    "item_id",
    "name",
    "owner",
    "timing",
    "action",
    "evidence",
    "severity",
    "source_idea_id",
)


def brief_context(store: Any, brief: dict[str, Any]) -> dict[str, Any]:
    """Return normalized context and source ideas for a persisted design brief."""
    source_ideas = source_ideas_for_brief(store, brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    title = text(brief.get("title"), "Design brief")
    base = fallback_name(title)
    fallbacks: list[str] = []

    target_user = first_text(brief.get("specific_user"), lead_idea and lead_idea.get("specific_user"))
    if not target_user:
        target_user = f"{base} users"
        fallbacks.append("specific_user")

    buyer = first_text(brief.get("buyer"), lead_idea and lead_idea.get("buyer"))
    if not buyer:
        buyer = f"{base} sponsor"
        fallbacks.append("buyer")

    workflow = first_text(
        brief.get("workflow_context"), lead_idea and lead_idea.get("workflow_context")
    )
    if not workflow:
        workflow = f"{base} operating workflow"
        fallbacks.append("workflow_context")

    concept = first_text(
        brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("solution"),
        title,
    )
    if not concept:
        concept = title
        fallbacks.append("merged_product_concept")

    scope = list_values(brief.get("mvp_scope"))
    if not scope:
        scope = ["smallest testable product behavior"]
        fallbacks.append("mvp_scope")

    risks = dedupe(
        [
            *list_values(brief.get("risks")),
            *[
                risk
                for idea in source_ideas
                for risk in list_values(idea.get("domain_risks"))
            ],
        ]
    )
    evidence = dedupe(
        [
            *list_values(brief.get("validation_plan")),
            *[
                signal
                for idea in source_ideas
                for signal in [
                    *list_values(idea.get("evidence_signals")),
                    *list_values(idea.get("inspiring_insights")),
                ]
            ],
        ]
    )
    source_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_ids:
        source_ids = list_values(brief.get("source_idea_ids"))

    return {
        "title": title,
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "product_concept": concept,
        "mvp_scope": scope,
        "risks": risks,
        "evidence": evidence,
        "evidence_count": len(evidence),
        "readiness_score": float(brief.get("readiness_score") or 0.0),
        "source_ideas": source_ideas,
        "source_idea_ids": source_ids,
        "primary_source_idea_id": source_ids[0] if source_ids else "",
        "fallbacks_used": fallbacks,
    }


def source_ideas_for_brief(store: Any, brief: dict[str, Any]) -> list[dict[str, Any]]:
    sources = list(brief.get("sources") or [])
    if not sources:
        lead_id = brief.get("lead_idea_id")
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        for rank, idea_id in enumerate(list_values(brief.get("source_idea_ids")), start=1):
            if idea_id != lead_id:
                sources.append({"idea_id": idea_id, "role": "source", "rank": rank})

    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sorted(sources, key=lambda row: (int(row.get("rank", 0)), str(row.get("role", "")))):
        idea_id = str(source.get("idea_id") or source.get("id") or "").strip()
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
        data = unit.model_dump(mode="json") if hasattr(unit, "model_dump") else dict(unit)
        data["id"] = data.get("id") or idea_id
        data["role"] = source.get("role", data.get("role", "source"))
        data["rank"] = source.get("rank", data.get("rank", 0))
        ideas.append(data)
    return ideas


def design_brief_block(brief: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": brief["id"],
        "title": brief["title"],
        "domain": brief.get("domain", ""),
        "theme": brief.get("theme", ""),
        "readiness_score": context["readiness_score"],
        "design_status": brief.get("design_status", ""),
        "lead_idea_id": brief.get("lead_idea_id", ""),
        "source_idea_ids": context["source_idea_ids"],
    }


def source_block(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": "max",
        "entity_type": "design_brief",
        "id": brief["id"],
        "generated_at": brief.get("updated_at") or brief.get("created_at"),
    }


def render_sectioned_markdown(
    report: dict[str, Any],
    *,
    title: str,
    summary_title: str,
    sections: tuple[tuple[str, str], ...],
) -> str:
    brief = dict_value(report.get("design_brief"))
    summary = dict_value(report.get("summary"))
    lines = [
        f"# {title}: {text(brief.get('title'), 'Untitled design brief')}",
        "",
        f"Schema: `{text(report.get('schema_version'), 'unknown')}`",
        f"Design brief: `{text(brief.get('id'), 'unknown')}`",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {join_text(brief.get('source_idea_ids'), 'design brief')}",
        "",
        f"## {summary_title}",
        "",
    ]
    for key in sorted(summary):
        value = summary[key]
        if key.endswith("_count"):
            continue
        label = key.replace("_", " ").capitalize()
        lines.append(f"- {label}: {join_text(value, 'none') if isinstance(value, list) else text(value, 'Not specified')}")

    for section_key, section_title in sections:
        lines.extend(["", f"## {section_title}", ""])
        rows = list_of_dicts(report.get(section_key))
        if not rows:
            lines.append("- None")
            continue
        for row in rows:
            heading = text(row.get("name") or row.get("title") or row.get("id"), "Item")
            details = []
            for field in ("owner", "timing", "severity", "action", "evidence", "description", "source_idea_id"):
                if row.get(field) not in (None, "", []):
                    details.append(f"{field.replace('_', ' ')}: {join_text(row[field], 'none') if isinstance(row[field], list) else text(row[field])}")
            suffix = "; ".join(details)
            lines.append(f"- **{text(row.get('id'), section_key)} {heading}**: {suffix}")
    return "\n".join(lines).rstrip() + "\n"


def render_sectioned_csv(
    report: dict[str, Any],
    sections: tuple[str, ...],
    columns: tuple[str, ...] = DEFAULT_CSV_COLUMNS,
) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    brief = dict_value(report.get("design_brief"))
    for section in sections:
        for row in list_of_dicts(report.get(section)):
            values = {
                "design_brief_id": brief.get("id"),
                "design_brief_title": brief.get("title"),
                "section": section,
                "item_id": row.get("id"),
                "name": row.get("name") or row.get("title"),
                "owner": row.get("owner"),
                "timing": row.get("timing"),
                "action": row.get("action") or row.get("description"),
                "evidence": row.get("evidence"),
                "severity": row.get("severity"),
                "source_idea_id": row.get("source_idea_id"),
            }
            writer.writerow({column: text(values.get(column), "") for column in columns})
    return output.getvalue()


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return " ".join(value.split()) or default
    if isinstance(value, (dict, list)):
        if not value:
            return default
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return " ".join(str(value).split()) or default


def join_text(value: Any, default: str) -> str:
    if isinstance(value, list):
        joined = ", ".join(text(item) for item in value if text(item))
        return joined or default
    return text(value, default)


def first_text(*values: Any) -> str:
    for value in values:
        candidate = join_text(value, "") if isinstance(value, list) else text(value, "")
        if candidate:
            return candidate
    return ""


def list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, dict):
        return [f"{key}={value[key]}" for key in sorted(value) if value[key]]
    if isinstance(value, (list, tuple, set)):
        return [text(item) for item in value if text(item)]
    return [text(value)] if text(value) else []


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = text(value)
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def fallback_name(title: str) -> str:
    cleaned = text(title, "Design brief")
    for suffix in (" Brief", " Plan", " Report"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned or "Design brief"
