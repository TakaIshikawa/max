from __future__ import annotations

import json

from max.api.source_auth_health_status import source_auth_health_status_to_json


def test_source_auth_health_status_reports_credential_states() -> None:
    report = json.loads(
        source_auth_health_status_to_json(
            {
                "credentials": [
                    {"source": "valid", "configured": True, "expires_at": "2026-06-02T00:00:00Z"},
                    {"source": "missing", "configured": False},
                    {"source": "expired", "configured": True, "expires_at": "2026-05-30T00:00:00Z"},
                    {"source": "soon", "configured": True, "expires_at": "2026-05-31T12:00:00Z"},
                    {"source": "error", "configured": True, "last_auth_error": "401", "last_auth_error_at": "2026-05-31T01:30:00Z"},
                ]
            },
            now="2026-05-31T02:00:00Z",
            expiring_soon_seconds=86400,
            recent_error_seconds=3600,
        )
    )

    assert [row["source"] for row in report["rows"][:3]] == ["error", "expired", "missing"]
    assert report["summary"]["state_counts"]["valid"] == 1
    assert report["summary"]["state_counts"]["expiring_soon"] == 1
    assert report["summary"]["severity"] == "critical"
