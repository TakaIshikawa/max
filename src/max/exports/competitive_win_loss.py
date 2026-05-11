"""Competitive win/loss export for sales outcome analysis."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.competitive_win_loss.v1"
KIND = "max.competitive_win_loss"

_OUTCOME_ORDER = {"won": 0, "lost": 1, "open": 2}
_CSV_FIELDS = [
    "idea_id",
    "title",
    "competitor",
    "outcome",
    "segment",
    "sales_stage",
    "deal_size",
    "win_reason",
    "loss_reason",
]


def build_competitive_win_loss_export(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build win/loss patterns from buildable unit competitive sales metadata."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    opportunities = [row for unit in units for row in _opportunity_rows(unit)]
    opportunities.sort(
        key=lambda row: (
            row["competitor"].lower(),
            _OUTCOME_ORDER[row["outcome"]],
            row["segment"],
            row["idea_id"],
        )
    )
    summary = _summary(opportunities, len(units))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "competitive_win_loss",
            "domain_filter": domain,
            "defaults": {
                "outcome": "open",
                "segment": "unknown",
                "sales_stage": "unknown",
                "deal_size": 0.0,
            },
        },
        "opportunities": opportunities,
        "competitor_rollups": _competitor_rollups(opportunities),
        "reason_rollups": _reason_rollups(opportunities),
        "summary": summary,
        "recommendations": _recommendations(opportunities, summary),
    }


def render_competitive_win_loss_markdown(report: dict[str, Any]) -> str:
    """Render competitive win/loss analysis as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Competitive Win/Loss",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Opportunities: {summary.get('opportunity_count', 0)}",
        f"- Competitors: {summary.get('competitor_count', 0)}",
        f"- Won: {summary.get('won_count', 0)}",
        f"- Lost: {summary.get('lost_count', 0)}",
        f"- Open: {summary.get('open_count', 0)}",
        f"- Win rate: {summary.get('win_rate', 0.0):.1f}%",
        f"- Total deal value: ${summary.get('total_deal_value', 0.0):,.0f}",
        "",
        "## Opportunities",
        "",
    ]
    if report.get("opportunities"):
        lines.extend([
            "| Competitor | Idea | Outcome | Segment | Stage | Deal Value | Reason |",
            "|------------|------|---------|---------|-------|------------|--------|",
        ])
        for row in report["opportunities"]:
            reason = row["win_reason"] if row["outcome"] == "won" else row["loss_reason"]
            lines.append(
                f"| {_md(row['competitor'])} | {_md(row['title'])} | {row['outcome']} | "
                f"{_md(row['segment'])} | {_md(row['sales_stage'])} | "
                f"${row['deal_size']:,.0f} | {_md(reason or 'Needs discovery')} |"
            )
    else:
        lines.append(
            "- No competitive opportunities found. Add competitors, deal_outcome, "
            "deal_size, and win/loss reasons to buildable unit metadata."
        )

    lines.extend(["", "## Competitor Rollup", ""])
    if report.get("competitor_rollups"):
        lines.extend([
            "| Competitor | Opportunities | Wins | Losses | Open | Win Rate | Deal Value |",
            "|------------|---------------|------|--------|------|----------|------------|",
        ])
        for row in report["competitor_rollups"]:
            lines.append(
                f"| {_md(row['competitor'])} | {row['opportunity_count']} | {row['win_count']} | "
                f"{row['loss_count']} | {row['open_count']} | {row['win_rate']:.1f}% | "
                f"${row['total_deal_value']:,.0f} |"
            )
    else:
        lines.append("- No competitor rollups available.")

    lines.extend(["", "## Reason Rollup", ""])
    for label, key in (("Win reasons", "win_reasons"), ("Loss reasons", "loss_reasons")):
        lines.extend([f"### {label}", ""])
        reasons = report.get("reason_rollups", {}).get(key, [])
        if reasons:
            lines.extend(["| Reason | Opportunities | Deal Value |", "|--------|---------------|------------|"])
            for row in reasons:
                lines.append(f"| {_md(row['reason'])} | {row['opportunity_count']} | ${row['total_deal_value']:,.0f} |")
            lines.append("")
        else:
            lines.extend(["- No reasons captured.", ""])

    lines.extend(["## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def render_competitive_win_loss_json(report: dict[str, Any]) -> str:
    """Render competitive win/loss analysis as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_competitive_win_loss_csv(report: dict[str, Any]) -> str:
    """Render competitive win/loss opportunity rows as CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for row in report.get("opportunities", []):
        writer.writerow({field: row.get(field) for field in _CSV_FIELDS})
    return output.getvalue()


def _opportunity_rows(unit: Any) -> list[dict[str, Any]]:
    metadata = _metadata(unit)
    competitors = _competitors(metadata)
    if not competitors:
        return []

    outcome = _normalize_outcome(_string(metadata, ["deal_outcome", "outcome", "status"], "open"))
    deal_size = _non_negative_float(_number(metadata, ["deal_size", "deal_value", "annual_contract_value", "acv"], 0.0))
    segment = _string(metadata, ["segment", "buyer_segment", "customer_segment"], "unknown").lower()
    sales_stage = _string(metadata, ["sales_stage", "pipeline_stage", "stage"], "unknown").lower()
    win_reason = _string(metadata, ["win_reason", "won_reason"], "")
    loss_reason = _string(metadata, ["loss_reason", "lost_reason"], "")

    return [
        {
            "idea_id": str(getattr(unit, "id", "")),
            "title": str(getattr(unit, "title", "Untitled")),
            "competitor": competitor,
            "outcome": outcome,
            "segment": segment or "unknown",
            "sales_stage": sales_stage or "unknown",
            "deal_size": deal_size,
            "win_reason": win_reason if outcome == "won" else "",
            "loss_reason": loss_reason if outcome == "lost" else "",
        }
        for competitor in competitors
    ]


def _competitor_rollups(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "opportunity_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "open_count": 0,
            "total_deal_value": 0.0,
        }
    )
    for row in opportunities:
        group = groups[row["competitor"].lower()]
        group.setdefault("competitor", row["competitor"])
        group["opportunity_count"] += 1
        if row["outcome"] == "won":
            group["win_count"] += 1
        elif row["outcome"] == "lost":
            group["loss_count"] += 1
        else:
            group["open_count"] += 1
        group["total_deal_value"] += row["deal_size"]

    rollups: list[dict[str, Any]] = []
    for values in groups.values():
        closed_count = values["win_count"] + values["loss_count"]
        rollups.append({
            "competitor": values["competitor"],
            "opportunity_count": values["opportunity_count"],
            "win_count": values["win_count"],
            "loss_count": values["loss_count"],
            "open_count": values["open_count"],
            "win_rate": _percentage(values["win_count"], closed_count),
            "total_deal_value": round(values["total_deal_value"], 2),
        })
    return sorted(rollups, key=lambda row: (-row["opportunity_count"], row["competitor"].lower()))


def _reason_rollups(opportunities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "win_reasons": _rollup_reasons(opportunities, "won", "win_reason"),
        "loss_reasons": _rollup_reasons(opportunities, "lost", "loss_reason"),
    }


def _rollup_reasons(opportunities: list[dict[str, Any]], outcome: str, field: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"opportunity_count": 0, "total_deal_value": 0.0})
    for row in opportunities:
        if row["outcome"] != outcome:
            continue
        reason = row.get(field) or "Unspecified"
        group = groups[reason]
        group["opportunity_count"] += 1
        group["total_deal_value"] += row["deal_size"]

    return [
        {"reason": reason, "opportunity_count": values["opportunity_count"], "total_deal_value": round(values["total_deal_value"], 2)}
        for reason, values in sorted(
            groups.items(),
            key=lambda item: (-item[1]["opportunity_count"], -item[1]["total_deal_value"], item[0].lower()),
        )
    ]


def _summary(opportunities: list[dict[str, Any]], unit_count: int) -> dict[str, Any]:
    won_count = sum(1 for row in opportunities if row["outcome"] == "won")
    lost_count = sum(1 for row in opportunities if row["outcome"] == "lost")
    open_count = sum(1 for row in opportunities if row["outcome"] == "open")
    closed_count = won_count + lost_count
    return {
        "unit_count": unit_count,
        "opportunity_count": len(opportunities),
        "competitor_count": len({row["competitor"] for row in opportunities}),
        "won_count": won_count,
        "lost_count": lost_count,
        "open_count": open_count,
        "closed_count": closed_count,
        "win_rate": _percentage(won_count, closed_count),
        "total_deal_value": round(sum(row["deal_size"] for row in opportunities), 2),
        "average_deal_value": round(sum(row["deal_size"] for row in opportunities) / len(opportunities), 2) if opportunities else 0.0,
    }


def _recommendations(opportunities: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not opportunities:
        return [
            "Add competitor names and deal outcomes to buildable unit metadata before reviewing win/loss patterns.",
            "Capture win_reason and loss_reason fields on closed opportunities to make the report actionable.",
        ]

    recommendations: list[str] = []
    missing_reasons = sum(
        1
        for row in opportunities
        if row["outcome"] in {"won", "lost"} and not (row["win_reason"] or row["loss_reason"])
    )
    if missing_reasons:
        recommendations.append("Backfill win and loss reasons for closed competitive opportunities.")
    if summary["lost_count"] > summary["won_count"]:
        recommendations.append("Review loss reasons by competitor and update battlecards for recurring gaps.")
    if summary["open_count"]:
        recommendations.append("Use open competitive opportunities to validate active objection handling before close.")
    if not recommendations:
        recommendations.append("Continue tracking competitive outcomes by segment and competitor.")
    return recommendations


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    extra = getattr(unit, "extra", None)
    return extra if isinstance(extra, dict) else {}


def _competitors(metadata: dict[str, Any]) -> list[str]:
    raw = None
    for key in ("competitors", "competitor", "competitive_alternatives", "alternative"):
        if key in metadata:
            raw = metadata[key]
            break
    names = _string_list(raw)
    deduped: dict[str, str] = {}
    for name in names:
        normalized = " ".join(name.split())
        if normalized:
            deduped.setdefault(normalized.lower(), normalized)
    return [deduped[key] for key in sorted(deduped)]


def _string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    if isinstance(value, dict):
        if "name" in value:
            return [str(value["name"]).strip()]
        return [str(key).strip() for key in value if str(key).strip()]
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                if "name" in item:
                    result.append(str(item["name"]).strip())
            else:
                result.extend(_string_list(item))
        return [item for item in result if item]
    return [str(value).strip()]


def _normalize_outcome(value: Any) -> str:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"won", "win", "closed_won", "closedwon", "success"}:
        return "won"
    if normalized in {"lost", "loss", "closed_lost", "closedlost", "failed", "churned"}:
        return "lost"
    return "open"


def _string(metadata: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        if key in metadata and metadata[key] not in (None, ""):
            return str(metadata[key]).strip()
    sales = metadata.get("sales")
    if isinstance(sales, dict):
        for key in keys:
            if key in sales and sales[key] not in (None, ""):
                return str(sales[key]).strip()
    return default


def _number(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        if key in metadata:
            return _coerce_float(metadata[key], default)
    sales = metadata.get("sales")
    if isinstance(sales, dict):
        for key in keys:
            if key in sales:
                return _coerce_float(sales[key], default)
    return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return default


def _non_negative_float(value: float) -> float:
    return round(max(value, 0.0), 2)


def _percentage(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
