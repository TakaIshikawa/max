from __future__ import annotations

import json

from max.api.profile_run_readiness import KIND, SCHEMA_VERSION, profile_run_readiness_to_json


def test_profile_run_readiness_derives_readiness_from_checks() -> None:
    payload = {
        "profiles": [
            {"profile_id": "p2", "name": "Ops", "checks": [{"check": "credentials", "status": "failed", "message": "missing token"}]},
            {"profile_id": "p1", "name": "Growth", "checks": [{"check": "budget", "status": "pass"}, {"check": "source_configuration", "status": "warning", "message": "low coverage"}]},
        ]
    }

    parsed = json.loads(profile_run_readiness_to_json(payload))

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {"blocked_count": 1, "ready_count": 1, "total_count": 2, "warning_count": 1}
    assert [row["profile_id"] for row in parsed["profiles"]] == ["p1", "p2"]
    assert parsed["ready_profiles"] == [{"name": "Growth", "profile_id": "p1"}]
    assert parsed["blocked_profiles"] == [{"name": "Ops", "profile_id": "p2"}]
    assert parsed["warnings"] == [{"check": "source_configuration", "message": "low coverage", "profile_id": "p1"}]
    assert [row["profile_id"] for row in parsed["check_matrix"]] == ["p1", "p1", "p2"]
    assert parsed["next_actions"][0]["id"] == "fix-p2"


def test_profile_run_readiness_honors_explicit_sections() -> None:
    parsed = json.loads(
        profile_run_readiness_to_json(
            {
                "profile_readiness": [{}],
                "summary": {"ready_count": 5},
                "ready_profiles": [{"profile_id": "ready"}],
                "blocked_profiles": [{"profile_id": "blocked"}],
                "warnings": [{"profile_id": "p", "check": "c"}],
                "check_matrix": [{"profile_id": "p", "check": "c", "status": "pass"}],
                "next_actions": [{"id": "manual"}],
            }
        )
    )

    assert parsed["summary"]["ready_count"] == 5
    assert parsed["ready_profiles"][0]["profile_id"] == "ready"
    assert parsed["blocked_profiles"][0]["profile_id"] == "blocked"
    assert parsed["warnings"][0]["check"] == "c"
    assert parsed["check_matrix"][0]["status"] == "pass"
    assert parsed["next_actions"][0]["id"] == "manual"
