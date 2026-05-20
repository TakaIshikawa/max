"""Source freshness SLA digest for persisted signals."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.source_freshness_sla_digest.v1"
KIND = "max.source_freshness_sla_digest"
CSV_COLUMNS = (
    "adapter",
    "signal_count",
    "newest_signal_at",
    "newest_age_hours",
    "oldest_signal_at",
    "stale_count",
    "freshness_band",
    "recommended_follow_up",
)


def build_source_freshness_sla_digest(
    store: "Store",
    *,
    stale_after_hours: float = 168.0,
    limit: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic freshness SLA digest grouped by source adapter."""
    if stale_after_hours <= 0:
        raise ValueError("stale_after_hours must be greater than 0")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    current = _aware_utc(now or datetime.now(UTC))
    records = store.get_signal_freshness_records()
    adapters = _adapter_rows(records, current, stale_after_hours)
    adapters = sorted(
        adapters,
        key=lambda row: (
            0 if row["freshness_band"] in {"missing", "stale"} else 1,
            str(row.get("newest_signal_at") or ""),
            str(row["adapter"]),
        ),
    )[:limit]
    bands = {band: [row["adapter"] for row in adapters if row["freshness_band"] == band] for band in ("missing", "stale", "aging", "fresh")}
    summary = {
        "adapter_count": len(adapters),
        "signal_count": sum(row["signal_count"] for row in adapters),
        "stale_adapter_count": len(bands["stale"]),
        "missing_adapter_count": len(bands["missing"]),
        "stale_signal_count": sum(row["stale_count"] for row in adapters),
        "fresh_adapter_count": len(bands["fresh"]),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {"stale_after_hours": float(stale_after_hours), "limit": limit},
        "summary": summary,
        "adapters": adapters,
        "freshness_bands": bands,
        "next_actions": _next_actions(adapters),
    }


def render_source_freshness_sla_digest(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render a source freshness SLA digest as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported source freshness SLA digest format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Source Freshness SLA Digest",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Adapters: {summary.get('adapter_count', 0)}",
        f"Stale adapters: {summary.get('stale_adapter_count', 0)}",
        "",
        "## Adapters",
        "",
        "| Adapter | Signals | Newest Age Hours | Stale | Band | Follow-Up |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in _list_of_maps(report.get("adapters")):
        lines.append(
            "| `{}` | {} | {} | {} | {} | {} |".format(
                row.get("adapter") or "",
                row.get("signal_count", 0),
                row.get("newest_age_hours", ""),
                row.get("stale_count", 0),
                row.get("freshness_band") or "",
                row.get("recommended_follow_up") or "",
            )
        )
    if not report.get("adapters"):
        lines.append("| none | 0 |  | 0 | missing | Add source signals. |")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions")
    lines.extend(f"- {item}" for item in actions) if isinstance(actions, list) and actions else lines.append("- None")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _list_of_maps(report.get("adapters")):
        writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
    return output.getvalue()


def _adapter_rows(records: list[dict[str, Any]], now: datetime, stale_after_hours: float) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("source_adapter") or "unknown"), []).append(record)
    rows = []
    for adapter, items in grouped.items():
        timestamps = [_parse_timestamp(item.get("published_at") or item.get("fetched_at")) for item in items]
        valid = [item for item in timestamps if item is not None]
        newest = max(valid) if valid else None
        oldest = min(valid) if valid else None
        ages = [max((now - item).total_seconds() / 3600, 0.0) for item in valid]
        newest_age = min(ages) if ages else None
        stale_count = sum(1 for age in ages if age > stale_after_hours) + (len(items) - len(valid))
        band = _band(len(items), newest_age, stale_count, stale_after_hours)
        rows.append(
            {
                "adapter": adapter,
                "signal_count": len(items),
                "newest_signal_at": newest.isoformat() if newest else None,
                "newest_age_hours": round(newest_age, 2) if newest_age is not None else None,
                "oldest_signal_at": oldest.isoformat() if oldest else None,
                "stale_count": stale_count,
                "freshness_band": band,
                "recommended_follow_up": _follow_up(adapter, band),
            }
        )
    return rows


def _band(signal_count: int, newest_age: float | None, stale_count: int, stale_after_hours: float) -> str:
    if signal_count == 0 or newest_age is None:
        return "missing"
    if newest_age > stale_after_hours:
        return "stale"
    if stale_count:
        return "aging"
    return "fresh"


def _follow_up(adapter: str, band: str) -> str:
    if band == "missing":
        return f"Verify `{adapter}` ingestion is configured and producing signals."
    if band == "stale":
        return f"Refresh `{adapter}` before using dependent insights."
    if band == "aging":
        return f"Schedule a normal refresh for `{adapter}`."
    return f"Keep `{adapter}` on the current refresh cadence."


def _next_actions(adapters: list[dict[str, Any]]) -> list[str]:
    stale = [row for row in adapters if row["freshness_band"] in {"missing", "stale"}]
    if not adapters:
        return ["Ingest signals before evaluating source freshness SLAs."]
    if not stale:
        return ["All analyzed source adapters are within freshness SLA."]
    return [row["recommended_follow_up"] for row in stale[:5]]


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
