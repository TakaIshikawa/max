from __future__ import annotations

from max.exports.publication_channel_effectiveness_report import build_publication_channel_effectiveness_report, render_publication_channel_effectiveness_report_markdown


def test_publication_channel_effectiveness_report_flags_weak_channels() -> None:
    report = build_publication_channel_effectiveness_report(
        [
            {"destination": "docs", "channel": "api", "profile": "P", "attempted_count": 10, "successful_count": 8, "average_delivery_minutes": 5},
            {"destination": "slack", "channel": "webhook", "profile": "P", "attempted_count": 10, "successful_count": 10, "average_delivery_minutes": 45},
        ]
    )

    assert report["summary"]["attempted_count"] == 20
    assert report["summary"]["successful_count"] == 18
    assert report["summary"]["weak_channel_count"] == 2
    assert report["channel_effectiveness"][0]["success_rate"] == 0.8
    assert {row["channel"] for row in report["weak_channels"]} == {"api", "webhook"}
    assert "- Weak channels: 2" in render_publication_channel_effectiveness_report_markdown(report)
