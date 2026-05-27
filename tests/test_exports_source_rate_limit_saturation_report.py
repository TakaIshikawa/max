from __future__ import annotations

import json

from max.exports.source_rate_limit_saturation_report import build_source_rate_limit_saturation_report, render_source_rate_limit_saturation_report_json, render_source_rate_limit_saturation_report_markdown


def test_source_rate_limit_saturation_report_sorts_and_recommends() -> None:
    report = build_source_rate_limit_saturation_report([
        {"source": "b", "window": "1h", "requests_attempted": 0, "limited_requests": 5},
        {"source": "a", "window": "1h", "requests_attempted": 10, "limited_requests": 5, "retry_after_seconds": 30},
    ], threshold_percent=20)

    assert [row["source"] for row in report["saturation_rows"]] == ["a", "b"]
    assert report["saturation_rows"][0]["saturation_percent"] == 50.0
    assert report["saturation_rows"][1]["saturation_percent"] == 0.0
    assert report["summary"]["over_threshold_count"] == 1
    assert "throttle requests" in report["saturation_rows"][0]["allocation_recommendation"]
    assert json.loads(render_source_rate_limit_saturation_report_json(report))["summary"]["limited_request_count"] == 10
    assert "a 1h: 50.0%" in render_source_rate_limit_saturation_report_markdown(report)
