"""Product usage segmentation export for account and intensity analysis."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.product_usage_segmentation.v1"
KIND = "max.product_usage_segmentation"

_ROW_FIELDS = [
    "idea_id",
    "title",
    "account_segment",
    "plan",
    "usage_intensity",
    "active_users",
    "active_accounts",
    "usage_events",
    "events_per_user",
    "events_per_account",
    "last_activity_at",
]


def build_product_usage_segmentation_export(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build account segment and usage intensity rollups for buildable units."""
    units = store.get_buildable_units(limit=1000, domain=domain)
    rows = [_usage_row(unit) for unit in units]
    rows.sort(key=lambda row: (row["account_segment"], _intensity_rank(row["usage_intensity"]), row["title"], row["idea_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "product_usage_segmentation",
            "domain_filter": domain,
            "defaults": {
                "account_segment": "unknown",
                "plan": "unknown",
                "active_users": 0,
                "active_accounts": 0,
                "usage_events": 0,
                "last_activity_at": None,
            },
        },
        "summary": _summary(rows),
        "segment_rollups": _segment_rollups(rows),
        "intensity_rollups": _intensity_rollups(rows),
        "ideas": rows,
    }


def render_product_usage_segmentation_markdown(report: dict[str, Any]) -> str:
    """Render product usage segmentation as Markdown."""
    summary = report.get("summary", {})
    lines = [
        "# Product Usage Segmentation",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Ideas analyzed: {summary.get('idea_count', 0)}",
        f"- Account segments: {summary.get('segment_count', 0)}",
        f"- Active users: {summary.get('active_users', 0):,}",
        f"- Active accounts: {summary.get('active_accounts', 0):,}",
        f"- Usage events: {summary.get('usage_events', 0):,}",
        f"- High-intensity ideas: {summary.get('high_intensity_count', 0)}",
        "",
        "## Segment Rollup",
        "",
        "| Segment | Ideas | Active Users | Active Accounts | Usage Events | Avg Events/User | High | Medium | Low | None |",
        "|---------|-------|--------------|-----------------|--------------|-----------------|------|--------|-----|------|",
    ]
    for row in report.get("segment_rollups", []):
        lines.append(
            f"| {row['account_segment']} | {row['idea_count']} | {row['active_users']:,} | "
            f"{row['active_accounts']:,} | {row['usage_events']:,} | {row['average_events_per_user']:.2f} | "
            f"{row['high_intensity_count']} | {row['medium_intensity_count']} | "
            f"{row['low_intensity_count']} | {row['no_usage_count']} |"
        )

    lines.extend(["", "## Idea Usage", ""])
    if report.get("ideas"):
        lines.extend([
            "| Idea | Segment | Plan | Intensity | Users | Accounts | Events | Events/User | Last Activity |",
            "|------|---------|------|-----------|-------|----------|--------|-------------|---------------|",
        ])
        for row in report["ideas"]:
            lines.append(
                f"| {row['title']} | {row['account_segment']} | {row['plan']} | "
                f"{row['usage_intensity']} | {row['active_users']:,} | {row['active_accounts']:,} | "
                f"{row['usage_events']:,} | {row['events_per_user']:.2f} | {row['last_activity_at'] or 'unknown'} |"
            )
    else:
        lines.append("- No buildable units available. Add usage metadata to segment product adoption.")

    return "\n".join(lines).rstrip() + "\n"


def render_product_usage_segmentation_json(report: dict[str, Any]) -> str:
    """Render product usage segmentation as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_product_usage_segmentation_csv(report: dict[str, Any]) -> str:
    """Render product usage segmentation rows as CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_ROW_FIELDS)
    writer.writeheader()
    for row in report.get("ideas", []):
        writer.writerow({field: row.get(field) for field in _ROW_FIELDS})
    return output.getvalue()


def _usage_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    active_users = _non_negative_int(_number_from_metadata(metadata, ["active_users", "users"], 0))
    active_accounts = _non_negative_int(_number_from_metadata(metadata, ["active_accounts", "accounts"], 0))
    usage_events = _non_negative_int(_number_from_metadata(metadata, ["usage_events", "events"], 0))
    events_per_user = round(usage_events / active_users, 2) if active_users else 0.0
    events_per_account = round(usage_events / active_accounts, 2) if active_accounts else 0.0
    segment = _string_from_metadata(metadata, ["segment", "account_segment", "customer_segment"], "unknown").lower()
    plan = _string_from_metadata(metadata, ["plan", "pricing_plan"], "unknown").lower()

    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "account_segment": segment or "unknown",
        "plan": plan or "unknown",
        "usage_intensity": _usage_intensity(active_users, active_accounts, usage_events),
        "active_users": active_users,
        "active_accounts": active_accounts,
        "usage_events": usage_events,
        "events_per_user": events_per_user,
        "events_per_account": events_per_account,
        "last_activity_at": _string_from_metadata(metadata, ["last_activity_at", "last_seen_at"], "") or None,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "idea_count": len(rows),
        "segment_count": len({row["account_segment"] for row in rows}),
        "active_users": sum(row["active_users"] for row in rows),
        "active_accounts": sum(row["active_accounts"] for row in rows),
        "usage_events": sum(row["usage_events"] for row in rows),
        "high_intensity_count": sum(1 for row in rows if row["usage_intensity"] == "high"),
        "unclassified_count": sum(1 for row in rows if row["account_segment"] in {"unknown", "unclassified"}),
    }


def _segment_rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["account_segment"]].append(row)

    rollups: list[dict[str, Any]] = []
    for segment in sorted(groups):
        segment_rows = groups[segment]
        active_users = sum(row["active_users"] for row in segment_rows)
        usage_events = sum(row["usage_events"] for row in segment_rows)
        rollups.append({
            "account_segment": segment,
            "idea_count": len(segment_rows),
            "active_users": active_users,
            "active_accounts": sum(row["active_accounts"] for row in segment_rows),
            "usage_events": usage_events,
            "average_events_per_user": round(usage_events / active_users, 2) if active_users else 0.0,
            "high_intensity_count": sum(1 for row in segment_rows if row["usage_intensity"] == "high"),
            "medium_intensity_count": sum(1 for row in segment_rows if row["usage_intensity"] == "medium"),
            "low_intensity_count": sum(1 for row in segment_rows if row["usage_intensity"] == "low"),
            "no_usage_count": sum(1 for row in segment_rows if row["usage_intensity"] == "none"),
        })
    return rollups


def _intensity_rollups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rollups = []
    for intensity in ("high", "medium", "low", "none"):
        intensity_rows = [row for row in rows if row["usage_intensity"] == intensity]
        if intensity_rows:
            rollups.append({
                "usage_intensity": intensity,
                "idea_count": len(intensity_rows),
                "active_users": sum(row["active_users"] for row in intensity_rows),
                "active_accounts": sum(row["active_accounts"] for row in intensity_rows),
                "usage_events": sum(row["usage_events"] for row in intensity_rows),
            })
    return rollups


def _usage_intensity(active_users: int, active_accounts: int, usage_events: int) -> str:
    if usage_events <= 0 and active_users <= 0 and active_accounts <= 0:
        return "none"
    events_per_user = usage_events / active_users if active_users else 0.0
    if active_users >= 500 or active_accounts >= 100 or usage_events >= 50_000 or events_per_user >= 100:
        return "high"
    if active_users >= 100 or active_accounts >= 25 or usage_events >= 5_000 or events_per_user >= 25:
        return "medium"
    return "low"


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _number_from_metadata(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        if key in metadata:
            return _coerce_float(metadata[key], default)
    for nested_key in ("usage", "product_usage", "analytics"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                if key in nested:
                    return _coerce_float(nested[key], default)
    return default


def _string_from_metadata(metadata: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None and value != "":
            return str(value).strip()
    for nested_key in ("usage", "product_usage", "analytics"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if value is not None and value != "":
                    return str(value).strip()
    return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _non_negative_int(value: float) -> int:
    return max(int(value), 0)


def _intensity_rank(intensity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2, "none": 3}.get(intensity, 99)
