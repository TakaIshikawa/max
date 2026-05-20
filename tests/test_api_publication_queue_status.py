from __future__ import annotations

import json

from max.api.publication_queue_status import (
    KIND,
    SCHEMA_VERSION,
    publication_queue_status_to_json,
)


def test_publication_queue_status_to_json_derives_queue_sections() -> None:
    payload = {
        "schema_version": "max.publication_queue_status.v1",
        "kind": "max.publication_queue_status",
        "publication_queue": [
            {
                "spec_id": "spec-z",
                "title": "Zendesk launch",
                "destination": "zendesk",
                "status": "queued",
                "owner": "support",
                "enqueued_at": "2026-05-20T12:00:00Z",
            },
            {
                "spec_id": "spec-g",
                "destination": "github",
                "status": "retrying",
                "owner": "devrel",
                "created_at": "2026-05-16T12:00:00Z",
                "attempt_count": "2",
                "next_retry_at": "2026-05-21T11:00:00Z",
            },
            {
                "spec_id": "spec-b",
                "destination": "jira",
                "status": "blocked",
                "owner": "product",
                "enqueued_at": "2026-04-01T00:00:00Z",
                "blocker_reasons": ["missing owner", "missing owner", "schema approval"],
            },
            {
                "spec_id": "spec-r",
                "destination": "jira",
                "status": "published_ready",
                "enqueued_at": "2026-05-01T00:00:00Z",
            },
        ],
    }

    output = publication_queue_status_to_json(payload, as_of="2026-05-21T12:00:00Z")
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {
        "blocked_count": 1,
        "published_ready_count": 1,
        "queued_count": 2,
        "retrying_count": 1,
        "total_count": 4,
    }
    assert [row["spec_id"] for row in parsed["queued_specs"]] == [
        "spec-b",
        "spec-g",
        "spec-r",
        "spec-z",
    ]
    assert parsed["queued_specs"][1]["retry_eligible"] is True
    assert parsed["destinations"] == [
        {
            "blocked_count": 0,
            "destination": "github",
            "published_ready_count": 0,
            "queued_count": 0,
            "retrying_count": 1,
        },
        {
            "blocked_count": 1,
            "destination": "jira",
            "published_ready_count": 1,
            "queued_count": 1,
            "retrying_count": 0,
        },
        {
            "blocked_count": 0,
            "destination": "zendesk",
            "published_ready_count": 0,
            "queued_count": 1,
            "retrying_count": 0,
        },
    ]
    assert parsed["retry_state"] == {
        "as_of": "2026-05-21T12:00:00Z",
        "eligible_retry_count": 1,
        "next_retry_at": "2026-05-21T11:00:00Z",
        "retrying_count": 1,
    }
    assert parsed["blocked_items"] == [
        {
            "blocker_reasons": ["missing owner", "schema approval"],
            "destination": "jira",
            "owner": "product",
            "spec_id": "spec-b",
        }
    ]
    assert parsed["owner_hints"] == [
        {"owner": "devrel", "reason": None, "spec_ids": ["spec-g"]},
        {"owner": "product", "reason": None, "spec_ids": ["spec-b"]},
        {"owner": "support", "reason": None, "spec_ids": ["spec-z"]},
    ]
    assert parsed["age_buckets"] == {
        "0_1d": 1,
        "2_7d": 1,
        "8_30d": 1,
        "over_30d": 1,
        "unknown": 0,
    }
    assert [row["id"] for row in parsed["next_actions"]] == ["retry-spec-g", "unblock-spec-b"]
    assert parsed["metadata"]["source_kind"] == "max.publication_queue_status"
    assert output == publication_queue_status_to_json(payload, as_of="2026-05-21T12:00:00Z")


def test_publication_queue_status_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(publication_queue_status_to_json({"queue_items": [{}]}))

    assert parsed["summary"] == {
        "blocked_count": 0,
        "published_ready_count": 0,
        "queued_count": 1,
        "retrying_count": 0,
        "total_count": 1,
    }
    assert parsed["queued_specs"] == [
        {
            "age_bucket": "unknown",
            "attempt_count": 0,
            "blocker_reasons": [],
            "destination": "unknown",
            "enqueued_at": None,
            "metadata": {},
            "next_retry_at": None,
            "owner": None,
            "retry_eligible": False,
            "spec_id": "Q1",
            "status": "queued",
            "target_url": None,
            "title": None,
        }
    ]
    assert parsed["destinations"] == [
        {
            "blocked_count": 0,
            "destination": "unknown",
            "published_ready_count": 0,
            "queued_count": 1,
            "retrying_count": 0,
        }
    ]
    assert parsed["retry_state"] == {
        "as_of": None,
        "eligible_retry_count": 0,
        "next_retry_at": None,
        "retrying_count": 0,
    }
    assert parsed["blocked_items"] == []
    assert parsed["owner_hints"] == []
    assert parsed["age_buckets"] == {
        "0_1d": 0,
        "2_7d": 0,
        "8_30d": 0,
        "over_30d": 0,
        "unknown": 1,
    }
    assert parsed["next_actions"] == []
    assert parsed["metadata"]["source_schema_version"] is None
