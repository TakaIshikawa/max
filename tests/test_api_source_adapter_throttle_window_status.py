from __future__ import annotations

import json

from max.api import source_adapter_throttle_window_status_to_json


def test_source_adapter_throttle_window_status_orders_blocked_first() -> None:
    report = json.loads(source_adapter_throttle_window_status_to_json({"adapters": [{"id": "ok", "name": "OK"}, {"id": "crm", "name": "CRM", "reset_after_seconds": 120, "window_seconds": 300}, {"id": "ads", "name": "Ads", "status": "blocked", "reset_at": "2026-06-01T00:00:00Z"}], "metadata": {"source": "ops"}}))

    assert report["schema_version"] == "max.api.source_adapter_throttle_window_status.v1"
    assert [row["id"] for row in report["adapters"]] == ["ads", "crm", "ok"]
    assert report["summary"]["status"] == "critical"
    assert report["throttled_adapters"][0]["adapter"] == "Ads"
    assert report["next_reset"] == "2026-06-01T00:00:00Z"
    assert report["metadata"]["source"] == "ops"


def test_source_adapter_throttle_window_status_empty_is_no_data() -> None:
    report = json.loads(source_adapter_throttle_window_status_to_json({}))

    assert report["summary"]["status"] == "no_data"
    assert report["adapters"] == []
