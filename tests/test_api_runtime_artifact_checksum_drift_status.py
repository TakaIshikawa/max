from __future__ import annotations

import json

from max.api import runtime_artifact_checksum_drift_status_to_json


def test_runtime_artifact_checksum_drift_status_compares_case_insensitively() -> None:
    report = json.loads(runtime_artifact_checksum_drift_status_to_json({"artifacts": [{"artifact_id": "ok", "expected_checksum": "ABC", "observed_checksum": "abc", "size_bytes": 1}, {"path": "/missing", "expected_checksum": "abc"}, {"artifact_id": "bad", "expected_checksum": "abc", "observed_checksum": "def", "size_bytes": 200_000_000}]}))

    assert [row["artifact_id"] for row in report["artifact_rows"]] == ["bad", "/missing", "ok"]
    assert report["artifact_rows"][0]["checksum_match"] is False
    assert report["artifact_rows"][1]["status"] == "warning"
    assert report["summary"]["checksum_mismatches"] == 1
