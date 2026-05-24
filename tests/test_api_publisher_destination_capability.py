from __future__ import annotations

import json

from max.api.publisher_destination_capability import publisher_destination_capability_to_json


def test_publisher_destination_capability_normalizes_capabilities_and_unsupported_requests() -> None:
    parsed = json.loads(
        publisher_destination_capability_to_json(
            {
                "requested_destinations": ["jira", "github", "slack"],
                "destinations": [
                    {"name": "github", "artifact_types": ["spec", "brief", "spec"], "capabilities": ["update", "create"], "auth": "valid", "rate_limit": "ok", "supports_dry_run": "yes"},
                    {"destination": "jira", "supported_artifact_types": "ticket", "auth_status": "missing", "rate_limit_posture": "limited"},
                ],
            }
        )
    )

    assert parsed["destinations"][0]["supported_artifact_types"] == ["brief", "spec"]
    assert parsed["destinations"][0]["capabilities"] == ["create", "update"]
    assert parsed["unsupported_requests"] == [{"action": "configure publisher destination", "destination": "slack", "reason": "destination is not configured"}]
    assert parsed["summary"]["unsupported_request_count"] == 1


def test_publisher_destination_capability_auth_and_rate_limit_warnings() -> None:
    parsed = json.loads(publisher_destination_capability_to_json({"configured_destinations": [{"target_type": "x"}]}))

    assert parsed["auth_warnings"][0]["destination"] == "x"
    assert parsed["rate_limit_warnings"][0]["destination"] == "x"
    assert parsed["summary"]["auth_warning_count"] == 1


def test_publisher_destination_capability_schema_and_stable_json() -> None:
    payload = {"schema_version": "source.v1", "kind": "source.kind", "destinations": []}
    parsed = json.loads(publisher_destination_capability_to_json(payload, as_of="2026-05-21T00:00:00Z"))

    assert set(parsed) == {"schema_version", "kind", "summary", "destinations", "unsupported_requests", "auth_warnings", "rate_limit_warnings", "metadata"}
    assert parsed["metadata"]["source_kind"] == "source.kind"
    assert publisher_destination_capability_to_json(payload) == publisher_destination_capability_to_json(payload)
