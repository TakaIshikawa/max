from __future__ import annotations

import json

from max.api.run_checkpoint_retention_status import run_checkpoint_retention_status_to_json


def test_run_checkpoint_retention_status_detects_cleanup_candidates() -> None:
    report = json.loads(run_checkpoint_retention_status_to_json({"checkpoints": [{"run_id": "r2", "checkpoint_id": "c2", "stage": "eval", "age_days": 20, "retention_days": 7}, {"run_id": "r1", "checkpoint_id": "c1", "age_days": 30, "retention_days": 7, "protected": True}, {"run_id": "r3", "checkpoint_id": "c3", "age_days": "bad", "retention_days": 7}]}))

    assert report["rows"][0]["checkpoint_id"] == "c2"
    assert report["rows"][0]["expired"] is True
    assert report["summary"]["checkpoint_count"] == 3
    assert report["summary"]["expired_count"] == 1
    assert report["summary"]["protected_count"] == 1
    assert report["summary"]["cleanup_candidate_count"] == 1
