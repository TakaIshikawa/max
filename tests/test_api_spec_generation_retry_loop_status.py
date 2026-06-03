from __future__ import annotations

import json

from max.api.spec_generation_retry_loop_status import spec_generation_retry_loop_status_to_json


def test_spec_generation_retry_loop_status_accepts_mapping_and_classifies() -> None:
    report = json.loads(spec_generation_retry_loop_status_to_json({"jobs": {"j1": {"unit_id": "u1", "attempts": 4, "last_error": "timeout"}, "j2": {"unit_id": "u2", "attempts": 2, "last_error": "invalid"}, "j3": {"unit_id": "u3", "attempts": 5}}}))

    assert [row["job_id"] for row in report["job_rows"]] == ["j1", "j2", "j3"]
    assert [row["status"] for row in report["job_rows"]] == ["critical", "warning", "ok"]
    assert report["summary"]["max_attempts"] == 5


def test_spec_generation_retry_loop_status_handles_list_and_malformed_attempts() -> None:
    report = json.loads(spec_generation_retry_loop_status_to_json({"jobs": [{"job_id": "bad", "unit_id": "u1", "attempts": "nope", "last_error": "x"}]}))

    assert report["job_rows"][0]["attempts"] == 0
    assert report["job_rows"][0]["status"] == "ok"
