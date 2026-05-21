"""Deterministic training content gap plans for design brief mappings."""

from __future__ import annotations

import json
from typing import Any

from max.analysis._design_brief_plan_common import dedupe, join_text, list_values, text

KIND = "max.design_brief.training_content_gap_plan"
SCHEMA_VERSION = "max.design_brief.training_content_gap_plan.v1"

_MISSING_STATUSES = {"missing", "not_started", "not started", "gap", "none"}


def build_design_brief_training_content_gap_plan(brief: dict[str, Any]) -> dict[str, Any]:
    rows = _gap_rows(brief)
    blockers = [row for row in rows if row["launch_blocker"]]
    unowned = [row for row in rows if row["owner"] == "Training owner"]
    missing_critical = [
        row for row in rows if row["coverage_status"] in _MISSING_STATUSES and row["criticality"] == "critical"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(brief),
        "design_brief": _brief_block(brief),
        "summary": {
            "readiness_status": "ready_for_training_launch" if not blockers and not missing_critical else "blocked_pending_training_content",
            "role_count": len({row["role"] for row in rows}),
            "asset_count": len(rows),
            "missing_critical_asset_count": len(missing_critical),
            "unowned_content_count": len(unowned),
            "overdue_blocker_count": sum(1 for row in blockers if row["due_window"] == "overdue"),
            "coverage_by_role": _coverage_by_role(rows),
        },
        "training_gap_rows": rows,
        "blocker_priorities": blockers,
        "launch_blockers": blockers,
        "unowned_content": unowned,
        "recommendation": _recommendation(blockers, missing_critical),
    }


def render_design_brief_training_content_gap_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported training content gap plan format: {fmt}")

    brief = report["design_brief"]
    summary = report["summary"]
    lines = [
        f"# Training Content Gap Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Recommendation: `{report['recommendation']['status']}`",
        "",
        "## Readiness Summary",
        "",
        f"- Readiness status: {summary['readiness_status']}",
        f"- Roles: {summary['role_count']}",
        f"- Assets: {summary['asset_count']}",
        f"- Missing critical assets: {summary['missing_critical_asset_count']}",
        f"- Unowned content: {summary['unowned_content_count']}",
        f"- Overdue blockers: {summary['overdue_blocker_count']}",
        "",
        "## Training Gaps",
        "",
    ]
    if not report["training_gap_rows"]:
        lines.append("- None")
    for row in report["training_gap_rows"]:
        lines.append(
            f"- **{row['id']} {row['role']} {row['asset_type']}**: "
            f"coverage: {row['coverage_status']}; owner: {row['owner']}; "
            f"due: {row['due_window']}; blocker: {row['launch_blocker']}; "
            f"evidence: {join_text(row['evidence_refs'], 'missing')}"
        )

    lines.extend(["", "## Launch Blockers", ""])
    if not report["launch_blockers"]:
        lines.append("- None")
    for row in report["launch_blockers"]:
        lines.append(f"- **{row['id']} {row['role']}**: {row['action']}")

    lines.extend(["", "## Unowned Content", ""])
    if not report["unowned_content"]:
        lines.append("- None")
    for row in report["unowned_content"]:
        lines.append(f"- **{row['id']} {row['role']}**: Assign owner for {row['asset_type']}.")
    return "\n".join(lines).rstrip() + "\n"


def training_content_gap_plan_filename(brief: dict[str, Any], fmt: str = "markdown") -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(text(brief.get('id'), 'design-brief'))}-"
        f"{_filename_part(text(brief.get('title'), 'Training Content Gap Plan'))}-"
        f"training-content-gap-plan.{extension}"
    )


def _gap_rows(brief: dict[str, Any]) -> list[dict[str, Any]]:
    assets = _asset_rows(brief)
    if not assets:
        assets = [{}]
    rows = [_normalize_asset(row, idx) for idx, row in enumerate(assets, 1)]
    return sorted(
        rows,
        key=lambda row: (
            not row["launch_blocker"],
            row["role"].lower(),
            row["asset_type"].lower(),
            row["id"],
        ),
    )


def _asset_rows(brief: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "required_training_assets",
        "training_assets",
        "training_content",
        "current_coverage",
    ):
        value = brief.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"asset": item} for item in value]
        if isinstance(value, dict):
            return [value]
    roles = list_values(brief.get("target_roles"))
    return [{"role": role} for role in roles]


def _normalize_asset(row: dict[str, Any], idx: int) -> dict[str, Any]:
    role = text(row.get("role") or row.get("target_role") or row.get("audience"), f"Target role {idx}")
    asset_type = text(row.get("asset_type") or row.get("type"), "training module")
    coverage_status = _coverage_status(row.get("coverage_status") or row.get("status"))
    criticality = _criticality(row.get("criticality") or row.get("priority"))
    evidence_refs = dedupe(
        [
            *list_values(row.get("evidence_refs")),
            *list_values(row.get("evidence")),
            *list_values(row.get("source_ids")),
        ]
    )
    due_window = text(row.get("due_window") or row.get("due") or row.get("target"), _due_window(criticality, coverage_status))
    launch_blocker = _launch_blocker(row, criticality, coverage_status, due_window)
    return {
        "id": text(row.get("id") or row.get("asset_id"), f"TCG{idx}"),
        "role": role,
        "asset": text(row.get("asset") or row.get("name") or row.get("title"), f"{role} {asset_type}"),
        "asset_type": asset_type,
        "coverage_status": coverage_status,
        "criticality": criticality,
        "owner": text(row.get("owner") or row.get("assignee"), "Training owner"),
        "due_window": due_window,
        "launch_blocker": launch_blocker,
        "evidence_refs": evidence_refs,
        "action": text(row.get("action"), f"Close {asset_type} coverage gap for {role}."),
    }


def _coverage_status(value: Any) -> str:
    status = text(value, "missing").lower().replace("_", " ")
    if status in {"complete", "covered", "ready", "done"}:
        return "covered"
    if status in {"partial", "in progress", "draft"}:
        return "partial"
    if status in {"not started", "missing", "gap", "none"}:
        return "missing"
    return status.replace(" ", "_")


def _criticality(value: Any) -> str:
    lowered = text(value, "standard").lower()
    return "critical" if "critical" in lowered or "high" in lowered else "standard"


def _due_window(criticality: str, coverage_status: str) -> str:
    if coverage_status == "covered":
        return "complete"
    return "launch minus 1 week" if criticality == "critical" else "launch minus 2 weeks"


def _launch_blocker(
    row: dict[str, Any], criticality: str, coverage_status: str, due_window: str
) -> bool:
    explicit = row.get("launch_blocker") if "launch_blocker" in row else row.get("blocker")
    if isinstance(explicit, bool):
        return explicit
    if text(explicit).lower() in {"true", "yes", "blocker"}:
        return True
    return criticality == "critical" and coverage_status != "covered" or due_window == "overdue"


def _coverage_by_role(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    coverage: dict[str, dict[str, int]] = {}
    for row in rows:
        role = row["role"]
        coverage.setdefault(role, {"covered": 0, "partial": 0, "missing": 0, "other": 0})
        key = row["coverage_status"] if row["coverage_status"] in coverage[role] else "other"
        coverage[role][key] += 1
    return {role: coverage[role] for role in sorted(coverage)}


def _recommendation(
    blockers: list[dict[str, Any]], missing_critical: list[dict[str, Any]]
) -> dict[str, str]:
    status = "ready_for_training_launch" if not blockers and not missing_critical else "blocked_pending_training_content"
    return {
        "status": status,
        "rationale": f"{len(blockers)} launch blocker(s) and {len(missing_critical)} missing critical asset(s) remain.",
        "next_action": "Publish launch training content." if status == "ready_for_training_launch" else "Close launch-blocking training gaps.",
    }


def _source(brief: dict[str, Any]) -> dict[str, str]:
    return {
        "project": "max",
        "entity_type": "design_brief",
        "id": text(brief.get("id"), "design-brief"),
        "generated_at": text(brief.get("updated_at") or brief.get("created_at")),
    }


def _brief_block(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": text(brief.get("id"), "design-brief"),
        "title": text(brief.get("title"), "Design brief"),
        "domain": text(brief.get("domain")),
        "theme": text(brief.get("theme")),
        "source_idea_ids": list_values(brief.get("source_idea_ids")),
    }


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
