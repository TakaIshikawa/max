"""Evidence matrix for persisted synthesized design briefs."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.analysis.design_brief_one_pager import DesignBriefStoreProtocol

SCHEMA_VERSION = "max.design_brief.evidence_matrix.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "design_brief_id",
    "design_brief_title",
    "claim_id",
    "claim",
    "evidence_id",
    "source_type",
    "source_title",
    "strength",
    "confidence",
    "contradiction_flag",
    "notes",
)

CLAIM_AREAS = (
    "problem",
    "buyer",
    "workflow",
    "why_now",
    "validation_plan",
    "risks",
    "first_milestones",
)

CLAIM_CONFIG: dict[str, dict[str, Any]] = {
    "problem": {
        "brief_fields": ("why_this_now", "synthesis_rationale"),
        "idea_fields": ("problem", "value_proposition", "evidence_rationale"),
        "signal_roles": ("problem", "pain", "gap"),
        "validation_actions": [
            "Run problem interviews with the primary user profile.",
            "Ask for recent concrete examples and current workaround costs.",
        ],
    },
    "buyer": {
        "brief_fields": ("buyer",),
        "idea_fields": ("buyer", "first_10_customers"),
        "signal_roles": ("market", "buyer"),
        "validation_actions": [
            "Interview budget owners separately from end users.",
            "Map the approval path, pilot owner, and procurement blocker.",
        ],
    },
    "workflow": {
        "brief_fields": ("workflow_context", "merged_product_concept"),
        "idea_fields": ("workflow_context", "current_workaround", "solution"),
        "signal_roles": ("workflow", "solution", "problem"),
        "validation_actions": [
            "Shadow or reconstruct the target workflow step by step.",
            "Confirm where the concept would fit into existing tools.",
        ],
    },
    "why_now": {
        "brief_fields": ("why_this_now",),
        "idea_fields": ("why_now", "value_proposition"),
        "signal_roles": ("market", "trend", "timing"),
        "validation_actions": [
            "Validate urgency against recent ecosystem or policy changes.",
            "Ask prospects what changed in the last 90 days.",
        ],
    },
    "validation_plan": {
        "brief_fields": ("validation_plan",),
        "idea_fields": ("validation_plan", "first_10_customers"),
        "signal_roles": ("market", "problem"),
        "validation_actions": [
            "Execute the first validation step before implementation.",
            "Define pass and fail thresholds for interviews or smoke tests.",
        ],
    },
    "risks": {
        "brief_fields": ("risks",),
        "idea_fields": ("domain_risks", "current_workaround", "evidence_rationale"),
        "signal_roles": ("risk", "security", "failure"),
        "validation_actions": [
            "Convert the top risk into an explicit kill criterion.",
            "Probe adoption, technical, and evidence risks during discovery.",
        ],
    },
    "first_milestones": {
        "brief_fields": ("first_milestones", "mvp_scope"),
        "idea_fields": ("solution", "tech_approach", "suggested_stack"),
        "signal_roles": ("solution", "workflow"),
        "validation_actions": [
            "Review milestone scope with two target users before building.",
            "Tie each first milestone to a validated workflow or risk.",
        ],
    },
}


def build_design_brief_evidence_matrix(
    store: DesignBriefStoreProtocol,
    design_brief: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a claim-by-claim evidence matrix from persisted brief lineage."""
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    source_ideas = _source_ideas(store, design_brief)
    evidence = _collect_evidence(store, source_ideas)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": generated,
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": design_brief.get("source_idea_ids", []),
        },
        "rows": [
            _build_row(area, design_brief, source_ideas, evidence)
            for area in CLAIM_AREAS
        ],
    }


def render_design_brief_evidence_matrix(matrix: dict[str, Any], fmt: str = "json") -> str:
    """Render an evidence matrix as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(matrix, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(matrix)
    if fmt != "markdown":
        raise ValueError(f"Unsupported evidence matrix format: {fmt}")

    brief = matrix["design_brief"]
    lines = [
        f"# Evidence Matrix: {brief['title']}",
        "",
        f"Schema: `{matrix['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Theme: {brief.get('theme') or 'implementation-candidate'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        "",
    ]

    for row in matrix["rows"]:
        lines.extend(
            [
                f"## {row['claim_area']}",
                "",
                row["claim"] or "No explicit claim captured.",
                "",
                f"- **Evidence strength**: `{row['evidence_strength']}`",
                f"- **Supporting signals**: {_inline_ids(row['supporting_signal_ids'])}",
                f"- **Supporting insights**: {_inline_ids(row['supporting_insight_ids'])}",
                f"- **Supporting source ideas**: {_inline_ids(row['supporting_source_idea_ids'])}",
                f"- **Source adapters**: {_inline_ids(row['supporting_source_adapters'])}",
                "",
                "### Gaps",
                "",
            ]
        )
        lines.extend(f"- {gap}" for gap in row["gaps"])
        lines.extend(["", "### Validation Actions", ""])
        lines.extend(f"- {action}" for action in row["validation_actions"])
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _build_row(
    claim_area: str,
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    config = CLAIM_CONFIG[claim_area]
    supporting_signal_ids = _supporting_signal_ids(config, evidence)
    supporting_source_adapters = sorted(
        {
            evidence["signals"][signal_id].source_adapter
            for signal_id in supporting_signal_ids
            if signal_id in evidence["signals"]
        }
    )
    linked_insight_ids = sorted(
        insight_id
        for insight_id, signal_ids in evidence["insight_signal_ids"].items()
        if set(signal_ids) & set(supporting_signal_ids)
    )
    source_field_count = _source_field_count(source_ideas, config["idea_fields"])
    gaps = _gaps(
        claim_area,
        design_brief,
        source_ideas,
        supporting_signal_ids,
        supporting_source_adapters,
        source_field_count,
    )

    return {
        "claim_area": claim_area,
        "claim": _claim_text(claim_area, design_brief),
        "supporting_signal_ids": supporting_signal_ids,
        "supporting_source_adapters": supporting_source_adapters,
        "supporting_insight_ids": linked_insight_ids,
        "supporting_source_idea_ids": [
            idea["id"]
            for idea in source_ideas
            if _has_any_value(idea, config["idea_fields"])
        ],
        "supporting_evidence": _supporting_evidence(
            supporting_signal_ids,
            linked_insight_ids,
            source_ideas,
            config["idea_fields"],
            evidence,
        ),
        "evidence_strength": _evidence_strength(
            supporting_signal_ids,
            supporting_source_adapters,
            linked_insight_ids,
            source_field_count,
            gaps,
        ),
        "gaps": gaps,
        "validation_actions": list(config["validation_actions"]),
    }


def _render_csv(matrix: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(matrix):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(matrix: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for claim_row in matrix.get("rows") or []:
        if not isinstance(claim_row, dict):
            continue
        for evidence in _claim_evidence_items(claim_row):
            rows.append(_csv_row(matrix, claim_row, evidence))
    return rows


def _csv_row(
    matrix: dict[str, Any],
    claim_row: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, str]:
    brief = matrix.get("design_brief") or {}
    values = {
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "claim_id": claim_row.get("claim_area") or claim_row.get("claim_id"),
        "claim": claim_row.get("claim"),
        "evidence_id": evidence.get("id") or evidence.get("evidence_id"),
        "source_type": _source_type_text(evidence.get("source_type") or evidence.get("type")),
        "source_title": evidence.get("source_title") or evidence.get("title"),
        "strength": evidence.get("strength") or claim_row.get("evidence_strength"),
        "confidence": evidence.get("confidence"),
        "contradiction_flag": _contradiction_flag(evidence),
        "notes": evidence.get("notes") or evidence.get("note") or evidence.get("summary"),
    }
    return {column: _csv_text(values.get(column)) for column in CSV_COLUMNS}


def _claim_evidence_items(claim_row: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = claim_row.get("supporting_evidence")
    if isinstance(evidence, list):
        return [item for item in evidence if isinstance(item, dict)]

    items: list[dict[str, Any]] = []
    for signal_id in _string_list(claim_row.get("supporting_signal_ids")):
        items.append({"id": signal_id, "source_type": "signal"})
    for insight_id in _string_list(claim_row.get("supporting_insight_ids")):
        items.append({"id": insight_id, "source_type": "insight"})
    for idea_id in _string_list(claim_row.get("supporting_source_idea_ids")):
        items.append({"id": idea_id, "source_type": "source_idea"})
    return items


def _supporting_evidence(
    signal_ids: list[str],
    insight_ids: list[str],
    source_ideas: list[dict[str, Any]],
    idea_fields: tuple[str, ...],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for signal_id in signal_ids:
        signal = evidence["signals"].get(signal_id)
        if not signal:
            continue
        metadata = getattr(signal, "metadata", {}) or {}
        items.append(
            {
                "id": signal_id,
                "source_type": _source_type_text(getattr(signal, "source_type", "")),
                "source_title": getattr(signal, "title", ""),
                "confidence": getattr(signal, "credibility", ""),
                "contradiction_flag": _contradiction_flag(metadata),
                "notes": {
                    "source_adapter": getattr(signal, "source_adapter", ""),
                    "signal_role": getattr(signal, "signal_role", ""),
                    "tags": getattr(signal, "tags", []),
                },
            }
        )
    for insight_id in insight_ids:
        insight = evidence["insights"].get(insight_id)
        if not insight:
            continue
        items.append(
            {
                "id": insight_id,
                "source_type": "insight",
                "source_title": getattr(insight, "title", ""),
                "confidence": getattr(insight, "confidence", ""),
                "contradiction_flag": False,
                "notes": {
                    "category": _source_type_text(getattr(insight, "category", "")),
                    "evidence": _string_list(getattr(insight, "evidence", [])),
                },
            }
        )
    for idea in source_ideas:
        if not _has_any_value(idea, idea_fields):
            continue
        items.append(
            {
                "id": idea.get("id"),
                "source_type": "source_idea",
                "source_title": idea.get("title"),
                "confidence": idea.get("quality_score"),
                "contradiction_flag": False,
                "notes": {
                    "role": idea.get("role"),
                    "fields": [field for field in idea_fields if _has_value(idea.get(field))],
                },
            }
        )
    return items


def _supporting_signal_ids(config: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    roles = {role.lower() for role in config["signal_roles"]}
    selected: set[str] = set()

    for signal_id, signal in evidence["signals"].items():
        role = str(getattr(signal, "signal_role", "") or "").lower()
        tags = {str(tag).lower() for tag in getattr(signal, "tags", [])}
        source_type = str(getattr(signal, "source_type", "") or "").lower()
        if hasattr(signal.source_type, "value"):
            source_type = signal.source_type.value.lower()
        if role in roles or roles & tags or source_type in roles:
            selected.add(signal_id)

    if not selected:
        selected.update(evidence["idea_signal_ids"])

    return sorted(selected)


def _collect_evidence(store: DesignBriefStoreProtocol, source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    idea_signal_ids: set[str] = set()
    insight_ids: set[str] = set()

    for idea in source_ideas:
        idea_signal_ids.update(_string_list(idea.get("evidence_signals")))
        insight_ids.update(_string_list(idea.get("inspiring_insights")))

    insights: dict[str, Any] = {}
    insight_signal_ids: dict[str, list[str]] = {}
    for insight_id in sorted(insight_ids):
        insight = store.get_insight(insight_id)
        if not insight:
            continue
        insights[insight_id] = insight
        signal_ids = _string_list(insight.evidence)
        insight_signal_ids[insight_id] = signal_ids
        idea_signal_ids.update(signal_ids)

    signals: dict[str, Any] = {}
    for signal_id in sorted(idea_signal_ids):
        signal = store.get_signal(signal_id)
        if signal:
            signals[signal_id] = signal

    return {
        "idea_signal_ids": sorted(idea_signal_ids),
        "insights": insights,
        "insight_signal_ids": insight_signal_ids,
        "signals": signals,
    }


def _source_ideas(store: DesignBriefStoreProtocol, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    relationship_by_id: dict[str, dict[str, Any]] = {}
    for source in design_brief.get("sources", []):
        relationship_by_id.setdefault(source["idea_id"], source)

    ordered_ids = list(
        dict.fromkeys(
            [
                design_brief.get("lead_idea_id"),
                *design_brief.get("source_idea_ids", []),
                *relationship_by_id.keys(),
            ]
        )
    )

    ideas: list[dict[str, Any]] = []
    for idea_id in ordered_ids:
        if not idea_id:
            continue
        unit = store.get_buildable_unit(str(idea_id))
        if not unit:
            continue
        data = unit.model_dump(mode="json")
        relationship = relationship_by_id.get(str(idea_id), {})
        data["role"] = relationship.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = relationship.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _claim_text(claim_area: str, design_brief: dict[str, Any]) -> str:
    if claim_area == "problem":
        return _first_text(design_brief.get("synthesis_rationale"), design_brief.get("why_this_now"))
    if claim_area == "buyer":
        return _first_text(design_brief.get("buyer"), "Buyer is not specified.")
    if claim_area == "workflow":
        return _first_text(design_brief.get("workflow_context"), "Workflow is not specified.")
    if claim_area == "why_now":
        return _first_text(design_brief.get("why_this_now"), "Timing rationale is not specified.")
    if claim_area == "validation_plan":
        return _first_text(design_brief.get("validation_plan"), "Validation plan is not specified.")
    if claim_area == "risks":
        risks = _string_list(design_brief.get("risks"))
        return "; ".join(risks) if risks else "Risks are not specified."
    milestones = _string_list(design_brief.get("first_milestones"))
    return "; ".join(milestones) if milestones else "First milestones are not specified."


def _gaps(
    claim_area: str,
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    supporting_signal_ids: list[str],
    supporting_source_adapters: list[str],
    source_field_count: int,
) -> list[str]:
    config = CLAIM_CONFIG[claim_area]
    gaps: list[str] = []

    if not _has_any_value(design_brief, config["brief_fields"]):
        gaps.append(f"Persisted brief has no explicit {claim_area} claim.")
    if source_field_count == 0:
        gaps.append("No source idea has a populated field for this claim area.")
    elif source_field_count < max(2, len(source_ideas)) and len(source_ideas) > 1:
        gaps.append("Only part of the source idea set explicitly supports this claim.")
    if not supporting_signal_ids:
        gaps.append("No persisted evidence signals are linked to this claim area.")
    if len(supporting_source_adapters) == 1:
        gaps.append("Evidence comes from a single source adapter.")
    if not source_ideas:
        gaps.append("No persisted source ideas could be loaded for this brief.")

    return gaps or ["No major evidence gap detected from persisted data."]


def _evidence_strength(
    signal_ids: list[str],
    source_adapters: list[str],
    insight_ids: list[str],
    source_field_count: int,
    gaps: list[str],
) -> str:
    if not signal_ids or source_field_count == 0:
        return "weak"

    actionable_gaps = [gap for gap in gaps if not gap.startswith("No major")]
    if len(signal_ids) >= 3 and len(source_adapters) >= 2 and insight_ids and source_field_count >= 2:
        return "strong" if not actionable_gaps else "moderate"
    if len(signal_ids) >= 1 and (source_adapters or insight_ids) and source_field_count >= 1:
        return "moderate"
    return "weak"


def _source_field_count(source_ideas: list[dict[str, Any]], fields: tuple[str, ...]) -> int:
    return sum(1 for idea in source_ideas if _has_any_value(idea, fields))


def _has_any_value(record: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return any(_has_value(record.get(field)) for field in fields)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [str(key) for key in value.keys()]
    return [str(item) for item in value if str(item).strip()]


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _inline_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _source_type_text(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def _contradiction_flag(value: Any) -> bool:
    if isinstance(value, dict):
        for key in (
            "contradiction_flag",
            "contradictory",
            "contradiction",
            "contradicts",
            "contradictory_evidence",
        ):
            if bool(value.get(key)):
                return True
    return bool(getattr(value, "contradiction_flag", False))
