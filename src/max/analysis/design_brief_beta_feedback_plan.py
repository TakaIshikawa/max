"""Deterministic beta feedback plans for mapping-style design briefs."""

from __future__ import annotations

from typing import Any, Mapping

from max.analysis._design_brief_mapping_plan import evidence, first_text, gap, list_of_dicts, row_id, section, sorted_rows, text

KIND = "max.design_brief.beta_feedback_plan"
SCHEMA_VERSION = "max.design_brief.beta_feedback_plan.v1"


def generate_design_brief_beta_feedback_plan(brief: Mapping[str, Any]) -> dict[str, Any]:
    data = section(brief, "beta_feedback_plan")
    cohorts = _cohorts(data)
    channels = _channels(data)
    owners = sorted(evidence(data.get("owners") or data.get("owner_assignments")), key=str.casefold)
    themes = _themes(data)
    gaps = _gaps(cohorts, channels, owners)
    status = "blocked" if any(item["severity"] == "high" for item in gaps) else ("needs_attention" if themes else "ready")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "readiness_status": status,
            "cohort_count": len(cohorts),
            "feedback_channel_count": len(channels),
            "unresolved_theme_count": len(themes),
            "gap_count": len(gaps),
        },
        "beta_cohorts": cohorts,
        "feedback_channels": channels,
        "owner_assignments": owners,
        "unresolved_themes": themes,
        "readiness_gaps": gaps,
    }


def _cohorts(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_dicts(data.get("beta_cohorts") or data.get("cohorts")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("BC", index)),
                "name": first_text(item.get("name"), item.get("cohort"), default=f"beta cohort {index}"),
                "size": item.get("size", ""),
                "owner": text(item.get("owner")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "name")


def _channels(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_dicts(data.get("feedback_channels") or data.get("channels")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("FC", index)),
                "channel": first_text(item.get("channel"), item.get("name"), default=f"feedback channel {index}"),
                "response_sla": text(item.get("response_sla") or item.get("sla")),
                "owner": text(item.get("owner")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "channel")


def _themes(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(list_of_dicts(data.get("unresolved_themes") or data.get("themes")), start=1):
        rows.append(
            {
                "id": text(item.get("id"), row_id("TH", index)),
                "theme": first_text(item.get("theme"), item.get("name"), default=f"theme {index}"),
                "severity": text(item.get("severity"), "medium").lower(),
                "owner": text(item.get("owner")),
                "evidence_references": evidence(item.get("evidence_references") or item.get("evidence")),
            }
        )
    return sorted_rows(rows, "theme")


def _gaps(cohorts: list[dict[str, Any]], channels: list[dict[str, Any]], owners: list[str]) -> list[dict[str, Any]]:
    gaps = []
    if not cohorts:
        gaps.append(gap("missing_beta_cohorts", "No beta cohorts were provided."))
    if not channels:
        gaps.append(gap("missing_feedback_channels", "No feedback channels were provided."))
    if not owners and not any(row["owner"] for row in [*cohorts, *channels]):
        gaps.append(gap("missing_owner_assignments", "No owner assignments were provided."))
    for row in cohorts:
        if not row["owner"]:
            gaps.append(gap(f"{row['name'].lower().replace(' ', '_')}_missing_owner", f"{row['name']} is missing an owner.", "medium"))
    for row in channels:
        if not row["response_sla"]:
            gaps.append(gap(f"{row['channel'].lower().replace(' ', '_')}_missing_response_sla", f"{row['channel']} is missing a response SLA.", "medium"))
    return gaps
