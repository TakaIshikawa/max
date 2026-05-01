"""Data-room index exports for persisted design briefs."""

from __future__ import annotations

import json
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.data_room_index.v1"

ARTIFACTS: tuple[dict[str, Any], ...] = (
    {
        "key": "design_brief",
        "title": "Design Brief",
        "description": "Canonical persisted brief and source idea context.",
        "json_path": "/api/v1/design-briefs/{brief_id}",
        "markdown_path": "/api/v1/design-briefs/{brief_id}.md",
        "section": "core",
    },
    {
        "key": "bundle",
        "title": "Design Brief Bundle",
        "description": "Consolidated handoff package for implementation and review.",
        "json_path": "/api/v1/design-briefs/{brief_id}/bundle",
        "markdown_path": "/api/v1/design-briefs/{brief_id}/bundle.md",
        "section": "handoff",
    },
    {
        "key": "validation_plan",
        "title": "Validation Plan",
        "description": "Experiment and discovery plan for validating the brief.",
        "json_path": "/api/v1/design-briefs/{brief_id}/validation-plan",
        "markdown_path": "/api/v1/design-briefs/{brief_id}/validation-plan.md",
        "section": "validation",
    },
    {
        "key": "evidence_matrix",
        "title": "Evidence Matrix",
        "description": "Traceability from claims and decisions to supporting evidence.",
        "json_path": "/api/v1/design-briefs/{brief_id}/evidence-matrix",
        "markdown_path": "/api/v1/design-briefs/{brief_id}/evidence-matrix.md",
        "section": "validation",
    },
    {
        "key": "risk_register",
        "title": "Risk Register",
        "description": "Prioritized product, delivery, and domain risks.",
        "json_path": "/api/v1/design-briefs/{brief_id}/risk-register",
        "markdown_path": "/api/v1/design-briefs/{brief_id}/risk-register.md",
        "section": "risk",
    },
    {
        "key": "roadmap",
        "title": "Roadmap",
        "description": "Sequenced delivery milestones derived from the brief.",
        "json_path": "/api/v1/design-briefs/{brief_id}/roadmap",
        "markdown_path": "/api/v1/design-briefs/{brief_id}/roadmap.md",
        "section": "delivery",
    },
    {
        "key": "prd",
        "title": "PRD",
        "description": "Product requirements document for implementation handoff.",
        "json_path": "/api/v1/design-briefs/{brief_id}/prd",
        "markdown_path": "/api/v1/design-briefs/{brief_id}/prd.md",
        "section": "delivery",
    },
    {
        "key": "market_sizing",
        "title": "Market Sizing",
        "description": "Market hypotheses, segment sizing, and confidence signals.",
        "json_path": "/api/v1/design-briefs/{brief_id}/market-sizing",
        "markdown_path": "/api/v1/design-briefs/{brief_id}/market-sizing.md",
        "section": "commercial",
    },
    {
        "key": "competitive_landscape",
        "title": "Competitive Landscape",
        "description": "Competitor clusters, differentiation, and positioning guidance.",
        "json_path": "/api/v1/design-briefs/{brief_id}/competitive-landscape",
        "markdown_path": "/api/v1/design-briefs/{brief_id}/competitive-landscape.md",
        "section": "commercial",
    },
)


def build_design_brief_data_room_index(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build a static index of REST-accessible data-room artifacts for a design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    generated_at = design_brief.get("updated_at") or design_brief.get("created_at")
    artifacts = [_artifact_entry(artifact, brief_id) for artifact in ARTIFACTS]
    sections = []
    for section_key in ("core", "handoff", "validation", "risk", "delivery", "commercial"):
        section_artifacts = [artifact for artifact in artifacts if artifact["section"] == section_key]
        sections.append(
            {
                "key": section_key,
                "title": section_key.replace("_", " ").title(),
                "artifact_keys": [artifact["key"] for artifact in section_artifacts],
                "artifact_count": len(section_artifacts),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.data_room_index",
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": generated_at,
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": _string_list(design_brief.get("source_idea_ids")),
        },
        "summary": {
            "artifact_count": len(artifacts),
            "section_count": len(sections),
            "available_formats": ["json", "markdown"],
        },
        "sections": sections,
        "artifacts": artifacts,
    }


def render_design_brief_data_room_index(index: dict[str, Any], *, fmt: str = "markdown") -> str:
    """Render a data-room index as Markdown or deterministic JSON."""
    if fmt == "json":
        return json.dumps(index, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported data room index format: {fmt}")

    brief = index["design_brief"]
    artifacts_by_key = {artifact["key"]: artifact for artifact in index["artifacts"]}
    lines = [
        f"# Data Room Index: {brief['title']}",
        "",
        f"Schema: `{index['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Domain: {brief.get('domain') or 'general'}",
        f"Artifacts: {index['summary']['artifact_count']}",
        "",
        "## Artifact Index",
        "",
        "| Artifact | JSON | Markdown | Description |",
        "| --- | --- | --- | --- |",
    ]
    for artifact in index["artifacts"]:
        lines.append(
            "| "
            f"{artifact['title']} | "
            f"`{artifact['urls']['json']}` | "
            f"`{artifact['urls']['markdown']}` | "
            f"{artifact['description']} |"
        )

    lines.extend(["", "## Sections", ""])
    for section in index["sections"]:
        lines.extend([f"### {section['title']}", ""])
        for artifact_key in section["artifact_keys"]:
            artifact = artifacts_by_key[artifact_key]
            lines.append(f"- **{artifact['title']}**: {artifact['description']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def data_room_index_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = "json" if fmt == "json" else "md"
    return f"{_filename_part(str(design_brief.get('id') or 'design-brief'))}-data-room-index.{extension}"


def _artifact_entry(artifact: dict[str, Any], brief_id: str) -> dict[str, Any]:
    json_url = artifact["json_path"].format(brief_id=brief_id)
    markdown_url = artifact["markdown_path"].format(brief_id=brief_id)
    return {
        "key": artifact["key"],
        "title": artifact["title"],
        "description": artifact["description"],
        "section": artifact["section"],
        "formats": ["json", "markdown"],
        "urls": {
            "json": json_url,
            "markdown": markdown_url,
        },
    }


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "design-brief"
