"""Pilot exit criteria scorecard export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.pilot_exit_criteria_scorecard.v1"
KIND = "max.pilot_exit_criteria_scorecard"

_STATUS_ORDER = {"blocked": 0, "at_risk": 1, "on_track": 2, "complete": 3}


def build_pilot_exit_criteria_scorecard_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_scorecard_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["closeout_status"]], row["completion_percent"], row["account"], row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "pilot_exit_criteria_scorecard", "domain_filter": domain},
        "summary": summary,
        "scorecard_rows": rows,
        "unmet_criteria": _unmet_criteria(rows),
        "recommended_actions": _recommended_actions(rows, summary),
    }


def render_pilot_exit_criteria_scorecard_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_pilot_exit_criteria_scorecard_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Pilot Exit Criteria Scorecard",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Pilots analyzed: {summary.get('pilot_count', 0)}",
        f"- Blocked: {summary.get('status_counts', {}).get('blocked', 0)}",
        f"- At risk: {summary.get('status_counts', {}).get('at_risk', 0)}",
        f"- On track: {summary.get('status_counts', {}).get('on_track', 0)}",
        f"- Complete: {summary.get('status_counts', {}).get('complete', 0)}",
        "",
        "## Scorecard Rows",
        "",
    ]
    if report.get("scorecard_rows"):
        lines.extend(["| Account | Status | Completion | Adoption | Technical | Commercial | Owner | Action |", "|---------|--------|------------|----------|-----------|------------|-------|--------|"])
        for row in report["scorecard_rows"]:
            lines.append(
                f"| {_md(row['account'])} | {row['closeout_status']} | {row['completion_percent']:.1f}% | {row['adoption_progress_percent']:.1f}% | "
                f"{_md(row['technical_validation_status'])} | {_md(row['commercial_next_step'])} | {_md(row['owner'])} | {_md(row['recommended_action'])} |"
            )
    else:
        lines.append("- No pilot scorecard records found.")
    lines.extend(["", "## Recommended Actions", ""])
    for action in report.get("recommended_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines).rstrip() + "\n"


def _scorecard_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    criteria = _list(metadata.get("exit_criteria"))
    met = _list(metadata.get("met_criteria"))
    met_set = {item.lower() for item in met}
    unmet = [item for item in criteria if item.lower() not in met_set]
    completion = round((len(criteria) - len(unmet)) / len(criteria) * 100, 1) if criteria else 0.0
    adoption_target = _number(metadata.get("adoption_target"))
    current_adoption = _number(metadata.get("current_adoption"))
    adoption_progress = round((current_adoption / adoption_target) * 100, 1) if adoption_target and current_adoption is not None and adoption_target > 0 else 0.0
    technical = _text(metadata.get("technical_validation_status")).lower() or "unknown"
    commercial = _text(metadata.get("commercial_next_step"))
    blockers = _list(metadata.get("blockers"))
    if blockers:
        status = "blocked"
    elif completion >= 100 and adoption_progress >= 100 and technical in {"passed", "complete", "approved", "validated"} and commercial:
        status = "complete"
    elif completion >= 75 and adoption_progress >= 75 and technical not in {"failed", "blocked"}:
        status = "on_track"
    else:
        status = "at_risk"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account": _text(metadata.get("account") or getattr(unit, "title", "Untitled")),
        "pilot_start_date": _text(metadata.get("pilot_start_date")) or None,
        "pilot_end_date": _text(metadata.get("pilot_end_date")) or None,
        "exit_criteria": criteria,
        "met_criteria": met,
        "unmet_criteria": unmet,
        "success_metrics": _list(metadata.get("success_metrics")),
        "adoption_target": adoption_target,
        "current_adoption": current_adoption,
        "adoption_progress_percent": adoption_progress,
        "completion_percent": completion,
        "technical_validation_status": technical,
        "commercial_next_step": commercial or "Unassigned",
        "blockers": blockers,
        "owner": _text(metadata.get("owner")) or "Unassigned",
        "closeout_status": status,
        "recommended_action": _recommended_action(status, unmet, blockers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pilot_count": len(rows),
        "status_counts": {status: sum(1 for row in rows if row["closeout_status"] == status) for status in ("blocked", "at_risk", "on_track", "complete")},
        "average_completion_percent": round(sum(row["completion_percent"] for row in rows) / len(rows), 1) if rows else 0.0,
    }


def _unmet_criteria(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        for criterion in row["unmet_criteria"]:
            counts[criterion] = counts.get(criterion, 0) + 1
    return [{"criterion": criterion, "count": count} for criterion, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _recommended_actions(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Capture pilot exit criteria, adoption targets, validation status, commercial next step, blockers, and owner."]
    actions = []
    if summary["status_counts"]["blocked"]:
        actions.append("Resolve pilot blockers before closeout review.")
    if summary["status_counts"]["at_risk"]:
        actions.append("Create recovery plans for at-risk pilots with unmet criteria or weak adoption.")
    if not actions:
        actions.append("Prepare closeout package for pilots that are on track or complete.")
    return actions


def _recommended_action(status: str, unmet: list[str], blockers: list[str]) -> str:
    if blockers:
        return "Resolve blockers before pilot exit."
    if unmet:
        return "Close unmet exit criteria before commercial handoff."
    if status == "complete":
        return "Proceed to closeout and commercial next step."
    return "Track adoption and validation through pilot closeout."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
