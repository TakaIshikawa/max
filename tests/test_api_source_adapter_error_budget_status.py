from __future__ import annotations

import json

from max.api import source_adapter_error_budget_status_to_json


def test_source_adapter_error_budget_status_handles_zero_and_over_budget() -> None:
    report = json.loads(source_adapter_error_budget_status_to_json({"sources": [{"source": "zero", "adapter": "rss", "allowed_errors": 0, "consumed_errors": 1}, {"source": "warn", "allowed_errors": 10, "consumed_errors": 8}, {"source": "ok", "allowed_errors": 10, "consumed_errors": 1}]}))

    assert report["rows"][0]["source"] == "zero"
    assert report["rows"][0]["status"] == "over_budget"
    assert report["rows"][0]["burn_ratio"] == 1.0
    assert report["summary"]["status"] == "over_budget"
