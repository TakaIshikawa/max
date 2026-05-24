from __future__ import annotations

import json

from max.api.insight_freshness_window import insight_freshness_window_to_json


def test_insight_freshness_window_derives_statuses_and_summary() -> None:
    parsed = json.loads(
        insight_freshness_window_to_json(
            {
                "insights": [
                    {"id": "fresh", "profile": "p", "category": "c", "freshness_days": 5, "window_days": 10},
                    {"id": "stale", "profile": "p", "category": "c", "freshness_days": 11, "window_days": 10},
                    {"id": "expired", "profile": "q", "category": "d", "freshness_days": 20, "window_days": 10},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.insight_freshness_window.v1"
    assert [row["insight_id"] for row in parsed["insights"]] == ["expired", "stale", "fresh"]
    assert parsed["summary"] == {"expired_count": 1, "insight_count": 3, "refresh_needed_count": 2, "stale_count": 1}
    assert [row["insight_id"] for row in parsed["refresh_needed"]] == ["expired", "stale"]


def test_insight_freshness_window_aliases_totals_and_metadata() -> None:
    parsed = json.loads(insight_freshness_window_to_json({"freshness_windows": [{"insight_id": "i", "profile": "p", "category": "c", "age_days": "bad"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["insights"][0]["status"] == "fresh"
    assert parsed["profile_totals"][0]["profile"] == "p"
    assert parsed["category_totals"][0]["category"] == "c"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
