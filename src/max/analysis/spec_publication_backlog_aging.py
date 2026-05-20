"""Spec publication backlog aging report for approved unpublished ideas."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store
    from max.types.buildable_unit import BuildableUnit


SCHEMA_VERSION = "max.spec_publication_backlog_aging.v1"
KIND = "max.spec_publication_backlog_aging"

SUCCESS_STATUSES = {"published", "success", "succeeded", "completed"}
BACKLOG_STATUSES = {"approved"}
AGE_BANDS = ("overdue", "stale", "fresh")
CSV_COLUMNS = (
    "idea_id",
    "title",
    "status",
    "profile",
    "domain",
    "age_hours",
    "stale_band",
    "priority",
    "created_at",
    "latest_publication_status",
    "latest_publication_at",
    "recommendation",
)


def build_spec_publication_backlog_aging(
    store: "Store",
    *,
    stale_after_hours: int = 72,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic aging report for approved ideas awaiting publication."""
    if stale_after_hours < 1:
        raise ValueError("stale_after_hours must be at least 1")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    current_time = now or datetime.now(timezone.utc)
    units = store.get_buildable_units(limit=limit)
    items = [
        _backlog_item(store, unit, stale_after_hours=stale_after_hours, now=current_time)
        for unit in units
        if _is_backlog_candidate(store, unit)
    ]
    items = [item for item in items if item is not None]
    items.sort(key=_item_sort_key)
    age_bands = {band: [item["idea_id"] for item in items if item["stale_band"] == band] for band in AGE_BANDS}
    summary = _summary(items)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "stale_after_hours": stale_after_hours,
            "limit": limit,
            "now": _iso(current_time),
        },
        "summary": summary,
        "backlog_items": items,
        "age_bands": age_bands,
        "next_actions": _next_actions(items),
    }


def render_spec_publication_backlog_aging(
    report: Mapping[str, Any],
    *,
    fmt: str = "json",
) -> str:
    """Render spec publication backlog aging as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported spec publication backlog aging format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Spec Publication Backlog Aging",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Backlog items: {summary.get('backlog_count', 0)}",
        f"Oldest age hours: {summary.get('oldest_age_hours', 0)}",
        "",
        "## Backlog",
        "",
    ]
    items = _list_of_maps(report.get("backlog_items"))
    if items:
        lines.append("| Idea | Priority | Band | Age Hours | Profile | Domain | Latest Publication |")
        lines.append("| --- | --- | --- | ---: | --- | --- | --- |")
        for item in items:
            lines.append(
                "| `{}` | {} | {} | {} | `{}` | `{}` | `{}` |".format(
                    item.get("idea_id") or "",
                    item.get("priority") or "",
                    item.get("stale_band") or "",
                    item.get("age_hours", 0),
                    item.get("profile") or "",
                    item.get("domain") or "",
                    item.get("latest_publication_status") or "none",
                )
            )
    else:
        lines.append("No approved unpublished ideas are waiting for publication.")

    lines.extend(["", "## Profile Rollup", ""])
    _append_rollup(lines, summary.get("profiles"), "profile")
    lines.extend(["", "## Domain Rollup", ""])
    _append_rollup(lines, summary.get("domains"), "domain")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for item in sorted(_list_of_maps(report.get("backlog_items")), key=_item_sort_key):
        writer.writerow({column: item.get(column, "") for column in CSV_COLUMNS})
    return output.getvalue()


def _is_backlog_candidate(store: "Store", unit: "BuildableUnit") -> bool:
    status = str(unit.status or "").lower()
    if status not in BACKLOG_STATUSES:
        return False
    attempts = store.list_publication_attempts(unit.id, limit=20)
    return not any(str(attempt.get("status") or "").lower() in SUCCESS_STATUSES for attempt in attempts)


def _backlog_item(
    store: "Store",
    unit: "BuildableUnit",
    *,
    stale_after_hours: int,
    now: datetime,
) -> dict[str, Any] | None:
    created_at = _to_datetime(unit.created_at)
    if created_at is None:
        return None
    attempts = store.list_publication_attempts(unit.id, limit=20)
    latest_attempt = attempts[0] if attempts else {}
    age_hours = max(0, int((now - created_at).total_seconds() // 3600))
    stale_band = _stale_band(age_hours, stale_after_hours)
    priority = _priority(stale_band, age_hours, stale_after_hours)
    profile = _text(getattr(unit, "domain", "")) or "unknown"
    domain = _text(getattr(unit, "domain", "")) or "unknown"
    return {
        "idea_id": unit.id,
        "title": unit.title,
        "status": unit.status,
        "profile": profile,
        "domain": domain,
        "category": str(unit.category),
        "age_hours": age_hours,
        "stale_after_hours": stale_after_hours,
        "stale_band": stale_band,
        "priority": priority,
        "created_at": _iso(created_at),
        "latest_publication_status": latest_attempt.get("status") if latest_attempt else None,
        "latest_publication_at": latest_attempt.get("created_at") if latest_attempt else None,
        "recommendation": _recommendation(unit, stale_band, priority),
    }


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "backlog_count": len(items),
        "overdue_count": sum(1 for item in items if item["stale_band"] == "overdue"),
        "stale_count": sum(1 for item in items if item["stale_band"] == "stale"),
        "fresh_count": sum(1 for item in items if item["stale_band"] == "fresh"),
        "oldest_age_hours": max((item["age_hours"] for item in items), default=0),
        "profiles": _rollups(items, "profile"),
        "domains": _rollups(items, "domain"),
    }


def _rollups(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get(key) or "unknown"), []).append(item)
    rows = []
    for name, group in grouped.items():
        rows.append(
            {
                key: name,
                "backlog_count": len(group),
                "overdue_count": sum(1 for item in group if item["stale_band"] == "overdue"),
                "oldest_age_hours": max(item["age_hours"] for item in group),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["overdue_count"]), -int(row["oldest_age_hours"]), str(row[key])))


def _next_actions(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["No approved unpublished ideas need publication follow-up."]
    overdue = [item for item in items if item["stale_band"] == "overdue"]
    stale = [item for item in items if item["stale_band"] == "stale"]
    actions: list[str] = []
    if overdue:
        ids = ", ".join(item["idea_id"] for item in overdue[:5])
        actions.append(f"Publish or explicitly defer overdue specs first: {ids}.")
    if stale:
        ids = ", ".join(item["idea_id"] for item in stale[:5])
        actions.append(f"Schedule publication owners for stale approved ideas: {ids}.")
    if not actions:
        actions.append("Keep recent approved ideas on the next publication batch.")
    return actions


def _stale_band(age_hours: int, stale_after_hours: int) -> str:
    if age_hours >= stale_after_hours * 2:
        return "overdue"
    if age_hours >= stale_after_hours:
        return "stale"
    return "fresh"


def _priority(stale_band: str, age_hours: int, stale_after_hours: int) -> str:
    if stale_band == "overdue":
        return "p0" if age_hours >= stale_after_hours * 3 else "p1"
    if stale_band == "stale":
        return "p2"
    return "p3"


def _recommendation(unit: "BuildableUnit", stale_band: str, priority: str) -> str:
    if stale_band == "overdue":
        return f"{priority}: publish `{unit.id}` or record a deferral reason before the next planning cycle."
    if stale_band == "stale":
        return f"{priority}: assign a publication owner for `{unit.id}`."
    return f"{priority}: keep `{unit.id}` queued for the next normal publication batch."


def _item_sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    priority_order = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
    band_order = {"overdue": 0, "stale": 1, "fresh": 2}
    return (
        priority_order.get(str(item.get("priority") or ""), 9),
        band_order.get(str(item.get("stale_band") or ""), 9),
        -int(item.get("age_hours") or 0),
        str(item.get("idea_id") or ""),
    )


def _append_rollup(lines: list[str], value: Any, label: str) -> None:
    rows = _list_of_maps(value)
    lines.append(f"| {label.title()} | Backlog | Overdue | Oldest Age Hours |")
    lines.append("| --- | ---: | ---: | ---: |")
    if rows:
        for row in rows:
            lines.append(
                "| `{}` | {} | {} | {} |".format(
                    row.get(label) or "",
                    row.get("backlog_count", 0),
                    row.get("overdue_count", 0),
                    row.get("oldest_age_hours", 0),
                )
            )
    else:
        lines.append("| `none` | 0 | 0 | 0 |")


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _iso(value: datetime) -> str:
    return value.isoformat()


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
