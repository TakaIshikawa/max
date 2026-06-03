from __future__ import annotations

import json

from max.api.adapter_oauth_refresh_failure_status import adapter_oauth_refresh_failure_status_to_json


def test_adapter_oauth_refresh_failure_status_accepts_mapping_and_sorts() -> None:
    report = json.loads(adapter_oauth_refresh_failure_status_to_json({"adapters": {"ok": {"refresh_attempts": 100, "refresh_failures": 1}, "warn": {"refresh_attempts": 100, "refresh_failures": 5}, "crit": {"refresh_attempts": 20, "refresh_failures": 4}}}))

    assert [row["adapter"] for row in report["adapters"]] == ["crit", "warn", "ok"]
    assert report["adapters"][0] == {"adapter": "crit", "refresh_attempts": 20, "refresh_failures": 4, "failure_rate": 0.2, "status": "critical"}
    assert report["summary"] == {"total_adapters": 3, "critical_adapters": 1, "warning_adapters": 1, "total_refresh_failures": 10, "highest_failure_adapter": "crit"}


def test_adapter_oauth_refresh_failure_status_handles_list_and_zero_attempts() -> None:
    report = json.loads(adapter_oauth_refresh_failure_status_to_json([{"adapter": "idle", "refresh_attempts": 0, "refresh_failures": 0}, {"adapter": "broken", "refresh_attempts": 0, "refresh_failures": 1}], failure_rate_warning=0.1, failure_rate_critical=0.5))

    assert [row["adapter"] for row in report["adapters"]] == ["broken", "idle"]
    assert report["adapters"][0]["status"] == "critical"
    assert report["adapters"][0]["failure_rate"] == 1.0
    assert report["adapters"][1]["status"] == "ok"
    assert report["adapters"][1]["failure_rate"] == 0.0
