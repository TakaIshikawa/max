from __future__ import annotations

import json

from max.api.publication_destination_auth_health import publication_destination_auth_health_to_json


def test_publication_destination_auth_health_groups_statuses() -> None:
    parsed = json.loads(
        publication_destination_auth_health_to_json(
            {
                "expiry_warning_days": 10,
                "destinations": [
                    {"destination": "blog", "expires_at": "2026-06-30T00:00:00Z"},
                    {"destination": "slack", "expires_at": "2026-05-25T00:00:00Z"},
                    {"destination": "jira", "missing_scopes": ["Write"]},
                    {"destination": "hubspot", "failed_auth": True, "reason": "401"},
                ],
            },
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["summary"]["healthy_count"] == 1
    assert parsed["summary"]["expiring_count"] == 1
    assert parsed["summary"]["missing_scope_count"] == 1
    assert parsed["summary"]["failed_auth_count"] == 1
    assert parsed["failed_auth_destinations"][0]["destination"] == "hubspot"


def test_publication_destination_auth_health_aliases_scopes_and_metadata() -> None:
    parsed = json.loads(
        publication_destination_auth_health_to_json(
            {"auth_checks": [{"name": "teams", "token_expires_at": "2026-05-22T00:00:00Z", "missing_scope": "Publish"}], "metadata": {"run": "r1"}},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["missing_scope_destinations"][0]["missing_scopes"] == ["publish"]
    assert parsed["reauthorization_actions"][0]["action"] == "Grant missing publication scopes"
    assert parsed["metadata"]["run"] == "r1"
