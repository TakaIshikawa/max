from __future__ import annotations

import json

from max.api.insight_synthesis_failure_rate_status import insight_synthesis_failure_rate_status_to_json


def test_insight_synthesis_failure_rate_status_healthy() -> None:
    parsed = json.loads(insight_synthesis_failure_rate_status_to_json({"attempt_count": 100, "failures": [{"reason": "timeout", "count": 2, "retryable": True}]}))

    assert parsed["summary"]["status"] == "healthy"


def test_insight_synthesis_failure_rate_status_warning_and_critical() -> None:
    warning = json.loads(insight_synthesis_failure_rate_status_to_json({"attempt_count": 100, "failures": [{"reason": "timeout", "count": 8}]}))
    critical = json.loads(insight_synthesis_failure_rate_status_to_json({"attempt_count": 100, "failures": [{"reason": "timeout", "count": 20}]}))

    assert warning["summary"]["status"] == "warning"
    assert critical["summary"]["status"] == "critical"


def test_insight_synthesis_failure_rate_status_zero_attempt_is_safe() -> None:
    parsed = json.loads(insight_synthesis_failure_rate_status_to_json({"attempt_count": 0, "failures": [{"reason": "x", "count": 2}]}))

    assert parsed["summary"]["failure_rate"] == 0.0
    assert parsed["summary"]["status"] == "healthy"


def test_insight_synthesis_failure_rate_status_aggregates_reasons() -> None:
    parsed = json.loads(insight_synthesis_failure_rate_status_to_json({"attempt_count": 10, "failures": [{"reason": "Timeout", "count": 1, "retryable": True}, {"reason": "timeout", "count": 2, "retryable": True}, {"reason": "schema", "count": 1, "retryable": False}]}))

    assert parsed["failure_reasons"][0] == {"reason": "timeout", "retryable": True, "count": 3}
    assert parsed["summary"]["retryable_failure_count"] == 3
    assert parsed["summary"]["terminal_failure_count"] == 1
