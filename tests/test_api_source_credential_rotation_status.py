from __future__ import annotations

import json

from max.api.source_credential_rotation_status import source_credential_rotation_status_to_json


def test_source_credential_rotation_status_ranks_expired_and_soon_expiring() -> None:
    parsed = json.loads(
        source_credential_rotation_status_to_json(
            {
                "credentials": [
                    {"id": "ok", "source": "rss", "owner": "ops", "days_until_expiry": 80},
                    {"id": "expired", "source": "github", "owner": "sec", "days_until_expiry": -1},
                    {"id": "soon", "source": "postman", "owner": "dev", "days_until_expiry": 3},
                ]
            }
        )
    )

    assert [row["credential_id"] for row in parsed["credentials"]] == ["expired", "soon", "ok"]
    assert parsed["credentials"][0]["severity"] == "expired"
    assert parsed["credentials"][1]["severity"] == "critical"


def test_source_credential_rotation_status_preserves_missing_owner_and_blocked_reason() -> None:
    parsed = json.loads(
        source_credential_rotation_status_to_json(
            {"source_credentials": [{"source_adapter": "slack", "rotation_blocked_reason": "vendor freeze", "expires_in_days": 12}]}
        )
    )

    assert parsed["credentials"][0]["credential_owner"] is None
    assert parsed["credentials"][0]["blocked_reason"] == "vendor freeze"
    assert parsed["credentials"][0]["severity"] == "blocked"
    assert parsed["summary"]["blocked_count"] == 1
