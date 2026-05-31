from __future__ import annotations

import json

from max.api.source_fetch_success_rate_status import source_fetch_success_rate_status_to_json


def test_source_fetch_success_rate_status_groups_and_orders_by_severity() -> None:
    report = json.loads(
        source_fetch_success_rate_status_to_json(
            {
                "sources": [
                    {"source": "docs", "attempts": 10, "successes": 10},
                    {"source": "hn", "attempts": 10, "successes": 8, "recent_error_count": 2},
                    {"source": "github", "attempts": 10, "successes": 5, "failures": 5},
                    {"source": "empty", "attempts": 0},
                ]
            }
        )
    )

    assert [row["source"] for row in report["rows"]] == ["github", "hn", "empty", "docs"]
    assert [row["severity"] for row in report["rows"]] == ["critical", "warn", "unknown", "healthy"]
    assert report["rows"][0]["success_rate"] == 0.5
    assert report["rows"][1]["recent_error_count"] == 2
    assert report["summary"]["overall_success_rate"] == 0.7667


def test_source_fetch_success_rate_status_supports_threshold_overrides() -> None:
    report = json.loads(
        source_fetch_success_rate_status_to_json(
            {"sources": [{"source": "api", "attempts": 10, "successes": 8}]},
            warning_threshold=0.7,
            critical_threshold=0.5,
        )
    )

    assert report["rows"][0]["severity"] == "healthy"
    assert report["summary"]["warning_threshold"] == 0.7
