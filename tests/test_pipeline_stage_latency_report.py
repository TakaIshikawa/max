from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.pipeline_stage_latency_report import (
    KIND,
    SCHEMA_VERSION,
    PipelineStageLatencyRecord,
    build_pipeline_stage_latency_report,
    render_pipeline_stage_latency_report,
)


def test_pipeline_stage_latency_report_aggregates_and_orders_bottlenecks() -> None:
    records = [
        PipelineStageLatencyRecord("synthesis", 10, "enterprise", "run-1"),
        PipelineStageLatencyRecord("synthesis", 80, "enterprise", "run-1"),
        PipelineStageLatencyRecord("synthesis", 240, "enterprise", "run-1"),
        PipelineStageLatencyRecord("evaluation", 40, "enterprise", "run-1"),
        PipelineStageLatencyRecord("evaluation", 70, "enterprise", "run-1"),
        PipelineStageLatencyRecord("publish", 5, "enterprise", "run-1", timed_out=True),
        PipelineStageLatencyRecord("publish", 6, "enterprise", "run-1"),
    ]

    report = build_pipeline_stage_latency_report(records, warning_p95_seconds=60, critical_p95_seconds=180)
    repeated = build_pipeline_stage_latency_report(records, warning_p95_seconds=60, critical_p95_seconds=180)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "group_count": 3,
        "stage_event_count": 7,
        "timeout_count": 1,
        "critical_count": 2,
        "warning_count": 1,
        "healthy_count": 0,
    }
    assert [row["stage"] for row in report["rows"]] == ["publish", "synthesis", "evaluation"]
    synthesis = report["rows"][1]
    assert synthesis["count"] == 3
    assert synthesis["average_duration_seconds"] == 110.0
    assert synthesis["p95_duration_seconds"] == 240
    assert synthesis["max_duration_seconds"] == 240
    assert synthesis["timeout_count"] == 0
    assert synthesis["bottleneck_severity"] == "critical"


def test_pipeline_stage_latency_report_can_collapse_groups_and_render() -> None:
    records = [
        {"stage": "ideation", "duration_ms": 1000, "profile": "a", "run_id": "1"},
        {"stage": "ideation", "duration_seconds": 2, "profile": "b", "run_id": "2"},
    ]
    report = build_pipeline_stage_latency_report(
        records,
        warning_p95_seconds=10,
        critical_p95_seconds=20,
        group_by_profile=False,
        group_by_run=False,
    )

    assert report["rows"] == [
        {
            "profile": "",
            "run_group": "",
            "stage": "ideation",
            "count": 2,
            "average_duration_seconds": 1.5,
            "p95_duration_seconds": 2.0,
            "max_duration_seconds": 2.0,
            "timeout_count": 0,
            "bottleneck_severity": "healthy",
        }
    ]
    assert json.loads(render_pipeline_stage_latency_report(report, fmt="json")) == report

    markdown = render_pipeline_stage_latency_report(report, fmt="markdown")
    assert markdown.startswith("# Pipeline Stage Latency Report")
    assert "| `` | `` | `ideation` | 2 | 1.50 | 2.00 | 2.00 | 0 | healthy |" in markdown

    rendered_csv = render_pipeline_stage_latency_report(report, fmt="csv")
    assert rendered_csv.splitlines()[0] == (
        "profile,run_group,stage,count,average_duration_seconds,p95_duration_seconds,"
        "max_duration_seconds,timeout_count,bottleneck_severity"
    )
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert rows[0]["stage"] == "ideation"

    with pytest.raises(ValueError, match="Unsupported pipeline stage latency report format: yaml"):
        render_pipeline_stage_latency_report(report, fmt="yaml")


def test_pipeline_stage_latency_report_validates_thresholds() -> None:
    with pytest.raises(ValueError, match="warning_p95_seconds must be non-negative"):
        build_pipeline_stage_latency_report([], warning_p95_seconds=-1)
    with pytest.raises(ValueError, match="critical_p95_seconds must be greater than or equal"):
        build_pipeline_stage_latency_report([], warning_p95_seconds=10, critical_p95_seconds=5)
