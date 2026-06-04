from __future__ import annotations

import json

from max.api import spec_evidence_trace_completeness_status_to_json


def test_complete_traces_are_ok() -> None:
    report = json.loads(spec_evidence_trace_completeness_status_to_json({"specs": [{"id": "s1", "unit_id": "u1", "insight_id": "i1", "signal_id": "g1"}]}))
    assert report["summary"]["status"] == "ok"


def test_missing_insight_links_block() -> None:
    report = json.loads(spec_evidence_trace_completeness_status_to_json({"rows": [{"id": "s1", "unit_id": "u1", "signal_id": "g1"}]}))
    assert "missing_insight_reference" in report["spec_rows"][0]["issues"]
    assert report["spec_rows"][0]["status"] == "critical"


def test_missing_signal_links_warn() -> None:
    report = json.loads(spec_evidence_trace_completeness_status_to_json({"items": [{"id": "s1", "unit_id": "u1", "insight_id": "i1"}]}))
    assert report["spec_rows"][0]["status"] == "warning"


def test_duplicate_evidence_ids_are_reported() -> None:
    report = json.loads(spec_evidence_trace_completeness_status_to_json({"items": [{"id": "s1", "unit_id": "u1", "insight_id": "i1", "signal_id": "g1", "evidence_ids": ["e1", "e1"]}]}))
    assert "duplicate_evidence:e1" in report["spec_rows"][0]["issues"]


def test_empty_input_is_insufficient_data() -> None:
    report = json.loads(spec_evidence_trace_completeness_status_to_json({}))
    assert report["summary"]["status"] == "insufficient_data"
