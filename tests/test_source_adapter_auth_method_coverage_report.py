from __future__ import annotations

from max.exports.source_adapter_auth_method_coverage_report import generate_source_adapter_auth_method_coverage_report


def test_method_counts_include_normalized_unknowns() -> None:
    report = generate_source_adapter_auth_method_coverage_report(
        [
            {"adapter": "github", "auth_method": "token"},
            {"adapter": "jira", "auth_method": "oauth"},
            {"adapter": "rss", "auth_method": "none"},
            {"adapter": "blog", "auth_method": ""},
        ]
    )

    assert report["counts_by_method"] == {"token": 1, "oauth": 1, "none": 1, "unknown": 1}


def test_required_auth_violations_are_highlighted() -> None:
    report = generate_source_adapter_auth_method_coverage_report(
        [{"adapter": "github", "auth_method": "token"}, {"adapter": "jira", "auth_method": "none"}],
        required_auth_sources=["github", "jira"],
    )

    assert [row["adapter"] for row in report["missing_required_auth"]] == ["jira"]
    assert report["summary"]["missing_required_auth_count"] == 1


def test_empty_input_returns_empty_sections() -> None:
    report = generate_source_adapter_auth_method_coverage_report([])

    assert report["summary"]["adapter_count"] == 0
    assert report["counts_by_method"] == {"token": 0, "oauth": 0, "none": 0, "unknown": 0}
    assert report["missing_required_auth"] == []
