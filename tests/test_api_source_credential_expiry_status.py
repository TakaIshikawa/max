from __future__ import annotations

import json

from max.api.source_credential_expiry_status import source_credential_expiry_status_to_json


def test_source_credential_expiry_status_flags_expiry_and_missing_owner() -> None:
    report = json.loads(
        source_credential_expiry_status_to_json(
            {
                "credentials": [
                    {"source": "crm", "credential_name": "token", "expires_at": "2026-05-01", "days_until_expiry": -1, "rotation_owner": "", "warning_days": 14},
                    {"source": "ads", "credential_name": "key", "expires_at": "2026-06-01", "days_until_expiry": 5, "rotation_owner": "ops", "warning_days": 14},
                ]
            }
        )
    )

    assert [row["status"] for row in report["rows"]] == ["expired", "expiring_soon"]
    assert report["rows"][0]["missing_owner"] is True
    assert report["summary"]["expired_count"] == 1
    assert report["summary"]["expiring_soon_count"] == 1
    assert report["summary"]["missing_owner_count"] == 1
