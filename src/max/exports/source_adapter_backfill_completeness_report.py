"""Source adapter backfill completeness export report."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_backfill_completeness_report.v1"
KIND = "max.source_adapter_backfill_completeness_report"
_STATUS_RANK = {"missing": 0, "partial": 1, "complete": 2}


def generate_source_adapter_backfill_completeness_report(
    requested_windows: Iterable[dict[str, Any]],
    completed_intervals: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    requests_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    completions_by_pair: dict[tuple[str, str], list[tuple[datetime, datetime]]] = defaultdict(list)

    for index, raw in enumerate(requested_windows, start=1):
        if not isinstance(raw, dict):
            continue
        window = _window(raw, index, "request")
        if window is None:
            continue
        requests_by_pair[(window["adapter"], window["profile"])].append(window)

    for index, raw in enumerate(completed_intervals, start=1):
        if not isinstance(raw, dict):
            continue
        interval = _window(raw, index, "completed")
        if interval is None:
            continue
        completions_by_pair[(interval["adapter"], interval["profile"])].append((interval["start"], interval["end"]))

    rows = []
    for pair in sorted(set(requests_by_pair) | set(completions_by_pair), key=lambda item: (item[0].casefold(), item[1].casefold())):
        adapter, profile = pair
        completed = _merge_intervals(completions_by_pair[pair])
        for request in sorted(requests_by_pair[pair], key=lambda item: (item["start"], item["end"], item["window_id"])):
            requested_minutes = _minutes(request["start"], request["end"])
            covered_segments = _covered_segments(request["start"], request["end"], completed)
            covered_minutes = sum(_minutes(start, end) for start, end in covered_segments)
            missing_segments = _missing_segments(request["start"], request["end"], covered_segments)
            missing_minutes = requested_minutes - covered_minutes
            completeness = round(covered_minutes / requested_minutes, 4) if requested_minutes else 0.0
            status = "complete" if completeness >= 1.0 else ("partial" if completeness > 0 else "missing")
            rows.append(
                {
                    "adapter": adapter,
                    "profile": profile,
                    "window_id": request["window_id"],
                    "requested_start_at": _iso(request["start"]),
                    "requested_end_at": _iso(request["end"]),
                    "requested_minutes": requested_minutes,
                    "covered_minutes": covered_minutes,
                    "missing_minutes": missing_minutes,
                    "completeness": completeness,
                    "status": status,
                    "covered_intervals": [_segment(start, end) for start, end in covered_segments],
                    "missing_intervals": [_segment(start, end) for start, end in missing_segments],
                }
            )

    rows.sort(key=lambda row: (_STATUS_RANK[row["status"]], row["adapter"].casefold(), row["profile"].casefold(), row["window_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "window_count": len(rows),
            "complete_count": sum(1 for row in rows if row["status"] == "complete"),
            "partial_count": sum(1 for row in rows if row["status"] == "partial"),
            "missing_count": sum(1 for row in rows if row["status"] == "missing"),
            "requested_minutes": sum(row["requested_minutes"] for row in rows),
            "covered_minutes": sum(row["covered_minutes"] for row in rows),
            "missing_minutes": sum(row["missing_minutes"] for row in rows),
            "completeness": _ratio(sum(row["covered_minutes"] for row in rows), sum(row["requested_minutes"] for row in rows)),
        },
        "rows": rows,
    }


def _window(raw: dict[str, Any], index: int, prefix: str) -> dict[str, Any] | None:
    start = _parse(raw.get("start_at") or raw.get("started_at") or raw.get("from") or raw.get("window_start") or raw.get("requested_start_at"))
    end = _parse(raw.get("end_at") or raw.get("completed_at") or raw.get("to") or raw.get("window_end") or raw.get("requested_end_at"))
    if start is None or end is None or end <= start:
        return None
    return {
        "window_id": _text(raw.get("window_id") or raw.get("backfill_id") or raw.get("id")) or f"{prefix}-{index}",
        "adapter": _text(raw.get("adapter") or raw.get("source_adapter") or raw.get("source")) or "unknown-adapter",
        "profile": _text(raw.get("profile") or raw.get("profile_id") or raw.get("profile_name")) or "default",
        "start": start,
        "end": end,
    }


def _covered_segments(start: datetime, end: datetime, intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    segments = []
    for interval_start, interval_end in intervals:
        covered_start = max(start, interval_start)
        covered_end = min(end, interval_end)
        if covered_end > covered_start:
            segments.append((covered_start, covered_end))
    return _merge_intervals(segments)


def _missing_segments(start: datetime, end: datetime, covered: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    missing = []
    cursor = start
    for covered_start, covered_end in covered:
        if covered_start > cursor:
            missing.append((cursor, covered_start))
        cursor = max(cursor, covered_end)
    if cursor < end:
        missing.append((cursor, end))
    return missing


def _merge_intervals(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
    return merged


def _segment(start: datetime, end: datetime) -> dict[str, Any]:
    return {"start_at": _iso(start), "end_at": _iso(end), "minutes": _minutes(start, end)}


def _minutes(start: datetime, end: datetime) -> int:
    return round((end - start).total_seconds() / 60)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _parse(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _text(value)
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
