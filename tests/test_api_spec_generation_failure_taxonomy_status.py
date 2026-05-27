from __future__ import annotations

import json

from max.api import spec_generation_failure_taxonomy_status_to_json


def test_spec_generation_failure_taxonomy_status_normalizes_unknown_and_retryability() -> None:
    parsed = json.loads(spec_generation_failure_taxonomy_status_to_json({"failures": [{"id": "a1", "idea_id": "i1", "cause": "missing evidence"}, {"id": "a2", "idea_id": "i2", "cause": "weird", "retryable": False}]}))

    assert parsed["schema_version"] == "max.api.spec_generation_failure_taxonomy_status.v1"
    assert parsed["summary"]["failure_count"] == 2
    assert parsed["summary"]["retryable_count"] == 1
    assert parsed["summary"]["non_retryable_count"] == 1
    assert [row["category"] for row in parsed["failures"]] == ["missing_evidence", "unknown"]
