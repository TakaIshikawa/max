from __future__ import annotations

from max.exports.insight_novelty_collision_report import generate_insight_novelty_collision_report


def test_insight_novelty_collision_groups_and_filters_by_similarity() -> None:
    report = generate_insight_novelty_collision_report(
        [
            {"cluster_id": "c1", "insight_id": "i1", "similarity": 0.98, "profile": "p", "source_overlap": ["github"]},
            {"cluster_id": "c1", "insight_id": "i2", "similarity": 0.91, "profile": "p", "source_overlap": ["hn"]},
            {"cluster_id": "c2", "insight_id": "i3", "similarity": 0.75},
        ],
        similarity_threshold=0.9,
    )

    assert report["summary"]["collision_group_count"] == 1
    assert report["rows"][0]["group_id"] == "c1"
    assert report["rows"][0]["severity"] == "critical"
    assert report["rows"][0]["source_overlap"] == ["github", "hn"]
