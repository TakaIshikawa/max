from __future__ import annotations

import json

from max.exports import build_profile_idea_throughput_report
from max.exports.profile_idea_throughput_report import render_profile_idea_throughput_report_json, render_profile_idea_throughput_report_markdown


def test_profile_idea_throughput_counts_aliases_and_unspecified_window() -> None:
    rows = build_profile_idea_throughput_report(
        [
            {"profile": "Core", "generated_at": "2026-05-01T00:00:00Z", "status": "approved"},
            {"profile": "Core", "published_at": "2026-05-02T00:00:00Z", "status": "published"},
            {"profile": "Core", "status": "draft"},
        ]
    )

    assert [row["window"] for row in rows] == ["2026-05-01", "2026-05-02", "unspecified"]
    assert rows[0]["approved_count"] == 1
    assert rows[1]["published_count"] == 1
    assert rows[2]["throughput_status"] == "needs_generation"


def test_profile_idea_throughput_renderers() -> None:
    rows = build_profile_idea_throughput_report([{"status": "published"}])

    assert json.loads(render_profile_idea_throughput_report_json(rows))[0]["publish_rate"] == 1.0
    assert "| Profile | Window |" in render_profile_idea_throughput_report_markdown(rows)
