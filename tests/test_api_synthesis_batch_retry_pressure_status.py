from __future__ import annotations

import json

from max.api import synthesis_batch_retry_pressure_status_to_json


def test_empty_input_returns_empty_batches() -> None:
    report = json.loads(synthesis_batch_retry_pressure_status_to_json({}))
    assert report["batch_rows"] == []


def test_healthy_batch_is_ok() -> None:
    report = json.loads(synthesis_batch_retry_pressure_status_to_json({"batches": [{"batch_id": "b1", "retry_count": 0}]}))
    assert report["batch_rows"][0]["status"] == "ok"


def test_retry_pressure_warns_and_sorts_first() -> None:
    report = json.loads(synthesis_batch_retry_pressure_status_to_json({"rows": [{"batch_id": "ok", "retry_count": 0}, {"batch_id": "warn", "retry_count": 2}]}))
    assert report["batch_rows"][0]["batch_id"] == "warn"
    assert report["batch_rows"][0]["status"] == "warning"


def test_critical_retry_pressure_uses_threshold() -> None:
    report = json.loads(synthesis_batch_retry_pressure_status_to_json({"items": [{"batch_id": "hot", "retries": 5}]}))
    assert report["batch_rows"][0]["status"] == "critical"
