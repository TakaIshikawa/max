from __future__ import annotations

import json

from max.api import circuit_breaker_churn_status_to_json


def test_circuit_breaker_churn_status_reports_critical_rollup() -> None:
    data = json.loads(circuit_breaker_churn_status_to_json({"warning_churn_threshold": 4, "critical_churn_threshold": 8, "adapters": [{"adapter": "github", "opened_count": 2, "reopen_count": 1}, {"adapter": "reddit", "opened_count": 1, "reopen_count": 3}]}))

    assert data["status"] == "critical"
    assert data["adapter_count"] == 2
    assert data["worst_adapter"] == "reddit"
    assert data["opened_count"] == 3
    assert data["reopen_count"] == 4
    assert data["churn_score"] == 11


def test_circuit_breaker_churn_status_supports_warning_and_empty_inputs() -> None:
    warning = json.loads(circuit_breaker_churn_status_to_json({"warning_churn_threshold": 2, "critical_churn_threshold": 10, "items": [{"source": "hn", "open_count": 2}]}))
    empty = json.loads(circuit_breaker_churn_status_to_json({}))

    assert warning["status"] == "warning"
    assert warning["worst_adapter"] == "hn"
    assert empty["status"] == "ok"
    assert empty["adapter_count"] == 0
    assert empty["worst_adapter"] is None
