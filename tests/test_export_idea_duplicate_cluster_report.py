from __future__ import annotations

from max.exports import generate_idea_duplicate_cluster_report


def test_idea_duplicate_cluster_report_groups_pairs_above_threshold() -> None:
    report = generate_idea_duplicate_cluster_report(
        [
            {"left_id": "idea-b", "right_id": "idea-a", "similarity": 0.95},
            {"left_id": "idea-c", "right_id": "idea-b", "similarity": 0.91},
            {"left_id": "idea-z", "right_id": "idea-y", "similarity": 0.2},
        ],
        threshold=0.9,
    )

    assert report["summary"]["cluster_count"] == 1
    assert report["summary"]["total_duplicate_idea_count"] == 2
    assert report["clusters"][0]["canonical_idea_id"] == "idea-a"
    assert report["clusters"][0]["duplicate_ids"] == ["idea-b", "idea-c"]
    assert report["clusters"][0]["max_similarity"] == 0.95

