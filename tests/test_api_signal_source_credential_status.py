from __future__ import annotations

import json

from max.api.signal_source_credential_status import signal_source_credential_status_to_json


def test_signal_source_credential_status_handles_aliases_and_ordering() -> None:
    parsed = json.loads(
        signal_source_credential_status_to_json(
            {
                "credentials": [
                    {"id": "ok", "source": "crm", "provider": "salesforce", "status": "valid"},
                    {"id": "soon", "source_name": "ads", "vendor": "meta", "days_until_expiry": "5"},
                    {"id": "old", "source": "billing", "provider": "stripe", "days_until_expiry": "-1"},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.signal_source_credential_status.v1"
    assert parsed["kind"] == "max.api.signal_source_credential_status"
    assert [row["id"] for row in parsed["credentials"]] == ["soon", "old", "ok"]
    assert parsed["summary"]["expired_count"] == 1
    assert parsed["summary"]["expiring_soon_count"] == 1
    assert parsed["summary"]["valid_count"] == 1


def test_signal_source_credential_status_source_credentials_malformed_and_metadata() -> None:
    parsed = json.loads(
        signal_source_credential_status_to_json(
            {
                "schema_version": "source.v1",
                "kind": "source.kind",
                "metadata": {"tenant": "acme"},
                "source_credentials": [
                    {"credential_id": "missing", "source": "rss", "provider": "feed", "missing": "true"},
                    {"credential_id": "bad", "source": "api", "provider": "x", "days_until_expiry": "bad"},
                ],
            },
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["credentials"][0]["status"] == "missing"
    assert parsed["credentials"][1]["days_until_expiry"] is None
    assert parsed["summary"]["credential_count"] == 2
    assert parsed["summary"]["missing_count"] == 1
    assert parsed["summary"]["action_required_count"] == 1
    assert parsed["action_required"][0]["id"] == "missing"
    assert parsed["next_actions"][0]["credential_id"] == "missing"
    assert parsed["metadata"]["tenant"] == "acme"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
