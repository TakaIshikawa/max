from __future__ import annotations

import json

from max.api.source_adapter_error_taxonomy import source_adapter_error_taxonomy_to_json


def test_source_adapter_error_taxonomy_accepts_fallback_keys_and_sorts() -> None:
    parsed = json.loads(
        source_adapter_error_taxonomy_to_json(
            {
                "adapter_errors": [
                    {"adapter": "zendesk", "source": "tickets", "error_type": "timeout", "severity": "low", "count": 4, "retryable": True},
                    {"adapter": "github", "source": "issues", "type": "auth", "severity": "critical", "occurrences": "2"},
                    {"adapter": "asana", "source": "tasks", "code": "quota", "severity": "high", "count": 5, "can_retry": "yes"},
                ]
            }
        )
    )

    assert [row["error_type"] for row in parsed["error_types"]] == ["auth", "quota", "timeout"]
    assert parsed["summary"]["total_error_count"] == 11
    assert parsed["retryability"] == {"non_retryable": 2, "retryable": 9}


def test_source_adapter_error_taxonomy_defaults_malformed_values() -> None:
    parsed = json.loads(source_adapter_error_taxonomy_to_json({"errors": [{"count": "bad", "severity": "urgent"}]}))

    assert parsed["error_types"][0]["error_type"] == "unknown_error"
    assert parsed["error_types"][0]["severity"] == "unknown"
    assert parsed["affected_sources"][0]["source"] == "unknown-source"
    assert parsed["summary"]["total_error_count"] == 1


def test_source_adapter_error_taxonomy_json_schema_fields_and_metadata() -> None:
    parsed = json.loads(
        source_adapter_error_taxonomy_to_json(
            {"schema_version": "source.v1", "kind": "source.kind", "error_events": []},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert set(parsed) == {
        "schema_version",
        "kind",
        "summary",
        "error_types",
        "affected_sources",
        "retryability",
        "next_actions",
        "metadata",
    }
    assert parsed["metadata"]["source_schema_version"] == "source.v1"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
    assert source_adapter_error_taxonomy_to_json({"error_events": []}) == source_adapter_error_taxonomy_to_json({"error_events": []})
