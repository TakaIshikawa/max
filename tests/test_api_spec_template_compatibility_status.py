from __future__ import annotations

import json

from max.api import spec_template_compatibility_status_to_json


def test_spec_template_compatibility_status_groups_specs() -> None:
    report = json.loads(
        spec_template_compatibility_status_to_json(
            {
                "current_template_version": "v3",
                "supported_template_versions": ["v2", "v3"],
                "required_blocks": ["summary"],
                "specs": [
                    {"spec_id": "ok", "template_version": "v3", "blocks": ["summary"]},
                    {"spec_id": "old", "template_version": "v2", "blocks": ["summary"]},
                    {"spec_id": "bad", "template_version": "v1", "blocks": []},
                ],
            },
            as_of="2026-06-01T00:00:00Z",
        )
    )

    assert report["status"] == "critical"
    assert report["summary"]["compatible_count"] == 1
    assert report["summary"]["migration_required_count"] == 1
    assert report["summary"]["incompatible_count"] == 1
    assert report["incompatible_specs"][0]["template_version"] == "v1"
    assert report["incompatible_specs"][0]["missing_blocks"] == ["summary"]
