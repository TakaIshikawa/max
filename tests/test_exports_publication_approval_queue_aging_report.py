from __future__ import annotations

import json

from max.exports.publication_approval_queue_aging_report import (
    build_publication_approval_queue_aging_report,
    render_publication_approval_queue_aging_report_json,
    render_publication_approval_queue_aging_report_markdown,
)


def test_publication_approval_queue_aging_buckets_pending_and_closed_items() -> None:
    report = build_publication_approval_queue_aging_report(
        [
            {"spec_id": "fresh", "destination": "docs", "requested_at": "2026-05-31T18:00:00+00:00", "status": "pending"},
            {"spec_id": "aging", "destination": "slack", "requested_at": "2026-05-30T12:00:00+00:00", "status": "pending"},
            {"spec_id": "stale", "destination": "email", "requested_at": "2026-05-28T00:00:00+00:00", "status": "pending"},
            {"spec_id": "approved", "destination": "docs", "requested_at": "2026-05-20T00:00:00+00:00", "status": "approved"},
            {"spec_id": "rejected", "destination": "docs", "requested_at": "2026-05-20T00:00:00+00:00", "status": "rejected"},
            ["malformed"],
        ],
        generated_at="2026-06-01T00:00:00+00:00",
    )

    assert [row["age_bucket"] for row in report["approval_rows"]] == ["stale", "aging", "fresh", "approved", "rejected"]
    assert report["summary"]["pending_count"] == 3
    assert report["summary"]["stale_count"] == 1
    assert report["summary"]["aging_count"] == 1
    assert report["summary"]["approved_count"] == 1
    assert report["summary"]["rejected_count"] == 1


def test_publication_approval_queue_aging_renderers() -> None:
    report = build_publication_approval_queue_aging_report(
        [{"spec_id": "spec-1", "destination": "docs", "requested_at": "2026-05-31T18:00:00+00:00"}],
        generated_at="2026-06-01T00:00:00+00:00",
    )

    rendered = render_publication_approval_queue_aging_report_json(report)
    assert rendered.endswith("\n")
    assert json.loads(rendered)["summary"]["pending_count"] == 1
    assert "spec-1 -> docs: fresh" in render_publication_approval_queue_aging_report_markdown(report)
