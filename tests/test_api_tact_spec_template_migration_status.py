from __future__ import annotations

import json

from max.api import tact_spec_template_migration_status_to_json


def test_tact_spec_template_migration_status_reports_readiness_and_failures() -> None:
    report = json.loads(tact_spec_template_migration_status_to_json({"target_version": "v2", "specs": [{"spec_id": "ready", "template_version": "v2"}, {"spec_id": "fail", "template_version": "v1", "validation_failures": ["shape"]}, {"spec_id": "block", "template_version": "v1", "rollback_blockers": ["snapshot"]}]}))
    assert report["readiness_status"] == "blocked"
    assert report["migrated_count"] == 1
    assert report["failure_buckets"] == {"incompatible": 0, "rollback_blockers": 1, "validation_failures": 1}
    assert "clear rollback blockers" in report["next_actions"]
