from __future__ import annotations

import json

from max.api import fetch_allocation_drift_status_to_json


def test_fetch_allocation_drift_entries_and_ordering() -> None:
    parsed = json.loads(fetch_allocation_drift_status_to_json({"sources": [
        {"source": "healthy", "target_allocation": 0.3, "actual_allocation": 0.31, "threshold": 0.05},
        {"source": "warn", "target_allocation": 0.3, "actual_allocation": 0.38, "threshold": 0.05},
        {"source": "crit", "target_allocation": 0.3, "actual_allocation": 0.45, "threshold": 0.05},
    ]}))
    assert parsed["summary"]["status"] == "critical"
    assert parsed["entries"][0]["source"] == "crit"
    assert {"source", "targetAllocation", "actualAllocation", "drift", "threshold", "severity"} <= set(parsed["entries"][0])
