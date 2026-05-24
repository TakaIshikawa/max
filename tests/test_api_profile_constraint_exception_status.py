from __future__ import annotations

import json

from max.api.profile_constraint_exception_status import profile_constraint_exception_status_to_json


def test_profile_constraint_exception_status_derives_review_counts() -> None:
    parsed = json.loads(
        profile_constraint_exception_status_to_json(
            {
                "exceptions": [
                    {"id": "a", "profile": "p", "constraint": "latency", "status": "active", "severity": "low"},
                    {"id": "b", "profile": "p", "constraint": "cost", "pending_review": "true", "severity": "high"},
                    {"id": "c", "profile": "q", "constraint": "data", "status": "expired"},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.profile_constraint_exception_status.v1"
    assert [row["exception_id"] for row in parsed["exceptions"]] == ["c", "b", "a"]
    assert parsed["summary"]["active_count"] == 1
    assert parsed["summary"]["expired_count"] == 1
    assert parsed["summary"]["pending_review_count"] == 1
    assert parsed["summary"]["review_required_count"] == 2


def test_profile_constraint_exception_status_aliases_totals_and_metadata() -> None:
    parsed = json.loads(profile_constraint_exception_status_to_json({"constraint_exceptions": [{"exception_id": "e", "profile": "p", "constraint": "x", "review_required": True, "expires_at": "later"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["exceptions"][0]["status"] == "pending_review"
    assert parsed["profile_totals"][0]["profile"] == "p"
    assert parsed["severity_totals"][0]["severity"] == "medium"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
