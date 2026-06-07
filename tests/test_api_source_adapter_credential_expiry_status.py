from __future__ import annotations

import json

from max.api import source_adapter_credential_expiry_status_to_json


def test_source_adapter_credential_expiry_status_reports_critical_adapter() -> None:
    data = json.loads(source_adapter_credential_expiry_status_to_json({"warning_days": 14, "critical_days": 3, "adapters": [{"adapter": "github", "credential_name": "token", "days_until_expiry": 20}, {"adapter": "reddit", "credential_name": "oauth", "days_until_expiry": 2}]}))

    assert data["status"] == "critical"
    assert data["adapter_count"] == 2
    assert data["expired_count"] == 0
    assert data["expiring_count"] == 1
    assert data["worst_adapter"] == "reddit"


def test_source_adapter_credential_expiry_status_supports_warning_and_empty() -> None:
    warning = json.loads(source_adapter_credential_expiry_status_to_json({"warning_days": 14, "critical_days": 3, "items": [{"source": "hn", "days_until_expiry": 10}]}))
    empty = json.loads(source_adapter_credential_expiry_status_to_json({}))

    assert warning["status"] == "warning"
    assert empty["status"] == "ok"
    assert empty["adapter_count"] == 0
