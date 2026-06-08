from __future__ import annotations

from max.exports import generate_embedding_similarity_threshold_report as exported
from max.exports.embedding_similarity_threshold_report import generate_embedding_similarity_threshold_report


def test_embedding_similarity_threshold_report_groups_samples() -> None:
    report = generate_embedding_similarity_threshold_report(
        [
            {"index_name": "ideas", "profile": "core", "threshold": 0.8, "similarity": 0.82},
            {"index": "ideas", "profile": "core", "score": 0.77},
        ]
    )

    assert exported is generate_embedding_similarity_threshold_report
    assert report["rows"][0]["index_name"] == "ideas"
    assert report["rows"][0]["match_count"] == 1
    assert report["rows"][0]["near_miss_count"] == 1
    assert report["rows"][0]["average_similarity"] == 0.795


def test_embedding_similarity_threshold_report_identifies_loose_and_strict_thresholds() -> None:
    report = generate_embedding_similarity_threshold_report(
        [
            {"index": "loose", "profile": "core", "threshold": 0.8, "similarity": 0.95},
            {"index": "strict", "profile": "core", "threshold": 0.8, "similarity": 0.77},
            {"index": "strict", "profile": "core", "threshold": 0.8, "similarity": 0.76},
        ],
        collision_band=0.1,
    )

    assert [row["index_name"] for row in report["rows"]] == ["loose", "strict"]
    assert report["rows"][0]["status"] == "loose"
    assert report["rows"][1]["status"] == "strict"
