from __future__ import annotations

import json

from max.api import signal_source_auth_scope_status_to_json


def test_signal_source_auth_scope_status_flags_missing_overbroad_and_expiring() -> None:
    report = json.loads(
        signal_source_auth_scope_status_to_json(
            {
                "warning_days": 14,
                "sources": [
                    {"source": "crm", "credential_id": "c1", "required_scopes": ["read"], "granted_scopes": []},
                    {"source": "ads", "credential_id": "c2", "required_scopes": ["read"], "allowed_scopes": ["read"], "granted_scopes": ["read", "admin"]},
                    {"source": "docs", "credential_id": "c3", "required_scopes": ["read"], "granted_scopes": ["read"], "expires_at": "2026-06-05T00:00:00Z"},
                ],
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["missing_scope_count"] == 1
    assert report["summary"]["overbroad_scope_count"] == 1
    assert report["summary"]["expiring_scope_count"] == 1
    assert report["sources"][0]["source"] == "crm"
    assert report["status"] == "critical"
