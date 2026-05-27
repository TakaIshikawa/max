from __future__ import annotations

import json

from max.api.unit_generation_diversity_status import unit_generation_diversity_status_to_json


def test_unit_generation_diversity_status_flags_dominant_segments() -> None:
    report = json.loads(
        unit_generation_diversity_status_to_json(
            {
                "segments": [
                    {"profile": "p", "mode": "auto", "stack": "web", "target_user": "admin", "unit_count": 80, "minimum_share_ratio": 0.7},
                    {"profile": "p", "mode": "manual", "stack": "mobile", "target_user": "admin", "unit_count": 20, "minimum_share_ratio": 0.7},
                ]
            }
        )
    )

    assert report["summary"]["total_units"] == 100
    assert report["summary"]["distinct_stack_count"] == 2
    assert report["summary"]["distinct_mode_count"] == 2
    assert report["rows"][0]["share_ratio"] == 0.8
    assert {"segment_type": "stack", "segment": "web", "share_ratio": 0.8} in report["summary"]["dominant_segments"]
    assert {"segment_type": "mode", "segment": "auto", "share_ratio": 0.8} in report["summary"]["dominant_segments"]
