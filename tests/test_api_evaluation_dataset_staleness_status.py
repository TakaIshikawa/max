from __future__ import annotations

import json

from max.api import evaluation_dataset_staleness_status_to_json


def test_evaluation_dataset_staleness_status_derives_age_and_flags_stale() -> None:
    parsed = json.loads(evaluation_dataset_staleness_status_to_json({"datasets": [{"dataset_id": "fresh", "last_refreshed_at": "2026-05-20T00:00:00Z", "target_refresh_days": 7}, {"dataset_id": "stale", "age_days": 15, "target_refresh_days": 7}, {"dataset_id": "critical", "age_days": 25, "target_refresh_days": 7}]}, as_of="2026-05-21T00:00:00Z"))

    assert [row["dataset_id"] for row in parsed["datasets"]] == ["critical", "stale", "fresh"]
    assert parsed["datasets"][2]["age_days"] == 1
    assert parsed["summary"]["stale_count"] == 2
    assert parsed["summary"]["oldest_age_days"] == 25
