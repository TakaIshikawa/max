from __future__ import annotations

from max.exports import generate_embedding_cache_hit_rate_report as exported
from max.exports.embedding_cache_hit_rate_report import generate_embedding_cache_hit_rate_report


def test_embedding_cache_hit_rate_report_groups_and_thresholds() -> None:
    report = generate_embedding_cache_hit_rate_report(
        [
            {"namespace": "ideas", "model": "text-embedding-3-small", "hit": True, "lookup_at": "2026-06-01T00:00:00Z"},
            {"namespace": "ideas", "model": "text-embedding-3-small", "hit": False, "lookup_at": "2026-06-02T00:00:00Z"},
            {"namespace": "specs", "model": "text-embedding-3-small", "hit_count": 9, "miss_count": 1, "lookup_at": "2026-06-03T00:00:00Z"},
        ],
        cold_threshold=0.75,
    )

    assert exported is generate_embedding_cache_hit_rate_report
    assert report["rows"][0]["hit_rate"] == 0.5
    assert report["rows"][0]["status"] == "cold"
    assert report["rows"][1]["status"] == "warm"


def test_embedding_cache_hit_rate_report_empty_input() -> None:
    assert generate_embedding_cache_hit_rate_report([])["rows"] == []
