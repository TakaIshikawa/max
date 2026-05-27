from __future__ import annotations

from max.exports.profile_signal_mix_report import build_profile_signal_mix_report, render_profile_signal_mix_report_markdown


def test_profile_signal_mix_report_derives_mix_and_warnings() -> None:
    report = build_profile_signal_mix_report(
        [
            {"profile": "P", "source": "crm", "role": "buyer", "category": "deal", "freshness_bucket": "fresh", "signal_count": 8},
            {"profile": "P", "source": "support", "role": "user", "category": "ticket", "freshness_bucket": "fresh", "signal_count": 2},
        ]
    )

    total = report["profile_totals"][0]
    assert report["summary"]["profile_count"] == 1
    assert report["summary"]["signal_count"] == 10
    assert total["source_mix"]["crm"] == 0.8
    assert total["dominant_source"] == "crm"
    assert total["concentration_warning"] is True
    assert total["missing_role_warnings"] == ["technical"]
    assert "- Signals: 10" in render_profile_signal_mix_report_markdown(report)
