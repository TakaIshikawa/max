from __future__ import annotations

from max.exports import generate_embedding_dimension_mismatch_report


def test_embedding_dimension_mismatch_report_flags_missing_and_mismatched_vectors() -> None:
    report = generate_embedding_dimension_mismatch_report(
        [
            {"object_id": "ok", "source_type": "idea", "vector": [0.1, 0.2, 0.3]},
            {"object_id": "bad", "source_type": "idea", "vector_dimension": 2},
            {"object_id": "missing", "source_type": "insight"},
        ],
        expected_dimension=3,
    )

    assert report["summary"] == {
        "checked_count": 3,
        "mismatch_count": 1,
        "missing_vector_count": 1,
        "expected_dimension": 3,
    }
    assert [row["object_id"] for row in report["findings"]] == ["bad", "missing"]

