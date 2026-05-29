from __future__ import annotations

from max.exports import generate_publisher_auth_expiry_forecast_report, render_publisher_auth_expiry_forecast_report_markdown


def test_publisher_auth_expiry_forecast_sorts_expired_before_near_expiry() -> None:
    report = generate_publisher_auth_expiry_forecast_report(
        [
            {"publisher": "pub", "destination": "web", "profile": "p", "expires_at": "2026-06-05T00:00:00+00:00"},
            {"publisher": "pub", "destination": "api", "profile": "p", "expires_at": "2026-05-01T00:00:00+00:00", "last_success_at": "2026-04-30"},
        ],
        now="2026-05-29T00:00:00+00:00",
    )
    assert [row["destination"] for row in report["rows"]] == ["api", "web"]
    assert report["rows"][0]["severity"] == "critical"
    assert report["rows"][0]["days_until_expiry"] < 0
    assert "pub / api / p" in render_publisher_auth_expiry_forecast_report_markdown(report)
