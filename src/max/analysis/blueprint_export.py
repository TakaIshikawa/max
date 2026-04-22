"""Export Max design briefs as canonical Blueprint source briefs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from max.store.db import Store

SCHEMA_VERSION = "max.blueprint.source_brief.v1"


def build_blueprint_source_brief(
    store: Store,
    design_brief: dict[str, Any],
    *,
    exported_at: str | None = None,
) -> dict[str, Any]:
    """Build a Blueprint import packet from a persisted Max design brief."""
    exported = exported_at or datetime.now(timezone.utc).isoformat()
    source_ideas = []
    seen: set[tuple[str, str]] = set()

    for source in design_brief.get("sources", []):
        idea_id = source["idea_id"]
        role = source["role"]
        key = (idea_id, role)
        if key in seen:
            continue
        seen.add(key)
        source_ideas.append(
            _source_idea_payload(
                store,
                idea_id=idea_id,
                role=role,
                rank=source["rank"],
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "exported_at": exported,
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief["domain"],
            "theme": design_brief["theme"],
            "readiness_score": design_brief["readiness_score"],
            "design_status": design_brief["design_status"],
            "buyer": design_brief["buyer"],
            "specific_user": design_brief["specific_user"],
            "workflow_context": design_brief["workflow_context"],
            "why_this_now": design_brief["why_this_now"],
            "merged_product_concept": design_brief["merged_product_concept"],
            "synthesis_rationale": design_brief["synthesis_rationale"],
            "mvp_scope": design_brief["mvp_scope"],
            "first_milestones": design_brief["first_milestones"],
            "validation_plan": design_brief["validation_plan"],
            "risks": design_brief["risks"],
            "source_idea_ids": design_brief["source_idea_ids"],
            "created_at": design_brief["created_at"],
            "updated_at": design_brief["updated_at"],
        },
        "source_ideas": source_ideas,
        "blueprint_import_hints": {
            "recommended_title": design_brief["title"],
            "recommended_domain": design_brief["domain"],
            "recommended_source_priority": "design_brief",
        },
    }


def render_blueprint_packet(packet: dict[str, Any], *, fmt: str) -> str:
    """Render a Blueprint packet as JSON or YAML."""
    if fmt == "json":
        return json.dumps(packet, indent=2) + "\n"
    if fmt == "yaml":
        return yaml.safe_dump(packet, sort_keys=False, allow_unicode=True)
    raise ValueError(f"Unsupported Blueprint export format: {fmt}")


def write_blueprint_packet(path: Path, packet: dict[str, Any], *, fmt: str) -> None:
    """Write a Blueprint packet to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_blueprint_packet(packet, fmt=fmt))


def blueprint_filename(design_brief: dict[str, Any], *, fmt: str) -> str:
    """Return a stable export filename for a design brief."""
    extension = "yaml" if fmt == "yaml" else "json"
    return f"{design_brief['id']}.{extension}"


def _source_idea_payload(
    store: Store,
    *,
    idea_id: str,
    role: str,
    rank: int,
) -> dict[str, Any]:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        return {
            "id": idea_id,
            "role": role,
            "rank": rank,
            "missing": True,
        }

    evaluation = store.get_evaluation(idea_id)
    feedback = store.get_latest_feedback(idea_id)
    return {
        "id": unit.id,
        "role": role,
        "rank": rank,
        "title": unit.title,
        "one_liner": unit.one_liner,
        "status": unit.status,
        "domain": unit.domain,
        "category": unit.category,
        "buyer": unit.buyer,
        "specific_user": unit.specific_user,
        "workflow_context": unit.workflow_context,
        "problem": unit.problem,
        "solution": unit.solution,
        "value_proposition": unit.value_proposition,
        "current_workaround": unit.current_workaround,
        "why_now": unit.why_now,
        "validation_plan": unit.validation_plan,
        "first_10_customers": unit.first_10_customers,
        "domain_risks": unit.domain_risks,
        "evidence_rationale": unit.evidence_rationale,
        "tech_approach": unit.tech_approach,
        "quality_score": unit.quality_score,
        "novelty_score": unit.novelty_score,
        "usefulness_score": unit.usefulness_score,
        "evaluation_score": evaluation.overall_score if evaluation else None,
        "recommendation": evaluation.recommendation if evaluation else None,
        "feedback_outcome": feedback["outcome"] if feedback else None,
        "feedback_reason": feedback["reason"] if feedback else "",
    }
