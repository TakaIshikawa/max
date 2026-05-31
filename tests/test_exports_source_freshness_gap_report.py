from __future__ import annotations

import json

from max.exports.source_freshness_gap_report import generate_source_freshness_gap_report, render_source_freshness_gap_report_json, render_source_freshness_gap_report_markdown


def test_source_freshness_gap_distinguishes_breach_types_and_orders_markdown() -> None:
    report = generate_source_freshness_gap_report(
        [
            {"source": "ok", "profile": "p", "category": "news", "last_successful_fetch_at": "2026-05-31T10:00:00+00:00", "newest_signal_at": "2026-05-31T10:30:00+00:00"},
            {"source": "none", "profile": "p", "category": "news", "newest_signal_at": "2026-05-31T10:00:00+00:00"},
            {"source": "fetch", "profile": "p", "category": "news", "last_successful_fetch_at": "2026-05-29T00:00:00+00:00", "newest_signal_at": "2026-05-31T10:00:00+00:00"},
            {"source": "signal", "profile": "p", "category": "news", "last_successful_fetch_at": "2026-05-31T10:00:00+00:00", "newest_signal_at": "2026-05-29T00:00:00+00:00"},
        ],
        now="2026-05-31T12:00:00+00:00",
        source_freshness_sla_hours=24,
    )

    assert [row["breach_status"] for row in report["rows"]] == ["no-successful-fetch", "stale-fetch", "stale-signal", "ok"]
    markdown = render_source_freshness_gap_report_markdown(report)
    assert markdown.index("none / p / news") < markdown.index("ok / p / news")
    assert "fetch 60.0h" in markdown
    json.loads(render_source_freshness_gap_report_json(report))
