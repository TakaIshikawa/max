from __future__ import annotations

import json

from max.api import run_budget_checkpoint_status_to_json


def test_run_budget_checkpoint_stage_rollups_and_limits() -> None:
    parsed = json.loads(run_budget_checkpoint_status_to_json({"checkpoints": [
        {"stage": "fetch", "checkpoint_id": "ok", "reserved_tokens": 100, "used_tokens": 20, "reserved_cost": 10, "actual_cost": 2, "soft_limit": 90, "hard_limit": 120},
        {"stage": "eval", "checkpoint_id": "soft", "reserved_tokens": 100, "used_tokens": 95, "reserved_cost": 10, "actual_cost": 4, "soft_limit": 90, "hard_limit": 120},
        {"stage": "eval", "checkpoint_id": "hard", "reserved_tokens": 100, "used_tokens": 121, "reserved_cost": 10, "actual_cost": 4, "soft_limit": 90, "hard_limit": 120},
    ]}, as_of="2026-06-01T00:00:00Z"))
    assert parsed["schema_version"] == "max.api.run_budget_checkpoint_status.v1"
    assert parsed["summary"]["status"] == "critical"
    assert {row["stage"]: row["status"] for row in parsed["stage_rollups"]}["eval"] == "critical"
    assert [row["checkpoint_id"] for row in parsed["checkpoints"][:2]] == ["hard", "soft"]
