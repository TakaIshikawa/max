from __future__ import annotations

import json

from max.api.gap_detection_coverage_status import gap_detection_coverage_status_to_json


def test_gap_detection_coverage_status_calculates_ratios_and_zero_gaps() -> None:
    report = json.loads(
        gap_detection_coverage_status_to_json(
            {
                "groups": [
                    {"profile": "p", "domain": "billing", "detected_gaps": 10, "addressed_gaps": 4, "ignored_gaps": 1, "target_coverage_ratio": 0.8},
                    {"profile": "p", "domain": "empty", "detected_gaps": 0, "addressed_gaps": 0, "ignored_gaps": 0, "target_coverage_ratio": 0.8},
                ]
            }
        )
    )

    assert report["rows"][0]["undercovered"] is True
    assert report["rows"][0]["coverage_ratio"] == 0.4
    assert report["rows"][1]["coverage_ratio"] == 1.0
    assert report["summary"]["total_detected_gaps"] == 10
    assert report["summary"]["total_addressed_gaps"] == 4
    assert report["summary"]["undercovered_count"] == 1
