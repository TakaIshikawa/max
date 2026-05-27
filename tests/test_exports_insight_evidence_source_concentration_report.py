from __future__ import annotations

from max.exports import generate_insight_evidence_source_concentration_report


def test_insight_evidence_source_concentration_report_flags_dominant_sources() -> None:
    report = generate_insight_evidence_source_concentration_report(
        [
            {"insight_id": "i1", "evidence": [{"source": "crm"}, {"source": "crm"}, {"source": "docs"}]},
            {"insight_id": "i2", "evidence": [{"source": "sales"}, {"source": "sales"}]},
        ],
        threshold=0.7,
    )

    assert report["summary"]["total_insights"] == 2
    assert report["summary"]["flagged_insights"] == 1
    assert report["summary"]["distinct_sources"] == 3
    assert report["findings"][0]["insight_id"] == "i2"
    assert report["findings"][0]["dominant_source_share"] == 1.0

