"""Source adapter pagination anomaly export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_pagination_anomaly_report.v1"
KIND = "max.source_adapter_pagination_anomaly_report"
_STATUS_RANK = {"anomalous": 0, "watch": 1, "ok": 2}


def generate_source_adapter_pagination_anomaly_report(
    fetch_runs: Iterable[dict[str, Any]],
    *,
    repeated_cursor_threshold: int = 2,
    empty_streak_threshold: int = 3,
    skipped_range_threshold: int = 1,
) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for index, raw in enumerate(fetch_runs, start=1):
        if not isinstance(raw, dict):
            continue
        row = _row(raw, index)
        groups[(row["adapter"], row["profile"])].append(row)

    rows = []
    for (adapter, profile), events in groups.items():
        events.sort(key=lambda row: (row["run_at"], row["page_number"], row["sequence"]))
        cursor_counts: dict[str, int] = defaultdict(int)
        empty_streak = max_empty_streak = 0
        skipped_ranges = []
        previous_page: int | None = None
        for event in events:
            if event["cursor"]:
                cursor_counts[event["cursor"]] += 1
            if event["fetched_count"] == 0:
                empty_streak += 1
                max_empty_streak = max(max_empty_streak, empty_streak)
            else:
                empty_streak = 0
            page = event["page_number"]
            if previous_page is not None and page is not None and page > previous_page + 1:
                skipped_ranges.append({"from_page": previous_page + 1, "to_page": page - 1, "missing_count": page - previous_page - 1})
            if page is not None:
                previous_page = page

        repeated_cursors = sorted(
            ({"cursor": cursor, "count": count} for cursor, count in cursor_counts.items() if count > 1),
            key=lambda item: (-item["count"], item["cursor"]),
        )
        repeated_cursor_count = sum(item["count"] - 1 for item in repeated_cursors)
        skipped_page_count = sum(item["missing_count"] for item in skipped_ranges)
        status = _status(
            repeated_cursor_count,
            max_empty_streak,
            skipped_page_count,
            repeated_cursor_threshold,
            empty_streak_threshold,
            skipped_range_threshold,
        )
        rows.append(
            {
                "adapter": adapter,
                "profile": profile,
                "page_count": len(events),
                "repeated_cursor_count": repeated_cursor_count,
                "repeated_cursors": repeated_cursors,
                "max_empty_page_streak": max_empty_streak,
                "skipped_page_count": skipped_page_count,
                "skipped_ranges": skipped_ranges,
                "status": status,
            }
        )

    rows.sort(key=lambda row: (_STATUS_RANK[row["status"]], row["adapter"].casefold(), row["profile"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "pair_count": len(rows),
            "anomalous_count": sum(1 for row in rows if row["status"] == "anomalous"),
            "watch_count": sum(1 for row in rows if row["status"] == "watch"),
            "repeated_cursor_count": sum(row["repeated_cursor_count"] for row in rows),
            "skipped_page_count": sum(row["skipped_page_count"] for row in rows),
            "repeated_cursor_threshold": max(1, repeated_cursor_threshold),
            "empty_streak_threshold": max(1, empty_streak_threshold),
            "skipped_range_threshold": max(1, skipped_range_threshold),
        },
        "rows": rows,
    }


def _status(
    repeated_cursor_count: int,
    max_empty_streak: int,
    skipped_page_count: int,
    repeated_cursor_threshold: int,
    empty_streak_threshold: int,
    skipped_range_threshold: int,
) -> str:
    if (
        repeated_cursor_count >= max(1, repeated_cursor_threshold)
        or max_empty_streak >= max(1, empty_streak_threshold)
        or skipped_page_count >= max(1, skipped_range_threshold)
    ):
        return "anomalous"
    if repeated_cursor_count or max_empty_streak > 1 or skipped_page_count:
        return "watch"
    return "ok"


def _row(raw: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "adapter": _text(raw.get("adapter") or raw.get("source_adapter") or raw.get("source")) or "unknown-adapter",
        "profile": _text(raw.get("profile") or raw.get("profile_id") or raw.get("profile_name")) or "default",
        "cursor": _text(raw.get("cursor") or raw.get("page_cursor") or raw.get("next_cursor")),
        "page_number": _int_or_none(raw.get("page_number") or raw.get("page") or raw.get("page_index")),
        "fetched_count": _int(raw.get("fetched_count") or raw.get("item_count") or raw.get("signal_count") or raw.get("count")),
        "run_at": _text(raw.get("run_at") or raw.get("fetched_at") or raw.get("created_at") or raw.get("timestamp")),
        "sequence": index,
    }


def _int_or_none(value: Any) -> int | None:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
