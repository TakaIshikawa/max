from __future__ import annotations

import json

from max.api import adapter_circuit_breaker_recovery_status_to_json


def test_adapter_circuit_breaker_recovery_status_groups_and_blocks() -> None:
    parsed = json.loads(
        adapter_circuit_breaker_recovery_status_to_json(
            {
                "adapters": [
                    {"adapter": "closed", "state": "closed"},
                    {"adapter": "half", "state": "half-open", "failure_streak": 1},
                    {"adapter": "open", "state": "open"},
                    {"adapter": "stuck", "state": "open", "failure_streak": 6},
                ]
            }
        )
    )

    assert [row["adapter"] for row in parsed["adapters"]] == ["stuck", "open", "closed", "half"]
    assert parsed["blocked_adapters"] == ["stuck", "open"]
    assert parsed["summary"]["ready_count"] == 2
    assert parsed["summary"]["stuck_count"] == 1


def test_adapter_circuit_breaker_recovery_status_normalizes_cooldown() -> None:
    parsed = json.loads(adapter_circuit_breaker_recovery_status_to_json({"circuit_breakers": [{"adapter_name": "a", "breaker_state": "open", "cooldown_remaining": -5, "retry_after": 9}]}))

    assert parsed["adapters"][0]["cooldown_remaining_seconds"] == 0
    assert parsed["adapters"][0]["retry_after_seconds"] == 9
    assert parsed["adapters"][0]["status"] == "cooling_down"

