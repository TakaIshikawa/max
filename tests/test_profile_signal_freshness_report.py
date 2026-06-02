from __future__ import annotations

import json

from max.exports.profile_signal_freshness_report import build_profile_signal_freshness_report, render_profile_signal_freshness_report_json, render_profile_signal_freshness_report_markdown


def test_profile_signal_freshness_orders_stale_before_fresh() -> None:
    report = build_profile_signal_freshness_report([
        {"profile": "core", "source": "github", "newest_signal_at": "2026-05-30T00:00:00+00:00", "stale_count": 5},
        {"profile": "core", "source": "hn", "newest_signal_at": "2026-06-01T00:00:00+00:00"},
        {"profile": "growth", "source": "rss"},
    ])

    assert report["summary"]["stale_total"] == 2
    assert report["rows"][0]["recommended_fetch_priority"] == "high"
    markdown = render_profile_signal_freshness_report_markdown(report)
    assert markdown.index("core / github") < markdown.index("core / hn")
    assert json.loads(render_profile_signal_freshness_report_json(report))["summary"]["stale_total"] == 2
