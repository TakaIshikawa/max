"""Roadmap prioritization export for ranked planning decisions."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.roadmap_prioritization.v1"
KIND = "max.roadmap_prioritization"

_FIELDS = ["rank", "idea_id", "title", "target_quarter", "impact_score", "effort_score", "confidence_score", "strategic_alignment", "customer_requests", "revenue_potential", "priority_score", "priority_band"]


def build_roadmap_prioritization_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (-row["priority_score"], row["target_quarter"], row["title"], row["idea_id"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "roadmap_prioritization", "domain_filter": domain},
        "summary": {"idea_count": len(rows), "top_priority_count": sum(1 for row in rows if row["priority_band"] == "high")},
        "quarter_rollups": _quarter_rollups(rows),
        "ranked_items": rows,
    }


def render_roadmap_prioritization_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Roadmap Prioritization",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Top Priorities",
        "",
        "| Rank | Idea | Quarter | Score | Band |",
        "|------|------|---------|-------|------|",
    ]
    for row in report.get("ranked_items", [])[:10]:
        lines.append(f"| {row['rank']} | {row['title']} | {row['target_quarter']} | {row['priority_score']:.1f} | {row['priority_band']} |")
    lines.extend(["", "## Quarter Summary", "", "| Quarter | Items | Avg Score | Revenue Potential | Customer Requests |", "|---------|-------|-----------|-------------------|-------------------|"])
    for row in report.get("quarter_rollups", []):
        lines.append(f"| {row['target_quarter']} | {row['item_count']} | {row['average_priority_score']:.1f} | {row['revenue_potential']:.1f} | {row['customer_requests']} |")
    return "\n".join(lines).rstrip() + "\n"


def render_roadmap_prioritization_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_roadmap_prioritization_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("ranked_items", []):
        writer.writerow({field: row.get(field) for field in _FIELDS})
    return output.getvalue()


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    impact = _number(metadata, "impact_score", 0.0)
    effort = max(_number(metadata, "effort_score", 1.0), 1.0)
    confidence = _number(metadata, "confidence_score", 0.5)
    alignment = _number(metadata, "strategic_alignment", 0.0)
    requests = _number(metadata, "customer_requests", 0.0)
    revenue = _number(metadata, "revenue_potential", 0.0)
    score = (impact * confidence * 12) + (alignment * 8) + min(requests, 100) * 0.4 + min(revenue / 1000, 100) * 0.2
    score = score / effort
    return {
        "rank": 0,
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "target_quarter": _string(metadata, "target_quarter", "unknown"),
        "impact_score": round(impact, 2),
        "effort_score": round(effort, 2),
        "confidence_score": round(confidence, 2),
        "strategic_alignment": round(alignment, 2),
        "customer_requests": int(max(requests, 0)),
        "revenue_potential": round(max(revenue, 0.0), 2),
        "priority_score": round(score, 1),
        "priority_band": _band(score),
    }


def _quarter_rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["target_quarter"]].append(row)
    return [{
        "target_quarter": quarter,
        "item_count": len(items),
        "average_priority_score": round(sum(item["priority_score"] for item in items) / len(items), 1),
        "revenue_potential": round(sum(item["revenue_potential"] for item in items), 2),
        "customer_requests": sum(item["customer_requests"] for item in items),
    } for quarter, items in sorted(groups.items())]


def _band(score: float) -> str:
    if score >= 30:
        return "high"
    if score >= 15:
        return "medium"
    return "low"


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _number(metadata: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(metadata.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _string(metadata: dict[str, Any], key: str, default: str) -> str:
    value = metadata.get(key, default)
    return str(value).strip() if value not in (None, "") else default
