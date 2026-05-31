from __future__ import annotations

import json

from max.api import incremental_synthesis_checkpoint_status_to_json


def test_incremental_synthesis_checkpoint_reports_stale_and_missing() -> None:
    report = json.loads(incremental_synthesis_checkpoint_status_to_json({"checkpoints": [{"source": "crm", "profile": "a", "last_processed_at": "2026-05-30T00:00:00Z"}, {"source": "web", "profile": "b"}]}, now="2026-05-31T12:00:00Z", stale_hours=24))

    assert report["summary"]["severity"] == "critical"
    assert report["summary"]["missing_count"] == 1
    assert report["checkpoints"][0]["source"] == "web"
    assert report["checkpoints"][1]["checkpoint_age_hours"] == 36.0


def test_incremental_synthesis_checkpoint_empty_is_ok() -> None:
    report = json.loads(incremental_synthesis_checkpoint_status_to_json({}, now="2026-05-31T00:00:00Z"))

    assert report["summary"]["severity"] == "ok"
