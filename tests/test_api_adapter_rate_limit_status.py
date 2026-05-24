from __future__ import annotations

import json

from max.api.adapter_rate_limit_status import adapter_rate_limit_status_to_json


def test_adapter_rate_limit_status_clamps_ratios_and_counts() -> None:
    parsed = json.loads(
        adapter_rate_limit_status_to_json(
            {
                "adapters": [
                    {"adapter": "a", "source": "s", "limit": "100", "remaining": "200"},
                    {"adapter": "b", "source": "s", "limit": "100", "remaining": "5"},
                    {"adapter": "c", "source": "q", "limit": "100", "remaining": "0"},
                    {"adapter": "d", "source": "q", "limit": "bad", "remaining": "bad", "throttled": "true"},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.adapter_rate_limit_status.v1"
    assert [row["adapter"] for row in parsed["adapters"]] == ["c", "d", "b", "a"]
    assert parsed["adapters"][-1]["remaining_ratio"] == 1.0
    assert parsed["summary"]["exhausted_count"] == 1
    assert parsed["summary"]["throttled_count"] == 1
    assert parsed["summary"]["near_limit_count"] == 1
    assert parsed["summary"]["total_remaining"] == 105


def test_adapter_rate_limit_status_aliases_totals_and_metadata() -> None:
    parsed = json.loads(adapter_rate_limit_status_to_json({"rate_limits": [{"adapter_name": "a", "source_name": "s", "limit_count": "10", "remaining_count": "1"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["adapter_totals"][0]["adapter"] == "a"
    assert parsed["source_totals"][0]["source"] == "s"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
