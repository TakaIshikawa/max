from __future__ import annotations

from max.exports.embedding_cluster_coverage_report import generate_embedding_cluster_coverage_report


def test_handles_records_with_optional_cluster_ids() -> None:
    report = generate_embedding_cluster_coverage_report([{"id": "s1", "cluster_id": "c1"}, {"id": "s2"}])
    assert report["summary"]["item_count"] == 2
    assert report["summary"]["unclustered_item_count"] == 1


def test_singleton_counts_are_deterministic() -> None:
    report = generate_embedding_cluster_coverage_report([{"cluster_id": "b"}, {"cluster_id": "a"}, {"cluster_id": "a"}])
    assert report["summary"]["singleton_cluster_count"] == 1
    assert [row["cluster_id"] for row in report["rows"]] == ["a", "b"]


def test_largest_cluster_concentration_contributes_to_risk() -> None:
    report = generate_embedding_cluster_coverage_report([{"cluster_id": "a"}, {"cluster_id": "a"}, {"cluster_id": "a"}, {"cluster_id": "b"}])
    assert report["summary"]["largest_cluster_share"] == 0.75
    assert report["summary"]["coverage_risk"] == "high"
