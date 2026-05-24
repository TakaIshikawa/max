from __future__ import annotations

import json

from max.api.spec_export_destination_status import (
    KIND,
    SCHEMA_VERSION,
    spec_export_destination_status_to_json,
)


def test_spec_export_destination_status_to_json_counts_readiness() -> None:
    payload = {
        "schema_version": "max.spec_export_destination_status.v1",
        "kind": "max.spec_export_destination_status",
        "destinations": [
            {"name": "filesystem", "kind": "filesystem", "enabled": True, "last_success_at": "2026-05-20T00:00:00Z"},
            {"name": "tact", "kind": "tact_daemon", "enabled": True, "last_error": "timeout"},
            {"name": "remote", "kind": "remote_publisher", "enabled": False, "pending_count": 4},
        ],
    }

    output = spec_export_destination_status_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {
        "degraded_count": 1,
        "disabled_count": 1,
        "ready_count": 1,
        "total_destinations": 3,
    }
    assert [row["name"] for row in parsed["destinations"]] == ["tact", "remote", "filesystem"]
    assert parsed["counts_by_kind"] == {"filesystem": 1, "remote_publisher": 1, "tact_daemon": 1}
    assert output == spec_export_destination_status_to_json(payload)


def test_spec_export_destination_status_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(spec_export_destination_status_to_json({"export_destinations": [{}]}))

    assert parsed["destinations"][0] == {
        "destination_id": "destination-1",
        "enabled": True,
        "kind": "unknown",
        "last_error": None,
        "last_success_at": None,
        "metadata": {},
        "name": "destination-1",
        "pending_count": 0,
        "readiness": "ready",
    }
