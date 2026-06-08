from __future__ import annotations

from max.exports import generate_insight_deduplication_collision_report as exported
from max.exports.insight_deduplication_collision_report import generate_insight_deduplication_collision_report


def test_insight_deduplication_collision_report_flags_cluster_conflicts() -> None:
    report = generate_insight_deduplication_collision_report(
        [
            {"cluster_id": "c1", "insight_id": "i1", "theme": "pricing", "role": "buyer", "sources": ["s1"], "confidence": 0.9, "similarity": 0.95},
            {"cluster_id": "c1", "insight_id": "i2", "theme": "onboarding", "role": "buyer", "sources": ["s2"], "confidence": 0.4, "similarity": 0.93},
            {"cluster_id": "c2", "insight_id": "i3", "theme": "pricing", "role": "buyer", "sources": ["s1"], "confidence": 0.9, "similarity": 0.7},
        ]
    )

    assert exported is generate_insight_deduplication_collision_report
    assert report["summary"]["collision_cluster_count"] == 1
    assert report["rows"][0]["cluster_id"] == "c1"
    assert report["rows"][0]["collision_reasons"] == ["conflicting_themes", "conflicting_sources", "conflicting_confidence_bands"]

