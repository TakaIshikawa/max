from __future__ import annotations

import json

from max.api.evidence_chain_integrity_status import evidence_chain_integrity_status_to_json


def test_evidence_chain_integrity_status_marks_broken_and_incomplete_units() -> None:
    report = json.loads(
        evidence_chain_integrity_status_to_json(
            {
                "chains": [
                    {"unit_id": "broken", "insight_id": "i", "signal_ids": ["s1"], "missing_signal_ids": ["s2"], "broken_links": [], "required_signal_count": 1},
                    {"unit_id": "incomplete", "insight_id": "i", "signal_ids": ["s1"], "missing_signal_ids": [], "broken_links": [], "required_signal_count": 2},
                ]
            }
        )
    )

    assert [row["status"] for row in report["rows"]] == ["broken", "incomplete"]
    assert report["summary"]["checked_units"] == 2
    assert report["summary"]["broken_units"] == 1
    assert report["summary"]["incomplete_units"] == 1
    assert report["summary"]["missing_signal_total"] == 1
