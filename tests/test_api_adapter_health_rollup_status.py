from __future__ import annotations

import json

from max.api import adapter_health_rollup_status_to_json


def test_adapter_health_rollup_status_covers_healthy_degraded_and_empty() -> None:
    empty = json.loads(adapter_health_rollup_status_to_json({"adapters": []}))
    assert empty["overall_status"] == "ok"
    assert empty["total_adapters"] == 0
    assert empty["unhealthy_adapters"] == []

    rendered = json.loads(adapter_health_rollup_status_to_json({"as_of": "2026-06-01T12:00:00Z", "adapters": [{"adapter": "ok", "circuit_state": "closed", "last_successful_fetch_at": "2026-06-01T11:00:00Z"}, {"adapter": "open", "circuit_state": "open", "last_successful_fetch_at": "2026-06-01T11:00:00Z"}, {"adapter": "stale", "recent_error_rate": 0.2, "last_successful_fetch_at": "2026-05-01T00:00:00Z"}]}))
    assert rendered["overall_status"] == "critical"
    assert rendered["unhealthy_count"] == 2
    assert [row["adapter"] for row in rendered["unhealthy_adapters"]] == ["open", "stale"]
