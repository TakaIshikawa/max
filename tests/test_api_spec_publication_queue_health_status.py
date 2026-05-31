from __future__ import annotations

import json

from max.api import spec_publication_queue_health_status_to_json


def test_spec_publication_queue_health_groups_targets_and_escalates() -> None:
    report = json.loads(spec_publication_queue_health_status_to_json({"queued_specs": [{"target_type": "daemon", "target_name": "prod", "status": "blocked"}, {"target_type": "filesystem", "target_name": "local", "status": "retrying"}, {"target_type": "filesystem", "target_name": "local", "status": "pending"}]}))

    assert report["summary"]["severity"] == "critical"
    assert report["targets"][0]["target_name"] == "prod"
    assert report["targets"][0]["blocked"] == 1
    assert report["targets"][1]["retrying"] == 1


def test_spec_publication_queue_health_empty_is_ok() -> None:
    report = json.loads(spec_publication_queue_health_status_to_json({}))

    assert report["summary"]["severity"] == "ok"
    assert report["targets"] == []
