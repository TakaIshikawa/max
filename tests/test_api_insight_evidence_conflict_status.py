from __future__ import annotations

import json

from max.api.insight_evidence_conflict_status import insight_evidence_conflict_status_to_json


def test_insight_evidence_conflict_status_ratios_unresolved_and_summary() -> None:
    report = json.loads(insight_evidence_conflict_status_to_json({"insights": [{"insight_id": "b", "profile": "sales", "conflict_count": 2, "supporting_signal_count": 2, "contradicting_signal_count": 2}, {"insight_id": "a", "conflict_count": 1, "supporting_signal_count": 0, "contradicting_signal_count": 3, "resolved_at": "now"}, {"insight_id": "c", "supporting_signal_count": "bad", "contradicting_signal_count": 0}]}))

    assert report["rows"][0]["insight_id"] == "b"
    assert report["rows"][0]["conflict_ratio"] == 0.5
    assert report["rows"][1]["conflict_ratio"] == 1.0
    assert report["rows"][0]["unresolved"] is True
    assert report["summary"]["total_conflicts"] == 3
    assert report["summary"]["unresolved_count"] == 1
    assert report["summary"]["highest_conflict_ratio"] == 1.0
