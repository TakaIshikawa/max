from __future__ import annotations

import json

from max.api import spec_trace_completeness_status_to_json


def test_spec_trace_completeness_status_flags_missing_traceability() -> None:
    report = json.loads(spec_trace_completeness_status_to_json({"specs": [{"spec_id": "ok", "unit_id": "u1", "insight_count": 2, "signal_count": 3, "required_signal_count": 2, "missing_trace_count": 0}, {"spec_id": "weak", "unit_id": "u2", "signal_count": 1, "required_signal_count": 3, "missing_trace_count": 2}]}))

    assert [row["spec_id"] for row in report["rows"]] == ["weak", "ok"]
    assert report["incomplete_specs"][0]["spec_id"] == "weak"
    assert report["summary"]["incomplete_count"] == 1
    assert report["summary"]["total_missing_trace_count"] == 2
