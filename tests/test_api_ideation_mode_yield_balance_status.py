from __future__ import annotations

import json

from max.api import ideation_mode_yield_balance_status_to_json


def test_balanced_yield_is_ok() -> None:
    report = json.loads(ideation_mode_yield_balance_status_to_json({"modes": [{"mode": "direct", "generated": 10, "approved": 5}, {"mode": "refinement", "generated": 10, "approved": 4}]}))
    assert report["summary"]["status"] == "ok"


def test_low_yield_skew_is_critical() -> None:
    report = json.loads(ideation_mode_yield_balance_status_to_json({"rows": [{"mode": "direct", "generated_count": 80, "approved_count": 4}, {"mode": "cross_domain", "generated_count": 20, "approved_count": 10}]}))
    assert report["mode_rows"][0]["mode"] == "direct"
    assert report["mode_rows"][0]["status"] == "critical"


def test_missing_mode_name_gets_deterministic_id() -> None:
    report = json.loads(ideation_mode_yield_balance_status_to_json({"items": [{"generated": 1, "approved": 1}]}))
    assert report["mode_rows"][0]["mode"] == "mode-1"


def test_zero_generated_is_insufficient_data() -> None:
    report = json.loads(ideation_mode_yield_balance_status_to_json({"modes": [{"mode": "direct", "generated": 0, "approved": 2}]}))
    assert report["mode_rows"][0]["approval_rate"] == 0.0
    assert report["mode_rows"][0]["status"] == "insufficient_data"
