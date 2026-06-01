from __future__ import annotations

import json

from max.api import insight_evidence_chain_gap_status_to_json


def test_insight_evidence_chain_gap_status_healthy() -> None:
    report = json.loads(insight_evidence_chain_gap_status_to_json({"known_signal_ids": ["s1", "s2"], "insights": [{"id": "i1", "evidence": [{"signal_id": "s1"}, {"signal_id": "s2"}]}]}))
    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["no_evidence_count"] == 0


def test_insight_evidence_chain_gap_status_missing_references() -> None:
    report = json.loads(insight_evidence_chain_gap_status_to_json({"known_signal_ids": ["s1"], "insights": [{"id": "i1", "profile": "p1", "evidence": [{"signal_id": "missing"}]}]}))
    assert report["summary"]["missing_signal_reference_count"] == 1
    assert report["per_profile"][0]["profile"] == "p1"


def test_insight_evidence_chain_gap_status_below_minimum_evidence() -> None:
    report = json.loads(insight_evidence_chain_gap_status_to_json({"minimum_evidence_count": 3, "insights": [{"id": "i1", "evidence": [{"signal_id": "s1"}]}]}))
    assert report["summary"]["weak_evidence_count"] == 1
    assert report["summary"]["status"] == "warning"


def test_insight_evidence_chain_gap_status_critical_threshold() -> None:
    report = json.loads(insight_evidence_chain_gap_status_to_json({"critical_missing_reference_rate": 0.5, "known_signal_ids": ["s1"], "insights": [{"id": "i1", "evidence": [{"signal_id": "x"}]}, {"id": "i2", "evidence": [{"signal_id": "s1"}, {"signal_id": "s1"}]}]}))
    assert report["summary"]["status"] == "critical"
    assert report["top_impacted_insights"][0]["insight_id"] == "i1"

