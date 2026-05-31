from __future__ import annotations

import json

from max.api.tact_spec_validation_failure_status import tact_spec_validation_failure_status_to_json


def test_tact_spec_validation_failure_status_clean_validation() -> None:
    parsed = json.loads(tact_spec_validation_failure_status_to_json({}))

    assert parsed["summary"]["status"] == "healthy"


def test_tact_spec_validation_failure_status_blocking_failures() -> None:
    parsed = json.loads(tact_spec_validation_failure_status_to_json({"failures": [{"template": "brief", "field_path": "$.title", "severity": "error"}]}))

    assert parsed["summary"]["status"] == "critical"
    assert parsed["summary"]["blocking_failure_count"] == 1


def test_tact_spec_validation_failure_status_nonblocking_warnings() -> None:
    parsed = json.loads(tact_spec_validation_failure_status_to_json({"issues": [{"template": "brief", "path": "$.body", "severity": "warning", "blocking": False}]}))

    assert parsed["summary"]["status"] == "warning"
    assert parsed["summary"]["nonblocking_warning_count"] == 1


def test_tact_spec_validation_failure_status_groups_repeated_fields_and_orders() -> None:
    parsed = json.loads(tact_spec_validation_failure_status_to_json({"failures": [{"template": "z", "field_path": "$.b", "severity": "warning", "blocking": False}, {"template": "a", "field_path": "$.a"}, {"template": "a", "field_path": "$.a"}]}))

    assert parsed["field_paths"][0] == {"field_path": "$.a", "occurrence_count": 2}
    assert parsed["failures"][0]["field_path"] == "$.a"
