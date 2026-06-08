from __future__ import annotations

from datetime import datetime, timezone

from max.exports import generate_spec_evidence_freshness_report as exported
from max.exports.spec_evidence_freshness_report import generate_spec_evidence_freshness_report


def test_spec_evidence_freshness_report_uses_as_of_for_age_and_staleness() -> None:
    report = generate_spec_evidence_freshness_report(
        [
            {"profile": "b2b", "spec_id": "spec-a", "evidence": [{"evidence_id": "old", "created_at": "2026-05-01T00:00:00Z"}, {"evidence_id": "new", "created_at": "2026-06-01T00:00:00Z"}]},
            {"profile": "b2b", "spec_id": "spec-b", "evidence": [{"evidence_id": "fresh", "created_at": "2026-06-07T00:00:00Z"}]},
        ],
        as_of=datetime(2026, 6, 8, tzinfo=timezone.utc),
        stale_after_days=30,
    )

    assert exported is generate_spec_evidence_freshness_report
    assert report["rows"][0] == {"profile": "b2b", "spec_id": "spec-a", "evidence_count": 2, "stale_count": 1, "newest_age_days": 7, "oldest_age_days": 38, "stale_evidence_ids": ["old"], "status": "stale"}
    assert report["rows"][1]["status"] == "fresh"


def test_spec_evidence_freshness_report_empty_input() -> None:
    report = generate_spec_evidence_freshness_report([], as_of=datetime(2026, 6, 8, tzinfo=timezone.utc))
    assert report["rows"] == []
