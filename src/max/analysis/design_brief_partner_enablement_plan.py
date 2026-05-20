"""Deterministic partner enablement plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, row_id, section, sorted_rows, text

KIND = "max.design_brief.partner_enablement_plan"
SCHEMA_VERSION = "max.design_brief.partner_enablement_plan.v1"


def generate_design_brief_partner_enablement_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "partner_enablement_plan")
    segments = _segments(data)
    gaps = _gaps(segments)
    status = "blocked" if any(row["launch_blockers"] for row in segments) or any(item["severity"] == "high" for item in gaps) else ("needs_attention" if gaps else "ready")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {"plan_status": status, "partner_segment_count": len(segments), "gap_count": len(gaps)},
        "partner_enablement": segments,
        "enablement_gaps": gaps,
    }


def _segments(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_dicts(data.get("partner_segments") or data.get("segments")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("PE", index)),
                "segment": first_text(item.get("segment"), item.get("name"), default=f"partner segment {index}"),
                "enablement_assets": evidence(item.get("enablement_assets") or item.get("assets")),
                "certification_steps": evidence(item.get("certification_steps") or item.get("certification")),
                "dependency_owner": text(item.get("dependency_owner") or item.get("owner")),
                "launch_blockers": evidence(item.get("launch_blockers") or item.get("blockers")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "segment")


def _gaps(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return [gap("missing_partner_segments", "No partner segments were provided.")]
    gaps = []
    for row in segments:
        key = row["segment"].lower().replace(" ", "_")
        if not row["enablement_assets"]:
            gaps.append(gap(f"{key}_missing_assets", f"{row['segment']} is missing enablement assets.", "medium"))
        if not row["certification_steps"]:
            gaps.append(gap(f"{key}_missing_certification", f"{row['segment']} is missing certification criteria.", "medium"))
        if not row["dependency_owner"]:
            gaps.append(gap(f"{key}_missing_dependency_owner", f"{row['segment']} is missing a dependency owner."))
    return gaps
