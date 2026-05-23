"""Partner referral pipeline coverage export report."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.partner_referral_pipeline_coverage_report.v1"
KIND = "max.partner_referral_pipeline_coverage_report"

_STAGE_ORDER = {"referred": 0, "qualified": 1, "proposal": 2, "closed_won": 3, "closed_lost": 4}


def build_partner_referral_pipeline_coverage_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (row["partner"].lower(), _STAGE_ORDER.get(row["stage"], 9), row["opportunity"].lower()))
    partner_rows = _partners(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "partner_referral_pipeline_coverage_report", "domain_filter": domain},
        "summary": _summary(rows, partner_rows),
        "partner_rows": partner_rows,
        "referral_rows": rows,
        "conversion_gaps": [row for row in partner_rows if row["conversion_rate"] < 0.25 and row["referral_count"]],
        "stale_referrals": [row for row in rows if row["stale"]],
        "recommended_actions": _actions(rows, partner_rows),
    }


def render_partner_referral_pipeline_coverage_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_partner_referral_pipeline_coverage_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Partner Referral Pipeline Coverage Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Partner Coverage", ""]
    if report.get("partner_rows"):
        lines.extend(["| Partner | Referrals | Won | Conversion | Stale | Action |", "|---------|-----------|-----|------------|-------|--------|"])
        for row in report["partner_rows"]:
            lines.append(f"| {_md(row['partner'])} | {row['referral_count']} | {row['won_count']} | {row['conversion_rate']} | {row['stale_count']} | {_md(row['recommended_action'])} |")
    else:
        lines.append("- No partner referral records found.")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    m = _metadata(unit)
    stage = _stage(m.get("stage"))
    age = _int(m.get("age_days") or m.get("days_in_stage"))
    stale = _bool(m.get("stale")) or age > 30
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "partner": _text(m.get("partner") or "Unassigned partner"),
        "opportunity": _text(m.get("opportunity") or getattr(unit, "title", "Untitled")),
        "stage": stage,
        "age_days": age,
        "stale": stale,
        "owner": _text(m.get("owner") or "Unassigned"),
        "enablement_action": _text(m.get("enablement_action") or _action(stage, stale, 0.0)),
    }


def _partners(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["partner"]].append(row)
    result = []
    for partner, items in grouped.items():
        won = sum(1 for row in items if row["stage"] == "closed_won")
        rate = round(won / len(items), 3) if items else 0.0
        stale = sum(1 for row in items if row["stale"])
        result.append({"partner": partner, "referral_count": len(items), "won_count": won, "conversion_rate": rate, "stage_counts": {stage: sum(1 for row in items if row["stage"] == stage) for stage in _STAGE_ORDER}, "stale_count": stale, "recommended_action": _action("partner", stale > 0, rate)})
    return sorted(result, key=lambda row: (-row["stale_count"], row["conversion_rate"], row["partner"].lower()))


def _summary(rows: list[dict[str, Any]], partners: list[dict[str, Any]]) -> dict[str, Any]:
    return {"partner_count": len(partners), "referral_count": len(rows), "stale_referral_count": sum(1 for row in rows if row["stale"]), "closed_won_count": sum(1 for row in rows if row["stage"] == "closed_won")}


def _actions(rows: list[dict[str, Any]], partners: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture partner, opportunity, stage, and age for referral pipeline tracking."]
    actions = []
    if any(row["stale"] for row in rows):
        actions.append("Refresh stale referrals with partner owners.")
    if any(row["conversion_rate"] < 0.25 and row["referral_count"] for row in partners):
        actions.append("Schedule enablement for low-conversion partner cohorts.")
    return actions or ["Maintain partner referral review cadence."]


def _action(stage: str, stale: bool, rate: float) -> str:
    if stale:
        return "Refresh referral next step and partner owner."
    if rate and rate < 0.25:
        return "Run partner enablement for low conversion."
    return "Maintain referral motion."


def _stage(value: Any) -> str:
    text = _text(value).lower().replace(" ", "_").replace("-", "_")
    return text if text in _STAGE_ORDER else "referred"


def _metadata(unit: Any) -> dict[str, Any]:
    return getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "stale"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
