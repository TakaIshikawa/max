from __future__ import annotations

import json

from max.api.publication_failure_triage import (
    KIND,
    SCHEMA_VERSION,
    publication_failure_triage_to_json,
)


def test_publication_failure_triage_to_json_normalizes_and_derives_retryable_counts() -> None:
    payload = {
        "schema_version": "max.publication_failure_triage.v1",
        "kind": "max.publication_failure_triage",
        "summary": {"attempt_count": 4, "open_failure_count": 2, "affected_idea_count": 2},
        "failure_groups": [
            {
                "target_type": "jira",
                "target_url": "https://jira.example/A",
                "status": "failed",
                "open_failure_count": 1,
                "affected_idea_count": 1,
                "latest_failure_at": "2026-05-20T00:00:00",
                "latest_error": "service unavailable",
                "retry_priority": "p1",
            },
            {
                "target_type": "github",
                "target_url": "https://github.example/B",
                "status": "failed",
                "open_failure_count": 1,
                "latest_error": "validation failed",
                "response_status": 422,
                "owner": "devrel",
            },
        ],
        "escalation_actions": [{"action": "Page destination owner", "owner": "ops"}],
    }

    output = publication_failure_triage_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"]["retryable_failure_count"] == 1
    assert [row["target_type"] for row in parsed["failures"]] == ["github", "jira"]
    assert parsed["categories"] == [
        {"category": "github", "count": 1, "retryable_count": 0},
        {"category": "jira", "count": 1, "retryable_count": 1},
    ]
    assert parsed["retryable_failures"] == [
        {
            "id": "F1",
            "reason": "service unavailable",
            "target_type": "jira",
            "target_url": "https://jira.example/A",
        }
    ]
    assert parsed["destination_health"][0]["status"] == "degraded"
    assert parsed["owner_assignments"] == [
        {"failure_ids": ["F2"], "owner": "devrel", "target_type": None}
    ]
    assert parsed["escalation_actions"][0]["owner"] == "ops"
    assert parsed["metadata"]["source_kind"] == "max.publication_failure_triage"
    assert output == publication_failure_triage_to_json(payload)


def test_publication_failure_triage_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(publication_failure_triage_to_json({}))

    assert parsed["summary"] == {
        "affected_idea_count": 0,
        "attempt_count": 0,
        "failure_count": 0,
        "open_failure_count": 0,
        "retryable_failure_count": 0,
    }
    assert parsed["failures"] == []
    assert parsed["categories"] == []
    assert parsed["retryable_failures"] == []
    assert parsed["destination_health"] == []
    assert parsed["owner_assignments"] == []
    assert parsed["escalation_actions"] == []
    assert parsed["metadata"]["source_schema_version"] is None
