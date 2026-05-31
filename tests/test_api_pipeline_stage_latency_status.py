from __future__ import annotations

import json

from max.api.pipeline_stage_latency_status import pipeline_stage_latency_status_to_json


def test_pipeline_stage_latency_status_reports_healthy_stages() -> None:
    payload = {"stages": [{"stage": "draft", "p50_ms": 90, "p95_ms": 300, "p99_ms": 500, "sample_count": 12}]}

    parsed = json.loads(pipeline_stage_latency_status_to_json(payload))

    assert parsed["summary"]["status"] == "healthy"
    assert parsed["stages"][0]["sla_breached"] is False
    assert parsed["slowest_stage"]["stage"] == "draft"


def test_pipeline_stage_latency_status_escalates_warning_and_critical() -> None:
    parsed = json.loads(
        pipeline_stage_latency_status_to_json(
            {"warning_threshold_ms": 800, "critical_threshold_ms": 1200, "stages": [{"stage": "warn", "p95_ms": 900}, {"stage": "crit", "p95_ms": 1400}]}
        )
    )

    assert parsed["summary"]["status"] == "critical"
    assert [row["status"] for row in parsed["stages"]] == ["critical", "warning"]
    assert parsed["summary"]["sla_breach_count"] == 2


def test_pipeline_stage_latency_status_marks_missing_stage_data() -> None:
    parsed = json.loads(pipeline_stage_latency_status_to_json({"stages": [{"stage": "publish"}]}))

    assert parsed["summary"]["status"] == "warning"
    assert parsed["stages"][0]["status"] == "missing"


def test_pipeline_stage_latency_status_orders_by_severity_then_stage_name() -> None:
    parsed = json.loads(
        pipeline_stage_latency_status_to_json(
            {"stages": [{"stage": "zeta", "p95_ms": 100}, {"stage": "beta", "p95_ms": 1300}, {"stage": "alpha", "p95_ms": 900}, {"stage": "aardvark", "p95_ms": 1300}]}
        )
    )

    assert [row["stage"] for row in parsed["stages"]] == ["aardvark", "beta", "alpha", "zeta"]


def test_pipeline_stage_latency_status_empty_input_is_no_data() -> None:
    parsed = json.loads(pipeline_stage_latency_status_to_json({}))

    assert parsed["summary"]["status"] == "no_data"
    assert parsed["stages"] == []
