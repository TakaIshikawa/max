from __future__ import annotations

import json

from max.exports.signal_taxonomy_coverage_report import generate_signal_taxonomy_coverage_report


def test_signal_taxonomy_coverage_reports_role_gaps() -> None:
    report = generate_signal_taxonomy_coverage_report([{"profile": "p1", "source": "crm", "role": "buyer"}], ["buyer", "user"])

    assert report["coverage"][0]["missing_roles"] == ["user"]
    assert report["coverage"][0]["role_coverage"] == 0.5
    assert report["profiles"][0]["role_coverage"] == 0.5
    assert report["summary"]["role_coverage"] == 0.5
    json.dumps(report)


def test_signal_taxonomy_coverage_reports_category_gaps() -> None:
    report = generate_signal_taxonomy_coverage_report(
        [{"profile": "p1", "source": "crm", "role": "buyer", "category": "intent"}],
        ["buyer"],
        required_categories=["intent", "risk"],
    )

    assert report["coverage"][0]["missing_categories"] == ["risk"]
    assert report["coverage"][0]["category_coverage"] == 0.5


def test_signal_taxonomy_coverage_uses_unknown_profile_and_source() -> None:
    report = generate_signal_taxonomy_coverage_report([{"role": "buyer"}], ["buyer"])

    assert report["coverage"][0]["profile"] == "unknown-profile"
    assert report["coverage"][0]["source"] == "unknown-source"


def test_signal_taxonomy_coverage_sorts_rows_and_missing_lists() -> None:
    report = generate_signal_taxonomy_coverage_report(
        [
            {"profile": "Beta", "source": "web", "role": "user", "category": "risk"},
            {"profile": "Alpha", "source": "crm", "role": "buyer", "category": "intent"},
        ],
        ["user", "buyer", "technical"],
        required_categories=["risk", "intent", "adoption"],
    )

    assert [(row["profile"], row["source"]) for row in report["coverage"]] == [("Alpha", "crm"), ("Beta", "web")]
    assert report["coverage"][0]["missing_roles"] == ["technical", "user"]
    assert report["coverage"][0]["missing_categories"] == ["adoption", "risk"]
