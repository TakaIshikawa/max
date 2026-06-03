from __future__ import annotations

import json

from max.api import insight_synthesis_queue_saturation_status_to_json


def test_insight_synthesis_queue_saturation_status_summarizes_and_sorts() -> None:
    data = json.loads(insight_synthesis_queue_saturation_status_to_json({"queues": [{"profile": "core", "pending_signal_count": 8, "batch_capacity": 10, "oldest_pending_age_minutes": 130, "failed_batch_count": 1}, {"profile": "growth", "pending_signal_count": 12, "batch_capacity": 10, "oldest_pending_age_minutes": 90}, {"profile": "ops", "pending_signal_count": 1, "batch_capacity": 10, "oldest_pending_age_minutes": 10}]}))
    assert data["summary"]["profile_count"] == 3
    assert data["summary"]["saturated_profile_count"] == 2
    assert data["summary"]["critical_count"] == 1
    assert data["summary"]["warning_count"] == 1
    assert data["summary"]["total_pending_signal_count"] == 21
    assert [row["profile"] for row in data["queues"]] == ["growth", "core", "ops"]
    assert data["queues"][0]["saturation_ratio"] == 1.2


def test_insight_synthesis_queue_saturation_status_accepts_rows_and_overrides() -> None:
    data = json.loads(insight_synthesis_queue_saturation_status_to_json({"rows": [{"profile": "p", "pending_signal_count": 5, "batch_capacity": 10, "oldest_pending_age_minutes": 50}], "warning_saturation_ratio": 0.4}))
    assert data["status"] == "warning"
    assert data["queues"][0]["age_minutes"] == 50.0
