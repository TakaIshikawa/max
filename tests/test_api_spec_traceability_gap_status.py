from __future__ import annotations

import json

from max.api import spec_traceability_gap_status_to_json


def test_spec_traceability_gap_status_reports_missing_links_and_depth() -> None:
    parsed = json.loads(spec_traceability_gap_status_to_json({"specs": [{"spec_id": "ok", "unit_id": "u", "insight_ids": ["i"], "signal_ids": ["s"]}, {"spec_id": "gap", "unit_id": "", "insight_ids": [], "signal_ids": []}, {"spec_id": "thin", "unit_id": "u", "insight_ids": ["i"], "signal_ids": [], "missing_links": ["signal_ids"]}]}))

    assert [row["spec_id"] for row in parsed["specs"]] == ["gap", "thin", "ok"]
    assert parsed["specs"][0]["missing_links"] == ["insight_ids", "signal_ids", "unit_id"]
    assert parsed["specs"][0]["status"] == "critical"
    assert parsed["summary"]["gap_count"] == 2
    assert parsed["summary"]["critical_gap_count"] == 1
