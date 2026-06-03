from __future__ import annotations

import json

from max.api import feedback_reviewer_sla_breach_status_to_json


def test_feedback_reviewer_sla_breach_status_computes_age_and_hot_spots() -> None:
    data = json.loads(feedback_reviewer_sla_breach_status_to_json({"as_of": "2026-06-03T00:00:00Z", "reviewers": [{"reviewer": "Taka", "profile": "core", "open_reviews": 2, "oldest_opened_at": "2026-06-01T00:00:00Z", "sla_hours": 24, "breached_reviews": 1}, {"reviewer": "Ari", "profile": "growth", "open_reviews": 3, "oldest_opened_at": "2026-05-30T00:00:00Z", "sla_hours": 24, "breached_reviews": 2}]}))

    assert data["status"] == "critical"
    assert data["summary"]["reviewer_count"] == 2
    assert data["summary"]["breached_reviewer_count"] == 2
    assert data["summary"]["breached_review_total"] == 3
    assert data["summary"]["overdue_profile_count"] == 2
    assert data["reviewers"][0]["reviewer"] == "ari"
    assert data["reviewers"][0]["oldest_open_age_hours"] == 96.0
