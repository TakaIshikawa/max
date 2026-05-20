"""Pipeline stage latency report with bottleneck severity bands."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import StringIO
from typing import Any


SCHEMA_VERSION = "max.pipeline_stage_latency_report.v1"
KIND = "max.pipeline_stage_latency_report"
CSV_COLUMNS = (
    "profile",
    "run_group",
    "stage",
    "count",
    "average_duration_seconds",
    "p95_duration_seconds",
    "max_duration_seconds",
    "timeout_count",
    "bottleneck_severity",
)
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "healthy": 2}


@dataclass(frozen=True)
class PipelineStageLatencyRecord:
    stage: str
    duration_seconds: float
    profile: str = ""
    run_group: str = ""
    timed_out: bool = False


@dataclass(frozen=True)
class PipelineStageLatencyRow:
    profile: str
    run_group: str
    stage: str
    count: int
    average_duration_seconds: float
    p95_duration_seconds: float
    max_duration_seconds: float
    timeout_count: int
    bottleneck_severity: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "run_group": self.run_group,
            "stage": self.stage,
            "count": self.count,
            "average_duration_seconds": self.average_duration_seconds,
            "p95_duration_seconds": self.p95_duration_seconds,
            "max_duration_seconds": self.max_duration_seconds,
            "timeout_count": self.timeout_count,
            "bottleneck_severity": self.bottleneck_severity,
        }


def build_pipeline_stage_latency_report(
    records: Iterable[PipelineStageLatencyRecord | Mapping[str, Any]],
    *,
    warning_p95_seconds: float = 60.0,
    critical_p95_seconds: float = 180.0,
    group_by_profile: bool = True,
    group_by_run: bool = True,
) -> dict[str, Any]:
    """Aggregate stage latency metrics and flag bottlenecks."""
    if warning_p95_seconds < 0:
        raise ValueError("warning_p95_seconds must be non-negative")
    if critical_p95_seconds < warning_p95_seconds:
        raise ValueError("critical_p95_seconds must be greater than or equal to warning_p95_seconds")

    grouped: dict[tuple[str, str, str], list[PipelineStageLatencyRecord]] = defaultdict(list)
    for record in (_normalize_record(item) for item in records):
        key = (record.profile if group_by_profile else "", record.run_group if group_by_run else "", record.stage)
        grouped[key].append(record)

    rows = [_row_for_group(key, values, warning_p95_seconds, critical_p95_seconds) for key, values in grouped.items()]
    rows.sort(key=_row_sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "warning_p95_seconds": warning_p95_seconds,
            "critical_p95_seconds": critical_p95_seconds,
            "group_by_profile": group_by_profile,
            "group_by_run": group_by_run,
        },
        "summary": {
            "group_count": len(rows),
            "stage_event_count": sum(row.count for row in rows),
            "timeout_count": sum(row.timeout_count for row in rows),
            "critical_count": sum(1 for row in rows if row.bottleneck_severity == "critical"),
            "warning_count": sum(1 for row in rows if row.bottleneck_severity == "warning"),
            "healthy_count": sum(1 for row in rows if row.bottleneck_severity == "healthy"),
        },
        "rows": [row.as_dict() for row in rows],
    }


def render_pipeline_stage_latency_report(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render pipeline stage latency report as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported pipeline stage latency report format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Pipeline Stage Latency Report",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Stage groups: {summary.get('group_count', 0)}",
        f"Timeouts: {summary.get('timeout_count', 0)}",
        "",
        "## Stage Latency",
        "",
        "| Profile | Run | Stage | Count | Avg Seconds | P95 Seconds | Max Seconds | Timeouts | Severity |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    rows = _sorted_row_maps(report.get("rows"))
    if rows:
        for row in rows:
            lines.append(
                "| `{}` | `{}` | `{}` | {} | {:.2f} | {:.2f} | {:.2f} | {} | {} |".format(
                    row.get("profile") or "",
                    row.get("run_group") or "",
                    row.get("stage") or "",
                    row.get("count", 0),
                    float(row.get("average_duration_seconds") or 0.0),
                    float(row.get("p95_duration_seconds") or 0.0),
                    float(row.get("max_duration_seconds") or 0.0),
                    row.get("timeout_count", 0),
                    row.get("bottleneck_severity") or "",
                )
            )
    else:
        lines.append("| none | none | none | 0 | 0.00 | 0.00 | 0.00 | 0 | healthy |")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _sorted_row_maps(report.get("rows")):
        writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
    return output.getvalue()


def _row_for_group(
    key: tuple[str, str, str],
    records: list[PipelineStageLatencyRecord],
    warning_p95_seconds: float,
    critical_p95_seconds: float,
) -> PipelineStageLatencyRow:
    profile, run_group, stage = key
    durations = sorted(record.duration_seconds for record in records)
    count = len(durations)
    average = round(sum(durations) / count, 4) if count else 0.0
    p95 = round(_percentile(durations, 0.95), 4)
    maximum = round(max(durations), 4) if durations else 0.0
    timeout_count = sum(1 for record in records if record.timed_out)
    if timeout_count or p95 >= critical_p95_seconds:
        severity = "critical"
    elif p95 >= warning_p95_seconds:
        severity = "warning"
    else:
        severity = "healthy"
    return PipelineStageLatencyRow(
        profile=profile,
        run_group=run_group,
        stage=stage,
        count=count,
        average_duration_seconds=average,
        p95_duration_seconds=p95,
        max_duration_seconds=maximum,
        timeout_count=timeout_count,
        bottleneck_severity=severity,
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int((len(values) - 1) * percentile + 0.999999)))
    return values[index]


def _normalize_record(item: PipelineStageLatencyRecord | Mapping[str, Any]) -> PipelineStageLatencyRecord:
    if isinstance(item, PipelineStageLatencyRecord):
        record = item
    else:
        record = PipelineStageLatencyRecord(
            stage=str(item.get("stage") or "unknown"),
            duration_seconds=_nonnegative_float(item.get("duration_seconds", item.get("duration_ms", 0.0)) / 1000 if "duration_ms" in item else item.get("duration_seconds", 0.0)),
            profile=str(item.get("profile") or ""),
            run_group=str(item.get("run_group") or item.get("run_id") or ""),
            timed_out=bool(item.get("timed_out", item.get("timeout", False))),
        )
    return PipelineStageLatencyRecord(
        stage=record.stage or "unknown",
        duration_seconds=_nonnegative_float(record.duration_seconds),
        profile=record.profile or "",
        run_group=record.run_group or "",
        timed_out=bool(record.timed_out),
    )


def _row_sort_key(row: PipelineStageLatencyRow) -> tuple[int, int, float, str, str, str]:
    return (
        _SEVERITY_ORDER[row.bottleneck_severity],
        -row.timeout_count,
        -row.p95_duration_seconds,
        row.profile,
        row.run_group,
        row.stage,
    )


def _sorted_row_maps(value: Any) -> list[Mapping[str, Any]]:
    rows = _list_of_maps(value)
    return sorted(
        rows,
        key=lambda row: (
            _SEVERITY_ORDER.get(str(row.get("bottleneck_severity")), len(_SEVERITY_ORDER)),
            -_int(row.get("timeout_count")),
            -_float(row.get("p95_duration_seconds")),
            str(row.get("profile") or ""),
            str(row.get("run_group") or ""),
            str(row.get("stage") or ""),
        ),
    )


def _nonnegative_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _float(value: Any) -> float:
    try:
        return float(value)
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
