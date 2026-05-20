from __future__ import annotations

import json

from max.exports.partner_enablement_coverage import (
    KIND,
    SCHEMA_VERSION,
    build_partner_enablement_coverage_report,
    render_partner_enablement_coverage_json,
    render_partner_enablement_coverage_markdown,
)


def test_partner_enablement_coverage_calculates_gaps_and_readiness() -> None:
    report = build_partner_enablement_coverage_report(
        [
            {
                "partner": "Northstar",
                "segment": "SI",
                "tier": "gold",
                "required_materials": ["deck", "demo", "battlecard"],
                "available_materials": ["deck"],
                "certification_status": "in progress",
                "owner": "alliances",
                "blocker": "Sandbox access",
                "evidence": ["lms"],
            },
            {
                "name": "CloudCo",
                "segment": "Cloud",
                "tier": "silver",
                "required_materials": "deck, demo",
                "available_materials": "deck, demo",
                "certification_status": "certified",
                "owner": "partner-ops",
                "readiness_status": "ready",
            },
        ]
    )

    assert report == build_partner_enablement_coverage_report(
        [
            {
                "partner": "Northstar",
                "segment": "SI",
                "tier": "gold",
                "required_materials": ["deck", "demo", "battlecard"],
                "available_materials": ["deck"],
                "certification_status": "in progress",
                "owner": "alliances",
                "blocker": "Sandbox access",
                "evidence": ["lms"],
            },
            {
                "name": "CloudCo",
                "segment": "Cloud",
                "tier": "silver",
                "required_materials": "deck, demo",
                "available_materials": "deck, demo",
                "certification_status": "certified",
                "owner": "partner-ops",
                "readiness_status": "ready",
            },
        ]
    )
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert [row["partner"] for row in report["records"]] == ["Northstar", "CloudCo"]
    assert report["records"][0]["material_coverage_percent"] == 33.3
    assert report["records"][0]["readiness_status"] == "blocked"
    assert report["summary"]["readiness_posture"] == "blocked"
    assert report["material_gaps"][0]["missing_materials"] == ["battlecard", "demo"]
    assert report["certification_gaps"][0]["partner"] == "Northstar"
    assert report["blocker_rows"][0]["blockers"] == ["Sandbox access"]

    markdown = render_partner_enablement_coverage_markdown(report)
    assert "## Partner Segments" in markdown
    assert "## Launch Blockers" in markdown
    assert json.loads(render_partner_enablement_coverage_json(report))["kind"] == KIND


def test_partner_enablement_coverage_empty_input_returns_zero_counts() -> None:
    report = build_partner_enablement_coverage_report([])

    assert report["summary"]["partner_count"] == 0
    assert report["summary"]["average_material_coverage_percent"] == 0.0
    assert report["partner_segments"] == []
    assert report["material_gaps"] == []
    assert "No partner enablement records were supplied." in render_partner_enablement_coverage_markdown(report)
