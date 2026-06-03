from __future__ import annotations

import json

from max.exports.profile_source_contract_coverage_report import (
    generate_profile_source_contract_coverage_report,
    render_profile_source_contract_coverage_report_json,
    render_profile_source_contract_coverage_report_markdown,
)


def test_profile_source_contract_coverage_report_classifies_rows_and_summary() -> None:
    report = generate_profile_source_contract_coverage_report(
        [
            {"profile": "Growth", "source": "  Zendesk  ", "contract_tests": 0, "required_contract_tests": 4, "last_verified_at": "2026-05-25T00:00:00+00:00"},
            {"profile": "Growth", "source": "GitHub", "contract_tests": 2, "required_contract_tests": 4, "last_verified_at": "2026-05-25T00:00:00+00:00"},
            {"profile": "Ops", "source": "Slack", "contract_tests": 3, "required_contract_tests": 3, "last_verified_at": "2026-04-01T00:00:00+00:00"},
            {"profile": "Ops", "source": "Airtable", "contract_tests": "bad", "required_contract_tests": -2, "last_verified_at": "2026-05-31T00:00:00+00:00"},
        ]
    )

    assert report["summary"] == {
        "profile_count": 2,
        "source_count": 4,
        "undercovered_source_count": 2,
        "stale_verification_count": 1,
        "row_count": 4,
    }
    assert [row["status"] for row in report["source_rows"]] == ["missing_coverage", "partial_coverage", "stale_verification", "healthy"]
    assert report["source_rows"][0]["source"] == "Zendesk"
    assert report["source_rows"][1]["coverage_ratio"] == 0.5
    assert report["source_rows"][-1]["required_contract_tests"] == 0
    assert report["source_rows"][-1]["coverage_ratio"] == 1.0


def test_profile_source_contract_coverage_report_renderers_are_deterministic() -> None:
    report = generate_profile_source_contract_coverage_report([{"profile": "Growth", "source": "GitHub"}])

    assert json.loads(render_profile_source_contract_coverage_report_json(report))["kind"] == "max.profile_source_contract_coverage_report"
    assert "Growth / GitHub" in render_profile_source_contract_coverage_report_markdown(report)
