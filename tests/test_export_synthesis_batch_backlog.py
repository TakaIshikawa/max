from __future__ import annotations

from max.exports import generate_synthesis_batch_backlog_report


def test_generate_synthesis_batch_backlog_report_empty() -> None:
    report = generate_synthesis_batch_backlog_report({"batches": []}, as_of="2026-05-24T12:00:00Z")

    assert report["summary"]["status"] == "normal"
    assert report["age_buckets"]["unknown"] == 0
    assert report["oldest_queued_batch"] is None


def test_generate_synthesis_batch_backlog_report_mixed_profiles() -> None:
    report = generate_synthesis_batch_backlog_report(
        {
            "batches": [
                {"id": "new", "profile": "a", "status": "queued", "queued_at": "2026-05-24T11:30:00Z"},
                {"id": "old", "profile": "b", "status": "queued", "queued_at": "2026-05-23T00:00:00Z"},
                {"id": "failed", "profile": "c", "status": "failed"},
                {"id": "done", "profile": "a", "status": "completed"},
            ]
        },
        as_of="2026-05-24T12:00:00Z",
    )

    assert report["summary"]["status"] == "stalled"
    assert report["summary"]["failed_batch_total"] == 1
    assert report["age_buckets"]["over_24h"] == 1
    assert report["oldest_queued_batch"]["batch_id"] == "old"
    assert [row["profile"] for row in report["profile_totals"]] == ["b", "c", "a"]

