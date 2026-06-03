from __future__ import annotations

import json

from max.api.insight_evidence_recency_skew_status import insight_evidence_recency_skew_status_to_json


def test_insight_evidence_recency_skew_status_accepts_mapping_and_classifies() -> None:
    report = json.loads(insight_evidence_recency_skew_status_to_json({"insights": {"i1": {"evidence": [{"published_at": "2026-05-31T00:00:00Z"}, {"published_at": "2026-05-01T00:00:00Z"}]}, "i2": {"signals": [{"timestamp": "2026-05-20T00:00:00Z"}, {"timestamp": "bad"}]}}}, now="2026-06-01T00:00:00Z", warning_days=14, critical_days=30))

    assert [row["insight_id"] for row in report["insight_rows"]] == ["i1", "i2"]
    assert report["insight_rows"][0]["oldest_age_days"] == 31
    assert report["insight_rows"][0]["age_spread_days"] == 30
    assert report["insight_rows"][1]["malformed_timestamps"] == 1


def test_insight_evidence_recency_skew_status_accepts_list_and_evidence_items() -> None:
    report = json.loads(insight_evidence_recency_skew_status_to_json({"insights": [{"insight_id": "fresh", "evidence_items": [{"created_at": "2026-05-31T00:00:00Z"}]}]}, now="2026-06-01T00:00:00Z"))

    assert report["insight_rows"][0]["newest_age_days"] == 1
    assert report["insight_rows"][0]["status"] == "ok"
