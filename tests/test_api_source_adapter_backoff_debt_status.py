from __future__ import annotations

import json

from max.api import source_adapter_backoff_debt_status_to_json


def test_source_adapter_backoff_debt_status_orders_by_severity() -> None:
    report = json.loads(source_adapter_backoff_debt_status_to_json({"max_delay_threshold_seconds": 100, "adapters": [{"adapter": "crm", "delayed_fetches": 4, "remaining_delay_seconds": 120}, {"adapter": "mail", "delayed_fetches": 8, "remaining_delay_seconds": 20}]}))

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["total_delayed_fetches"] == 12
    assert report["summary"]["max_remaining_delay_seconds"] == 120
    assert [row["adapter"] for row in report["adapters"]] == ["crm", "mail"]


def test_source_adapter_backoff_debt_status_zero_delays_are_healthy() -> None:
    report = json.loads(source_adapter_backoff_debt_status_to_json({"adapters": [{"adapter": "crm"}]}))

    assert report["summary"]["status"] == "healthy"
    assert report["adapters"] == []
