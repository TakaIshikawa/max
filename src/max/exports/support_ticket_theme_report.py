"""Support ticket theme report export for product feedback planning."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.support_ticket_theme_report.v1"
KIND = "max.support_ticket_theme_report"

_FIELDS = ["idea_id", "title", "support_theme", "ticket_count", "severity", "customer_segment", "product_area", "sentiment", "first_seen_at"]


def build_support_ticket_theme_report(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (row["support_theme"], _severity_rank(row["severity"]), row["first_seen_at"] or "9999-99-99", row["title"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "support_ticket_theme_report", "domain_filter": domain},
        "summary": {"idea_count": len(rows), "ticket_count": sum(row["ticket_count"] for row in rows), "theme_count": len({row["support_theme"] for row in rows})},
        "theme_rollups": _rollups(rows, "support_theme"),
        "severity_rollups": _rollups(rows, "severity", severity_order=True),
        "product_area_rollups": _rollups(rows, "product_area"),
        "rows": rows,
    }


def render_support_ticket_theme_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Support Ticket Theme Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Linked ideas: {summary.get('idea_count', 0)}",
        f"- Tickets: {summary.get('ticket_count', 0)}",
        f"- Themes: {summary.get('theme_count', 0)}",
        "",
        "## Theme Rollup",
        "",
        "| Theme | Ideas | Tickets |",
        "|-------|-------|---------|",
    ]
    for row in report.get("theme_rollups", []):
        lines.append(f"| {row['support_theme']} | {row['idea_count']} | {row['ticket_count']} |")
    lines.extend(["", "## Severity Distribution", "", "| Severity | Ideas | Tickets |", "|----------|-------|---------|"])
    for row in report.get("severity_rollups", []):
        lines.append(f"| {row['severity']} | {row['idea_count']} | {row['ticket_count']} |")
    lines.extend(["", "## Detailed Rows", "", "| Idea | Theme | Severity | Segment | Area | Tickets | Sentiment | First Seen |", "|------|-------|----------|---------|------|---------|-----------|------------|"])
    for row in report.get("rows", []):
        lines.append(f"| {row['title']} | {row['support_theme']} | {row['severity']} | {row['customer_segment']} | {row['product_area']} | {row['ticket_count']} | {row['sentiment']} | {row['first_seen_at'] or 'unknown'} |")
    return "\n".join(lines).rstrip() + "\n"


def render_support_ticket_theme_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_support_ticket_theme_report_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_FIELDS)
    writer.writeheader()
    for row in report.get("rows", []):
        writer.writerow({field: row.get(field) for field in _FIELDS})
    return output.getvalue()


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "support_theme": _string(metadata, "support_theme", "unknown").lower(),
        "ticket_count": int(max(_number(metadata, "ticket_count", 0.0), 0.0)),
        "severity": _string(metadata, "severity", "unknown").lower(),
        "customer_segment": _string(metadata, "customer_segment", "unknown").lower(),
        "product_area": _string(metadata, "product_area", "unknown").lower(),
        "sentiment": _string(metadata, "sentiment", "unknown").lower(),
        "first_seen_at": _string(metadata, "first_seen_at", "") or None,
    }


def _rollups(rows: list[dict[str, Any]], key: str, *, severity_order: bool = False) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    sort_key = (lambda item: _severity_rank(item[0])) if severity_order else (lambda item: item[0])
    return [{key: name, "idea_count": len(items), "ticket_count": sum(item["ticket_count"] for item in items)} for name, items in sorted(groups.items(), key=sort_key)]


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


def _severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}.get(severity, 5)
