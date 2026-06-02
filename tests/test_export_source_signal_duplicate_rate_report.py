from __future__ import annotations

from max.exports.source_signal_duplicate_rate_report import generate_source_signal_duplicate_rate_report


def test_duplicate_rate_groups_by_source_with_canonical_url_preferred() -> None:
    report = generate_source_signal_duplicate_rate_report([
        {"source": "github", "id": "1", "canonical_url": "https://example.com/a"},
        {"source": "github", "id": "2", "canonical_url": "https://example.com/a"},
        {"source": "github", "id": "3", "canonical_url": "https://example.com/b"},
        {"source_adapter": "hn", "id": "story-1"},
        {"source_adapter": "hn", "id": "story-1"},
    ])

    assert report["summary"]["duplicate_count"] == 2
    assert report["source_rows"][0] == {"source": "hn", "total_count": 2, "unique_count": 1, "duplicate_count": 1, "duplicate_rate": 0.5}
    assert report["source_rows"][1]["source"] == "github"
