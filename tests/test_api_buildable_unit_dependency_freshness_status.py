from __future__ import annotations

import json

from max.api import buildable_unit_dependency_freshness_status_to_json


def test_buildable_unit_dependency_freshness_status_normalizes_nested_dependencies() -> None:
    data = json.loads(buildable_unit_dependency_freshness_status_to_json({"stale_days": 30, "critical_days": 90, "units": [{"unit_id": "u2", "stack": "python", "dependencies": {"django": {"current_version": "4", "latest_version": "5", "days_behind": 100}}}, {"unit_id": "u1", "stack": "node", "dependencies": [{"name": "vite", "days_behind": 40}]}]}))

    assert data["status"] == "critical"
    assert data["summary"]["unit_count"] == 2
    assert data["summary"]["stale_unit_count"] == 2
    assert data["summary"]["stale_dependency_count"] == 2
    assert data["units"][0]["unit_id"] == "u2"
    assert data["units"][0]["dependencies"][0]["name"] == "django"
    assert data["stack_hot_spots"][0]["stale_unit_count"] == 1
