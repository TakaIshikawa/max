"""Customer migration wave readiness export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.customer_migration_wave_readiness_report.v1"
KIND = "max.customer_migration_wave_readiness_report"


def build_customer_migration_wave_readiness_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (row["wave"].lower(), row["readiness_score"], row["customer"].lower()))
    waves = _waves(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "customer_migration_wave_readiness_report", "domain_filter": domain},
        "summary": _summary(rows, waves),
        "wave_rows": waves,
        "customer_rows": rows,
    }


def render_customer_migration_wave_readiness_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_customer_migration_wave_readiness_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Customer Migration Wave Readiness Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Migration Waves", ""]
    if report.get("wave_rows"):
        lines.extend(["| Wave | Customers | Score | Blockers | Target | Recommendation |", "|------|-----------|-------|----------|--------|----------------|"])
        for row in report["wave_rows"]:
            lines.append(f"| {_md(row['wave'])} | {row['customer_count']} | {row['average_readiness_score']} | {row['blocker_count']} | {_md(row['target_date'])} | {_md(row['launch_recommendation'])} |")
    else:
        lines.append("- No migration wave records found.")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    m = _metadata(unit)
    blockers = _list(m.get("blockers") or m.get("blocker"))
    score = _score(m.get("readiness_score"), blockers)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "wave": _text(m.get("wave") or m.get("migration_wave") or "Unassigned wave"),
        "customer": _text(m.get("customer") or getattr(unit, "title", "Untitled")),
        "owner": _text(m.get("owner") or "Unassigned"),
        "target_date": _text(m.get("target_date") or "unscheduled"),
        "blockers": blockers,
        "readiness_score": score,
        "launch_recommendation": _recommendation(score, blockers),
    }


def _waves(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["wave"]].append(row)
    waves = []
    for wave, items in grouped.items():
        blocker_count = sum(len(row["blockers"]) for row in items)
        avg = round(sum(row["readiness_score"] for row in items) / len(items), 1)
        waves.append({"wave": wave, "customer_count": len(items), "average_readiness_score": avg, "blocker_count": blocker_count, "target_date": min(row["target_date"] for row in items), "launch_recommendation": _recommendation(avg, ["blocked"] if blocker_count else [])})
    return sorted(waves, key=lambda row: (row["blocker_count"] > 0, row["average_readiness_score"], row["wave"].lower()))


def _summary(rows: list[dict[str, Any]], waves: list[dict[str, Any]]) -> dict[str, Any]:
    return {"customer_count": len(rows), "wave_count": len(waves), "blocked_wave_count": sum(1 for row in waves if row["blocker_count"]), "average_readiness_score": round(sum(row["readiness_score"] for row in rows) / len(rows), 1) if rows else 0.0}


def _recommendation(score: float, blockers: list[str]) -> str:
    if blockers:
        return "Do not launch until blockers are cleared."
    if score < 80:
        return "Hold wave for readiness remediation."
    return "Ready for launch."


def _score(value: Any, blockers: list[str]) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 60.0 if blockers else 100.0
    return round(max(0.0, min(score, 100.0)), 1)


def _metadata(unit: Any) -> dict[str, Any]:
    return getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
