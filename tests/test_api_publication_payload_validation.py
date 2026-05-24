from __future__ import annotations

import json

from max.api.publication_payload_validation import publication_payload_validation_to_json


def test_publication_payload_validation_groups_invalid_payloads() -> None:
    parsed = json.loads(
        publication_payload_validation_to_json(
            {
                "payloads": [
                    {"id": "p2", "destination": "slack", "warnings": [{"code": "length"}]},
                    {"id": "p1", "destination": "slack", "errors": [{"code": "schema", "blocking": True}]},
                    {"id": "p3", "destination": "jira", "errors": [{"code": "schema", "blocking": True}]},
                ]
            }
        )
    )

    assert parsed["summary"]["status"] == "invalid"
    assert parsed["blocked_payload_ids"] == ["p3", "p1"]
    assert parsed["schema_error_summaries"] == [{"destination": "jira", "code": "schema", "count": 1}, {"destination": "slack", "code": "schema", "count": 1}]


def test_publication_payload_validation_warnings_do_not_block_valid_counts() -> None:
    parsed = json.loads(publication_payload_validation_to_json({"payloads": [{"id": "p1"}, {"id": "p2", "warnings": ["minor"]}]}))

    assert parsed["summary"]["valid_count"] == 1
    assert parsed["summary"]["warn_count"] == 1
    assert parsed["summary"]["blocked_count"] == 0
