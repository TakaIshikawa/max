from __future__ import annotations

from max.exports import generate_insight_evidence_chain_gap_report as exported
from max.exports.insight_evidence_chain_gap_report import generate_insight_evidence_chain_gap_report


def test_insight_evidence_chain_gap_report_computes_completeness() -> None:
    report = generate_insight_evidence_chain_gap_report(
        [
            {"profile": "b2b", "insight_id": "i-1", "expected_links": ["s1", "s2", "s3"], "present_links": ["s1", "s2"]},
            {"profile": "b2b", "insight_id": "i-2", "expected_links": ["s4"], "present_links": ["s4"]},
        ],
        completeness_threshold=0.8,
    )

    assert exported is generate_insight_evidence_chain_gap_report
    assert report["rows"][0] == {"profile": "b2b", "insight_id": "i-1", "expected_links": 3, "present_links": 2, "missing_links": ["s3"], "completeness_rate": 0.6667, "status": "gapped"}
    assert report["rows"][1]["status"] == "complete"


def test_insight_evidence_chain_gap_report_empty_input() -> None:
    assert generate_insight_evidence_chain_gap_report([])["summary"]["row_count"] == 0
