from __future__ import annotations

import json

from max.api import publisher_webhook_signature_status_to_json


def test_webhook_signature_status_hides_secret_and_escalates() -> None:
    parsed = json.loads(publisher_webhook_signature_status_to_json({"destinations": [
        {"destination_id": "ok", "provider": "slack", "secret_ref": "vault://secret", "signature_algorithm": "hmac-sha256", "required_algorithm": "hmac-sha256"},
        {"destination_id": "missing", "provider": "jira", "signature_algorithm": "hmac-sha1", "required_algorithm": "hmac-sha256"},
        {"destination_id": "fail", "provider": "teams", "secret_ref": "vault://x", "verification_failures": 3},
        {"destination_id": "rotate", "provider": "web", "secret_ref": "vault://y", "signature_algorithm": "hmac-sha256", "required_algorithm": "hmac-sha256", "rotation_due_at": "2026-06-10T00:00:00Z"},
    ]}, as_of="2026-06-01T00:00:00Z"))
    assert parsed["schema_version"] == "max.api.publisher_webhook_signature_status.v1"
    assert parsed["summary"]["status"] == "critical"
    assert parsed["affected_destinations"][0]["destination_id"] == "missing"
    assert "secret_ref" not in json.dumps(parsed)
    assert any(row["status"] == "warning" for row in parsed["destinations"])
