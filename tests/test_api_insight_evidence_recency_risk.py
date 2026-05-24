from __future__ import annotations

import json

from max.api.insight_evidence_recency_risk import insight_evidence_recency_risk_to_json


def test_insight_evidence_recency_risk_buckets_from_as_of() -> None:
    parsed = json.loads(
        insight_evidence_recency_risk_to_json(
            {"stale_after_days": 10, "expired_after_days": 30, "insights": [{"id": "a", "evidence": [{"timestamp": "2026-05-20T00:00:00Z"}, {"timestamp": "2026-04-20T00:00:00Z"}]}]},
            as_of="2026-05-25T00:00:00Z",
        )
    )

    assert parsed["insights"][0]["status"] == "degraded"
    assert parsed["insights"][0]["evidence_age_buckets"] == [["expired", 1], ["fresh", 1]]


def test_insight_evidence_recency_risk_all_expired() -> None:
    parsed = json.loads(insight_evidence_recency_risk_to_json({"expired_after_days": 30, "insights": [{"id": "x", "profile": "P", "category": "C", "evidence": [{"observed_at": "2026-01-01T00:00:00Z"}]}]}, as_of="2026-05-25T00:00:00Z"))

    assert parsed["summary"]["status"] == "expired"
    assert parsed["profile_totals"][0]["bucket"] == "p"
    assert parsed["category_totals"][0]["bucket"] == "c"
