from __future__ import annotations

import json

from max.api import signal_freshness_regression_status_to_json


def test_signal_freshness_regression_status_reports_delta_and_missing_baseline() -> None:
    report = json.loads(signal_freshness_regression_status_to_json({"regression_threshold_hours": 12, "signals": [{"source": "github", "profile": "ops", "current_age_hours": 48, "baseline_age_hours": 24, "stale_signal_count": 3}, {"source": "rss", "profile": "growth", "current_age_hours": 5}]}))

    assert report["rows"][0]["status"] == "regressed"
    assert report["rows"][0]["freshness_delta_hours"] == 24.0
    assert report["rows"][1]["status"] == "insufficient_baseline"
    assert report["summary"]["stale_signal_count"] == 3
