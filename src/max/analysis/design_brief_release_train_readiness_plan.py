"""Deterministic release train readiness plans for design brief mappings."""

from __future__ import annotations

import json
from typing import Any

from max.analysis._design_brief_plan_common import join_text, list_values, text

KIND = "max.design_brief.release_train_readiness_plan"
SCHEMA_VERSION = "max.design_brief.release_train_readiness_plan.v1"


def build_design_brief_release_train_readiness_plan(brief: dict[str, Any]) -> dict[str, Any]:
    release_train = _release_train(brief)
    scope = _release_scope(brief)
    gates = _readiness_gates(brief)
    owners = _owner_coverage(brief)
    rollback = _rollback_evidence(brief)
    warnings = _missing_input_warnings(release_train, scope, gates, owners, rollback)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(brief),
        "design_brief": _brief_block(brief),
        "summary": {
            "recommendation_status": "ready_for_go_no_go_review"
            if not warnings
            else "blocked_pending_release_inputs",
            "release_train": release_train["name"],
            "target_date": release_train["target_date"],
            "readiness_gate_count": len(gates),
            "missing_input_count": len(warnings),
        },
        "release_train": release_train,
        "release_scope": scope,
        "readiness_gates": gates,
        "owner_coverage": owners,
        "rollback_evidence": rollback,
        "recommendation": _recommendation(warnings),
        "missing_input_warnings": warnings,
    }


def render_design_brief_release_train_readiness_plan(
    report: dict[str, Any], fmt: str = "json"
) -> str:
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt != "markdown":
        raise ValueError(f"Unsupported release train readiness plan format: {fmt}")
    brief = report["design_brief"]
    lines = [
        f"# Release Train Readiness Plan: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Recommendation: `{report['recommendation']['status']}`",
    ]
    for key, title in (
        ("release_scope", "Release Scope"),
        ("readiness_gates", "Readiness Gates"),
        ("owner_coverage", "Owner Coverage"),
        ("rollback_evidence", "Rollback Evidence"),
        ("missing_input_warnings", "Missing Input Warnings"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = report.get(key) or []
        if not rows:
            lines.append("- None")
        for row in rows:
            label = row.get("name") or row.get("owner") or row.get("id")
            detail = (
                row.get("action")
                or row.get("description")
                or row.get("evidence")
                or row.get("status")
            )
            lines.append(f"- **{row['id']} {label}**: {detail}")
    return "\n".join(lines).rstrip() + "\n"


def release_train_readiness_plan_filename(
    brief: dict[str, Any], fmt: str = "markdown"
) -> str:
    extension = {"json": "json", "markdown": "md"}.get(fmt, "md")
    return (
        f"{_filename_part(text(brief.get('id'), 'design-brief'))}-"
        f"{_filename_part(text(brief.get('title'), 'Release Train Readiness Plan'))}-"
        f"release-train-readiness-plan.{extension}"
    )


def _release_train(brief: dict[str, Any]) -> dict[str, str]:
    name = _first_text(
        brief.get("release_train_name"),
        brief.get("train_name"),
        brief.get("release_train"),
        brief.get("release_name"),
    )
    target_date = _first_text(
        brief.get("release_train_date"),
        brief.get("release_date"),
        brief.get("target_release_date"),
        brief.get("target_date"),
        brief.get("date"),
    )
    return {
        "id": "RT1",
        "name": name or "unnamed release train",
        "target_date": target_date or "unscheduled",
        "description": text(brief.get("release_train_summary"), "Release train readiness review."),
    }


def _release_scope(brief: dict[str, Any]) -> list[dict[str, str]]:
    values = _dedupe(
        [
            *list_values(brief.get("release_scope")),
            *list_values(brief.get("scope")),
            *list_values(brief.get("mvp_scope")),
            *list_values(brief.get("features")),
        ]
    )
    if not values:
        return []
    return [
        {
            "id": f"S{idx}",
            "name": f"Scope item {idx}",
            "description": value,
            "owner": _first_text(brief.get("release_owner"), brief.get("owner")) or "Release owner",
        }
        for idx, value in enumerate(values, 1)
    ]


def _readiness_gates(brief: dict[str, Any]) -> list[dict[str, str]]:
    values = _dedupe(
        [
            *_rows_as_text(brief.get("dependency_gates")),
            *_rows_as_text(brief.get("dependencies")),
            *_rows_as_text(brief.get("readiness_gates")),
            *_rows_as_text(brief.get("launch_dependencies")),
        ]
    )
    return [
        {
            "id": f"G{idx}",
            "name": value,
            "owner": _owner_for_row(value, brief) or "Dependency owner",
            "status": _status_for_row(value),
            "action": f"Confirm gate before go/no-go: {value}",
        }
        for idx, value in enumerate(values, 1)
    ]


def _owner_coverage(brief: dict[str, Any]) -> list[dict[str, str]]:
    owners = _dedupe(
        [
            *_rows_as_text(brief.get("go_no_go_owners")),
            *_rows_as_text(brief.get("approval_owners")),
            *_rows_as_text(brief.get("owners")),
        ]
    )
    return [
        {
            "id": f"O{idx}",
            "owner": owner,
            "name": "Go/no-go owner",
            "coverage": "go_no_go",
            "action": f"{owner} signs off on release train readiness.",
        }
        for idx, owner in enumerate(owners, 1)
    ]


def _rollback_evidence(brief: dict[str, Any]) -> list[dict[str, str]]:
    values = _dedupe(
        [
            *_rows_as_text(brief.get("rollback_rehearsal_status")),
            *_rows_as_text(brief.get("rollback_rehearsal")),
            *_rows_as_text(brief.get("rollback_plan")),
            *_rows_as_text(brief.get("rollback_evidence")),
        ]
    )
    return [
        {
            "id": f"R{idx}",
            "name": "Rollback rehearsal",
            "status": _status_for_row(value),
            "evidence": value,
            "action": f"Keep rollback rehearsal evidence current: {value}",
        }
        for idx, value in enumerate(values, 1)
    ]


def _missing_input_warnings(
    release_train: dict[str, str],
    scope: list[dict[str, str]],
    gates: list[dict[str, str]],
    owners: list[dict[str, str]],
    rollback: list[dict[str, str]],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if release_train["name"] == "unnamed release train":
        warnings.append({"id": "missing_train_name", "description": "Release train name is missing."})
    if release_train["target_date"] == "unscheduled":
        warnings.append({"id": "missing_train_date", "description": "Release train target date is missing."})
    if not scope:
        warnings.append({"id": "missing_release_scope", "description": "Release scope is missing."})
    if not gates:
        warnings.append({"id": "missing_dependency_gates", "description": "Dependency gates are missing."})
    if not owners:
        warnings.append({"id": "missing_go_no_go_owners", "description": "Go/no-go owners are missing."})
    if not rollback:
        warnings.append({"id": "missing_rollback_rehearsal", "description": "Rollback rehearsal evidence is missing."})
    return warnings


def _recommendation(warnings: list[dict[str, str]]) -> dict[str, str]:
    status = "ready_for_go_no_go_review" if not warnings else "blocked_pending_release_inputs"
    return {
        "status": status,
        "rationale": f"{len(warnings)} release train input warning(s) remain.",
        "next_action": "Run go/no-go review." if not warnings else "Close missing release train inputs.",
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


def _rows_as_text(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [join_text([value.get("name"), value.get("status"), value.get("owner")], "")]
    rows = []
    for item in list_values(value):
        rows.append(text(item))
    return [row for row in rows if row]


def _owner_for_row(value: str, brief: dict[str, Any]) -> str:
    owners = _rows_as_text(brief.get("dependency_owners"))
    return owners[0] if owners else ("Engineering owner" if "engineering" in value.lower() else "")


def _status_for_row(value: str) -> str:
    lowered = value.lower()
    if any(word in lowered for word in ("missing", "blocked", "overdue", "not ready")):
        return "blocked"
    if any(word in lowered for word in ("ready", "done", "complete", "passed")):
        return "ready"
    return "needs_review"


def _first_text(*values: Any) -> str:
    return next((cleaned for value in values if (cleaned := text(value))), "")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = text(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _filename_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part) or "design-brief"
