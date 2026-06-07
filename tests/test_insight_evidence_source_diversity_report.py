from __future__ import annotations

from max.exports import generate_insight_evidence_source_diversity_report


def test_insight_evidence_source_diversity_flags_low_source_counts() -> None:
    report = generate_insight_evidence_source_diversity_report(
        [
            {"insight_id": "i1", "evidence": [{"source": "github"}, {"source": "reddit"}]},
            {"insight_id": "i2", "evidence": [{"source": "hn"}, {"source": "hn"}]},
        ],
        min_distinct_sources=2,
    )

    assert report["rows"][0]["insight_id"] == "i2"
    assert report["rows"][0]["evidence_count"] == 2
    assert report["rows"][0]["distinct_source_count"] == 1
    assert report["rows"][0]["sources"] == ["hn"]
    assert report["rows"][0]["status"] == "needs_more_sources"
    assert report["rows"][1]["status"] == "diverse"


def test_insight_evidence_source_diversity_empty() -> None:
    assert generate_insight_evidence_source_diversity_report([])["rows"] == []
