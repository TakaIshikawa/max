from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from max.analysis.profile_source_lint import (
    build_all_profile_source_lint_report,
    build_profile_source_lint_report,
)
from max.server.app import create_app
from max.sources.registry import AdapterMetadata


def _metadata() -> dict[str, AdapterMetadata]:
    return {
        "rss_feed": AdapterMetadata(
            name="rss_feed",
            config_keys=["feeds", "tags", "max_age_days"],
            required_keys=["feeds"],
            description="RSS feeds",
        ),
        "github": AdapterMetadata(
            name="github",
            config_keys=["topics"],
            required_keys=[],
            description="GitHub topics",
        ),
        "nvd_cve": AdapterMetadata(
            name="nvd_cve",
            config_keys=["keywords", "severities", "cvss_min", "max_age_days"],
            required_keys=[],
            description="NVD CVEs",
        ),
    }


def _write_profile(tmp_path: Path, name: str, sources: str) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(
        f"""
name: {name}
domain:
  name: test
  description: test
  categories: [app]
  target_user_types: [users]
sources:
{sources}
""".lstrip(),
        encoding="utf-8",
    )
    return path


def test_known_good_profile_passes_with_no_errors(tmp_path: Path) -> None:
    path = _write_profile(
        tmp_path,
        "good",
        """
  - adapter: rss_feed
    params:
      feeds:
        - https://example.com/feed.xml
      tags:
        - devtools
      max_age_days: 14
  - adapter: github
    params:
      topics:
        - ai
""",
    )

    with patch("max.analysis.profile_source_lint.get_profile_path", return_value=path), \
         patch("max.analysis.profile_source_lint.get_adapter_metadata", return_value=_metadata()):
        report = build_profile_source_lint_report("good")

    assert report.ok is True
    assert not [issue for issue in report.issues if issue.severity == "error"]


def test_reports_unknown_unsupported_missing_empty_duplicate_and_type_issues(
    tmp_path: Path,
) -> None:
    path = _write_profile(
        tmp_path,
        "bad",
        """
  - adapter: missing_adapter
    params:
      queries:
        - ai
  - adapter: rss_feed
    params:
      tags:
        - news
      unexpected: true
  - adapter: rss_feed
    params:
      feeds: []
  - adapter: nvd_cve
    params:
      keywords: security
      cvss_min: high
      max_age_days: "30"
""",
    )

    with patch("max.analysis.profile_source_lint.get_profile_path", return_value=path), \
         patch("max.analysis.profile_source_lint.get_adapter_metadata", return_value=_metadata()):
        report = build_profile_source_lint_report("bad")

    codes = {issue.code for issue in report.issues}
    assert report.ok is False
    assert {
        "unknown_adapter",
        "unsupported_param",
        "missing_required_param",
        "empty_required_list",
        "duplicate_adapter",
        "param_type_mismatch",
    } <= codes
    assert report.issue_counts_by_severity["error"] >= 5
    assert report.issue_counts_by_adapter["rss_feed"] >= 3
    assert all(issue.profile_path == str(path) for issue in report.issues)
    assert all(issue.suggested_fix for issue in report.issues)
    assert any(issue.path == "sources[1].params.feeds" for issue in report.issues)


def test_disabled_source_with_required_params_reports_info(tmp_path: Path) -> None:
    path = _write_profile(
        tmp_path,
        "disabled",
        """
  - adapter: rss_feed
    enabled: false
    params:
      feeds:
        - https://example.com/feed.xml
""",
    )

    with patch("max.analysis.profile_source_lint.get_profile_path", return_value=path), \
         patch("max.analysis.profile_source_lint.get_adapter_metadata", return_value=_metadata()):
        report = build_profile_source_lint_report("disabled")

    assert report.ok is True
    assert [issue.code for issue in report.issues] == ["disabled_source_with_required_params"]
    assert report.issue_counts_by_severity == {"info": 1}


def test_all_profile_report_aggregates_counts(tmp_path: Path) -> None:
    good = _write_profile(
        tmp_path,
        "good",
        """
  - adapter: github
    params:
      topics:
        - ai
""",
    )
    bad = _write_profile(
        tmp_path,
        "bad",
        """
  - adapter: rss_feed
    params: {}
""",
    )

    with patch("max.analysis.profile_source_lint.list_profile_paths", return_value=[good, bad]), \
         patch("max.analysis.profile_source_lint.get_adapter_metadata", return_value=_metadata()):
        report = build_all_profile_source_lint_report()

    assert report.ok is False
    assert report.profile_count == 2
    assert report.issue_counts_by_severity == {"error": 1}
    assert report.issue_counts_by_adapter == {"rss_feed": 1}


def test_source_lint_api_endpoints_return_structured_reports(tmp_path: Path) -> None:
    path = _write_profile(
        tmp_path,
        "bad",
        """
  - adapter: rss_feed
    params: {}
""",
    )
    app = create_app()
    client = TestClient(app)

    with patch("max.analysis.profile_source_lint.get_profile_path", return_value=path), \
         patch("max.analysis.profile_source_lint.list_profile_paths", return_value=[path]), \
         patch("max.analysis.profile_source_lint.get_adapter_metadata", return_value=_metadata()):
        single = client.get("/api/v1/profiles/bad/source-lint")
        all_profiles = client.get("/api/v1/profiles/source-lint")

    assert single.status_code == 200
    data = single.json()
    assert data["ok"] is False
    assert data["issue_counts_by_severity"] == {"error": 1}
    assert data["issues"][0]["adapter"] == "rss_feed"
    assert data["issues"][0]["suggested_fix"]

    assert all_profiles.status_code == 200
    aggregate = all_profiles.json()
    assert aggregate["profile_count"] == 1
    assert aggregate["issue_counts_by_adapter"] == {"rss_feed": 1}
