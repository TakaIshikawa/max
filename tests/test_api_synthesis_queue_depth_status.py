from __future__ import annotations

import json

from max.api.synthesis_queue_depth_status import synthesis_queue_depth_status_to_json


def test_synthesis_queue_depth_status_aggregates_and_blocks_profiles() -> None:
    report = json.loads(
        synthesis_queue_depth_status_to_json(
            {
                "queues": [
                    {"profile": "p1", "priority": "high", "pending_count": 10, "processing_count": 2, "failed_count": 0, "oldest_pending_minutes": 90, "target_drain_minutes": 60},
                    {"profile": "p2", "priority": "low", "pending_count": 1, "processing_count": 1, "failed_count": 2, "oldest_pending_minutes": 10, "target_drain_minutes": 60},
                ]
            }
        )
    )

    assert report["summary"]["total_pending"] == 11
    assert report["summary"]["total_processing"] == 3
    assert report["summary"]["total_failed"] == 2
    assert report["rows"][0]["delayed"] is True
    assert report["summary"]["blocked_profiles"] == ["p1", "p2"]
