from __future__ import annotations

import json

from max.api import publisher_payload_schema_status_to_json


def test_publisher_payload_schema_valid_invalid_stale_mixed() -> None:
    parsed = json.loads(publisher_payload_schema_status_to_json({"destinations": [
        {"destination_id": "ok", "schema_version": "v1", "last_validation_result": "valid", "last_validated_at": "2026-06-01T00:00:00Z"},
        {"destination_id": "bad", "schema_version": "v2", "last_validation_result": "failed", "error_count": 2},
        {"destination_id": "stale", "schema_version": "v1", "last_validation_result": "valid", "last_validated_at": "2026-05-01T00:00:00Z"},
    ]}, as_of="2026-06-01T00:00:00Z"))
    assert parsed["schema_version"] == "max.api.publisher_payload_schema_status.v1"
    assert parsed["summary"]["status"] == "critical"
    assert parsed["destinations"][0]["destination_id"] == "bad"
    assert any(row["stale"] and row["status"] == "warning" for row in parsed["destinations"])
