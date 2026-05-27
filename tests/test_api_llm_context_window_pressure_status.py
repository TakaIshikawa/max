from __future__ import annotations

import json

from max.api.llm_context_window_pressure_status import llm_context_window_pressure_status_to_json


def test_llm_context_window_pressure_status_computes_threshold_and_summary() -> None:
    report = json.loads(llm_context_window_pressure_status_to_json({"requests": [{"model": "m2", "prompt_tokens": 800, "completion_tokens": 100, "context_window_tokens": 1000}, {"model": "m1", "prompt_tokens": 10, "completion_tokens": 10, "context_window_tokens": 100}, {"model": "bad", "prompt_tokens": "x", "completion_tokens": -2, "context_window_tokens": 0}]}))

    assert report["rows"][0]["model"] == "m2"
    assert report["rows"][0]["pressure_ratio"] == 0.9
    assert report["rows"][0]["near_limit"] is True
    assert report["summary"]["request_count"] == 3
    assert report["summary"]["near_limit_count"] == 1
    assert report["summary"]["max_pressure_ratio"] == 0.9
    assert report["summary"]["truncation_risk_count"] == 1
