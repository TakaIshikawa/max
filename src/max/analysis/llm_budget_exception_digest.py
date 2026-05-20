"""Digest LLM budget exceptions and near-limit events across pipeline runs."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import StringIO
from typing import Any


SCHEMA_VERSION = "max.llm_budget_exception_digest.v1"
KIND = "max.llm_budget_exception_digest"
CSV_COLUMNS = (
    "profile",
    "stage",
    "model",
    "exception_type",
    "severity",
    "event_count",
    "total_estimated_cost",
    "max_utilization_percent",
    "latest_event_timestamp",
    "priority_band",
)
_PRIORITY_ORDER = {"critical": 0, "high": 1, "watch": 2}
_SEVERITY_ORDER = {"hard_failure": 0, "near_limit": 1}


@dataclass(frozen=True)
class LLMBudgetEvent:
    profile: str
    stage: str
    model: str
    exception_type: str
    severity: str
    estimated_cost: float = 0.0
    utilization_percent: float = 0.0
    timestamp: datetime | str | date | None = None


@dataclass(frozen=True)
class LLMBudgetDigestRow:
    profile: str
    stage: str
    model: str
    exception_type: str
    severity: str
    event_count: int
    total_estimated_cost: float
    max_utilization_percent: float
    latest_event_timestamp: str
    priority_band: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "stage": self.stage,
            "model": self.model,
            "exception_type": self.exception_type,
            "severity": self.severity,
            "event_count": self.event_count,
            "total_estimated_cost": self.total_estimated_cost,
            "max_utilization_percent": self.max_utilization_percent,
            "latest_event_timestamp": self.latest_event_timestamp,
            "priority_band": self.priority_band,
        }


def build_llm_budget_exception_digest(
    events: Iterable[LLMBudgetEvent | Mapping[str, Any]],
    *,
    high_event_count: int = 3,
    critical_utilization_percent: float = 100.0,
) -> dict[str, Any]:
    """Group LLM budget near-limit warnings and hard failures into deterministic rows."""
    if high_event_count < 1:
        raise ValueError("high_event_count must be at least 1")
    if critical_utilization_percent < 0:
        raise ValueError("critical_utilization_percent must be non-negative")

    grouped: dict[tuple[str, str, str, str, str], list[LLMBudgetEvent]] = defaultdict(list)
    for event in (_normalize_event(item) for item in events):
        grouped[(event.profile, event.stage, event.model, event.exception_type, event.severity)].append(event)

    rows = [_row_for_group(key, values, high_event_count, critical_utilization_percent) for key, values in grouped.items()]
    rows.sort(key=_row_sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "high_event_count": high_event_count,
            "critical_utilization_percent": critical_utilization_percent,
        },
        "summary": {
            "group_count": len(rows),
            "event_count": sum(row.event_count for row in rows),
            "hard_failure_event_count": sum(row.event_count for row in rows if row.severity == "hard_failure"),
            "near_limit_event_count": sum(row.event_count for row in rows if row.severity == "near_limit"),
            "critical_group_count": sum(1 for row in rows if row.priority_band == "critical"),
            "high_group_count": sum(1 for row in rows if row.priority_band == "high"),
            "watch_group_count": sum(1 for row in rows if row.priority_band == "watch"),
        },
        "rows": [row.as_dict() for row in rows],
    }


def render_llm_budget_exception_digest(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render LLM budget exception digest as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported LLM budget exception digest format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# LLM Budget Exception Digest",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Events: {summary.get('event_count', 0)}",
        f"Hard failures: {summary.get('hard_failure_event_count', 0)}",
        f"Near-limit warnings: {summary.get('near_limit_event_count', 0)}",
        "",
        "## Groups",
        "",
        "| Profile | Stage | Model | Type | Severity | Events | Cost | Max Utilization | Latest | Priority |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    rows = _sorted_row_maps(report.get("rows"))
    if rows:
        for row in rows:
            lines.append(
                "| `{}` | `{}` | `{}` | `{}` | {} | {} | {:.4f} | {:.1f} | `{}` | {} |".format(
                    row.get("profile") or "",
                    row.get("stage") or "",
                    row.get("model") or "",
                    row.get("exception_type") or "",
                    row.get("severity") or "",
                    row.get("event_count", 0),
                    float(row.get("total_estimated_cost") or 0.0),
                    float(row.get("max_utilization_percent") or 0.0),
                    row.get("latest_event_timestamp") or "",
                    row.get("priority_band") or "",
                )
            )
    else:
        lines.append("| none | none | none | none | near_limit | 0 | 0.0000 | 0.0 | `` | watch |")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _sorted_row_maps(report.get("rows")):
        writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
    return output.getvalue()


def _row_for_group(
    key: tuple[str, str, str, str, str],
    events: list[LLMBudgetEvent],
    high_event_count: int,
    critical_utilization_percent: float,
) -> LLMBudgetDigestRow:
    profile, stage, model, exception_type, severity = key
    event_count = len(events)
    total_cost = round(sum(event.estimated_cost for event in events), 6)
    max_utilization = round(max((event.utilization_percent for event in events), default=0.0), 2)
    latest = max((_coerce_datetime(event.timestamp) for event in events), default=datetime(1970, 1, 1, tzinfo=UTC))
    if severity == "hard_failure" or max_utilization >= critical_utilization_percent:
        priority = "critical"
    elif event_count >= high_event_count or max_utilization >= 90:
        priority = "high"
    else:
        priority = "watch"
    return LLMBudgetDigestRow(
        profile=profile,
        stage=stage,
        model=model,
        exception_type=exception_type,
        severity=severity,
        event_count=event_count,
        total_estimated_cost=total_cost,
        max_utilization_percent=max_utilization,
        latest_event_timestamp=_format_timestamp(latest),
        priority_band=priority,
    )


def _normalize_event(item: LLMBudgetEvent | Mapping[str, Any]) -> LLMBudgetEvent:
    if isinstance(item, LLMBudgetEvent):
        event = item
    else:
        raw_type = str(item.get("exception_type") or item.get("type") or "near_limit")
        raw_severity = str(item.get("severity") or "")
        event = LLMBudgetEvent(
            profile=str(item.get("profile") or "unspecified"),
            stage=str(item.get("stage") or "unknown"),
            model=str(item.get("model") or "unknown"),
            exception_type=raw_type,
            severity=raw_severity or _severity_from_type(raw_type),
            estimated_cost=_nonnegative_float(item.get("estimated_cost", item.get("cost", 0.0))),
            utilization_percent=_nonnegative_float(item.get("utilization_percent", item.get("budget_utilization_percent", 0.0))),
            timestamp=item.get("timestamp") or item.get("created_at") or item.get("event_timestamp"),
        )
    severity = event.severity if event.severity in _SEVERITY_ORDER else _severity_from_type(event.exception_type)
    return LLMBudgetEvent(
        profile=event.profile or "unspecified",
        stage=event.stage or "unknown",
        model=event.model or "unknown",
        exception_type=event.exception_type or "near_limit",
        severity=severity,
        estimated_cost=_nonnegative_float(event.estimated_cost),
        utilization_percent=_nonnegative_float(event.utilization_percent),
        timestamp=event.timestamp,
    )


def _severity_from_type(value: str) -> str:
    lowered = value.lower()
    return "hard_failure" if "fail" in lowered or "exceed" in lowered or "hard" in lowered else "near_limit"


def _row_sort_key(row: LLMBudgetDigestRow) -> tuple[int, int, int, str, str, str, str]:
    return (
        _PRIORITY_ORDER[row.priority_band],
        _SEVERITY_ORDER[row.severity],
        -row.event_count,
        row.profile,
        row.stage,
        row.model,
        row.exception_type,
    )


def _sorted_row_maps(value: Any) -> list[Mapping[str, Any]]:
    rows = _list_of_maps(value)
    return sorted(
        rows,
        key=lambda row: (
            _PRIORITY_ORDER.get(str(row.get("priority_band")), len(_PRIORITY_ORDER)),
            _SEVERITY_ORDER.get(str(row.get("severity")), len(_SEVERITY_ORDER)),
            -_int(row.get("event_count")),
            str(row.get("profile") or ""),
            str(row.get("stage") or ""),
            str(row.get("model") or ""),
            str(row.get("exception_type") or ""),
        ),
    )


def _coerce_datetime(value: datetime | str | date | None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime(1970, 1, 1, tzinfo=UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _nonnegative_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
