from __future__ import annotations

import json

from max.api import publication_destination_credential_scope_status_to_json


def test_publication_destination_credential_scope_status_flags_missing_and_stale() -> None:
    report = json.loads(
        publication_destination_credential_scope_status_to_json(
            {
                "stale_verification_hours": 24,
                "destinations": [
                    {"destination": "prod", "credential_id": "c1", "required_actions": ["publish", "comment"], "granted_actions": ["publish"], "last_verified_at": "2026-06-01T00:00:00Z"},
                    {"destination": "stage", "credential_id": "c2", "required_actions": ["publish"], "allowed_actions": ["publish"], "granted_actions": ["publish", "label"], "last_verified_at": "2026-05-30T00:00:00Z"},
                    {"destination": "dev", "credential_id": "c3", "required_actions": ["publish"], "granted_actions": ["publish"], "last_verified_at": "2026-06-01T11:00:00Z"},
                ],
            },
            as_of="2026-06-01T12:00:00Z",
        )
    )

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["blocked_destination_count"] == 1
    assert report["summary"]["stale_verification_count"] == 1
    assert report["summary"]["next_destination_to_verify"] == "prod"
    assert report["destinations"][0]["missing_actions"] == ["comment"]
    assert report["status"] == "critical"
