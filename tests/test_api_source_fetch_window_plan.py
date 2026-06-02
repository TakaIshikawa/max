from __future__ import annotations

import json

from max.api.source_fetch_window_plan import source_fetch_window_plan_to_json


def test_source_fetch_window_plan_orders_active_windows_by_priority() -> None:
    parsed = json.loads(
        source_fetch_window_plan_to_json(
            {
                "windows": [
                    {"source": "rss", "profile": "core", "priority": "low", "expected_budget_tokens": 50},
                    {"source": "github", "profile": "core", "priority": "high", "expected_budget_tokens": 100},
                ]
            }
        )
    )

    assert [row["source"] for row in parsed["fetch_windows"]] == ["github", "rss"]
    assert parsed["summary"]["active_count"] == 2
    assert parsed["summary"]["expected_budget_tokens"] == 150


def test_source_fetch_window_plan_counts_skipped_and_budget_limited_windows() -> None:
    parsed = json.loads(
        source_fetch_window_plan_to_json(
            {
                "fetch_windows": [
                    {"source_name": "hn", "skip_reason": "budget_limited", "priority": "critical"},
                    {"source_name": "postman", "skipped": True, "skipped_reason": "disabled"},
                ]
            }
        )
    )

    assert parsed["summary"]["skipped_count"] == 2
    assert parsed["summary"]["budget_limited_count"] == 1
    assert parsed["fetch_windows"][0]["skipped_reason"] == "budget_limited"


def test_source_fetch_window_plan_empty_input() -> None:
    parsed = json.loads(source_fetch_window_plan_to_json({}))

    assert parsed["summary"] == {"active_count": 0, "budget_limited_count": 0, "expected_budget_tokens": 0, "skipped_count": 0}
    assert parsed["fetch_windows"] == []
