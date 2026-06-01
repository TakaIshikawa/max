from __future__ import annotations

import json

from max.api import source_adapter_schema_migration_status_to_json


def test_source_adapter_schema_migration_status_groups_adapter_states() -> None:
    report = json.loads(
        source_adapter_schema_migration_status_to_json(
            {
                "target_schema_version": "v3",
                "adapters": [
                    {"adapter": "ok", "schema_version": "v3"},
                    {"adapter": "pending", "schema_version": "v2"},
                    {"adapter": "failed", "schema_version": "v2", "migration_failed": True},
                    {"adapter": "blocked", "schema_version": "v2", "blockers": ["contract"]},
                    {"adapter": "rollback", "status": "rollback_required"},
                ],
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["status"] == "critical"
    assert report["summary"]["current_count"] == 1
    assert report["summary"]["pending_count"] == 1
    assert report["summary"]["failed_count"] == 1
    assert report["summary"]["blocked_count"] == 1
    assert report["summary"]["rollback_required_count"] == 1
    assert report["affected_adapters"][0]["adapter"] == "failed"
