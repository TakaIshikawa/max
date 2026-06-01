from __future__ import annotations

import json

from max.api import insight_staleness_distribution_status_to_json


def test_insight_staleness_distribution_status_buckets_and_sorts_expired() -> None:
    report = json.loads(insight_staleness_distribution_status_to_json({"stale_days": 30, "insights": [{"id": "fresh", "age_days": 1}, {"id": "expired-1", "age_days": 45}, {"id": "expired-2", "age_days": 60}]}))

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["expired_count"] == 2
    assert [row["insight_id"] for row in report["expired_insights"]] == ["expired-2", "expired-1"]


def test_insight_staleness_distribution_status_supports_iso_dates() -> None:
    report = json.loads(insight_staleness_distribution_status_to_json({"as_of": "2026-06-10T00:00:00Z", "insights": [{"id": "i1", "generated_at": "2026-06-01T00:00:00Z", "profile": "p", "source": "crm"}]}))

    assert report["insights"][0]["age_days"] == 9.0
    assert report["insights"][0]["bucket"] == "stale"
    assert report["groups"][0]["profile"] == "p"
