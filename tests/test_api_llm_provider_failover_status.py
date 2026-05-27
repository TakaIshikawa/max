from __future__ import annotations

import json

from max.api import llm_provider_failover_status_to_json


def test_llm_provider_failover_status_sorts_and_summarizes() -> None:
    parsed = json.loads(llm_provider_failover_status_to_json({"failovers": [{"provider": "b", "trigger_count": 2}, {"provider": "a", "trigger_count": 8, "recovery_state": "fallback_active"}, {"provider": "c", "trigger_count": 20, "last_triggered_at": "bad"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["schema_version"] == "max.api.llm_provider_failover_status.v1"
    assert parsed["kind"] == "max.api.llm_provider_failover_status"
    assert [row["provider"] for row in parsed["providers"]] == ["c", "a", "b"]
    assert [row["status"] for row in parsed["providers"]] == ["critical", "high", "medium"]
    assert parsed["providers"][0]["last_triggered_at"] is None
    assert parsed["summary"]["trigger_count"] == 30


def test_llm_provider_failover_status_empty_input_is_healthy() -> None:
    parsed = json.loads(llm_provider_failover_status_to_json({}))

    assert parsed["providers"] == []
    assert parsed["summary"]["status"] == "low"
    assert parsed["summary"]["health"] == "healthy"
    assert parsed["summary"]["provider_count"] == 0
