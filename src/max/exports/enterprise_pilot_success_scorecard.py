"""Enterprise pilot success scorecard export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.enterprise_pilot_success_scorecard.v1"
KIND = "max.enterprise_pilot_success_scorecard"


def build_enterprise_pilot_success_scorecard_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (row["health_score"], row["target_close_date"] or "9999-12-31", row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "enterprise_pilot_success_scorecard", "domain_filter": domain},
        "pilot_rows": rows,
        "summary": _summary(rows),
        "health_distribution": {label: sum(1 for row in rows if row["health_label"] == label) for label in ("red", "yellow", "green")},
        "recommendations": _recommendations(rows),
    }


def render_enterprise_pilot_success_scorecard_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_enterprise_pilot_success_scorecard_markdown(report: dict[str, Any]) -> str:
    lines = ["# Enterprise Pilot Success Scorecard", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Pilots", ""]
    if report.get("pilot_rows"):
        lines.extend(["| Idea | Health | Score | Goal | Metrics | Blockers | Owner | Target | Next Step |", "|------|--------|-------|------|---------|----------|-------|--------|-----------|"])
        for row in report["pilot_rows"]:
            lines.append(f"| {_md(row['title'])} | {row['health_label']} | {row['health_score']} | {_md(row['pilot_goal'])} | {_md(', '.join(row['success_metrics']) or 'None')} | {_md(', '.join(row['blockers']) or 'None')} | {_md(row['owner'])} | {_md(row['target_close_date'] or 'Unknown')} | {_md(row['next_step'])} |")
    else:
        lines.append("- No enterprise pilot metadata available.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    blockers = _list(metadata.get("technical_blockers") or metadata.get("blockers"))
    usage = _score(metadata.get("usage_progress"), default=50)
    engagement = _score(metadata.get("stakeholder_engagement"), default=50)
    security = _security_score(metadata.get("security_status"))
    metrics = _list(metadata.get("success_metrics"))
    score = round(max(0, min(100, usage * 0.35 + engagement * 0.25 + security * 0.25 + (15 if metrics else 0) - len(blockers) * 12)))
    label = "green" if score >= 75 else "yellow" if score >= 50 else "red"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "health_score": score,
        "health_label": label,
        "pilot_goal": _text(metadata.get("pilot_goal") or "Unknown"),
        "success_metrics": metrics,
        "blockers": blockers,
        "owner": _text(metadata.get("owner") or metadata.get("pilot_owner") or "Unassigned"),
        "target_close_date": _text(metadata.get("target_close_date") or metadata.get("close_date")),
        "next_step": _text(metadata.get("next_step") or _next_step(label, blockers)),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pilot_count": len(rows),
        "average_health_score": round(sum(row["health_score"] for row in rows) / len(rows), 1) if rows else 0.0,
        "blocked_pilot_count": sum(1 for row in rows if row["blockers"]),
    }


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture pilot goals, success metrics, usage progress, stakeholder engagement, security status, target close date, and next step."]
    if any(row["health_label"] == "red" for row in rows):
        return ["Review red enterprise pilots with the account team and assign blocker owners."]
    if any(row["health_label"] == "yellow" for row in rows):
        return ["Convert yellow pilot risks into dated next steps before the target close date."]
    return ["Prepare green pilots for conversion and customer proof points."]


def _next_step(label: str, blockers: list[str]) -> str:
    if blockers:
        return f"Resolve {blockers[0]}."
    if label == "green":
        return "Confirm conversion plan."
    return "Refresh pilot plan with owner and date."


def _score(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        number = float(str(value).rstrip("%"))
        return round(max(0, min(100, number)))
    except ValueError:
        text = _text(value).lower()
        if any(word in text for word in ("high", "strong", "healthy", "complete", "engaged")):
            return 85
        if any(word in text for word in ("medium", "partial", "moderate", "in progress")):
            return 60
        if any(word in text for word in ("low", "weak", "blocked", "poor")):
            return 25
        return default


def _security_score(value: Any) -> int:
    text = _text(value).lower()
    if any(word in text for word in ("approved", "complete", "green", "passed")):
        return 90
    if any(word in text for word in ("pending", "review", "yellow", "partial")):
        return 55
    if any(word in text for word in ("blocked", "failed", "red")):
        return 20
    return 50


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return [_text(item) for item in value if _text(item)] if isinstance(value, (list, tuple, set)) else [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
