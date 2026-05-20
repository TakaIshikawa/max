from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.signal_source_coverage_drift import (
    KIND,
    SCHEMA_VERSION,
    ExpectedSourceCoverage,
    ObservedSignalSourceCount,
    build_signal_source_coverage_drift_report,
    render_signal_source_coverage_drift_report,
)


def test_signal_source_coverage_drift_includes_zero_observed_expected_sources() -> None:
    expected = [
        ExpectedSourceCoverage("enterprise", "github", 0.5, domain="security"),
        ExpectedSourceCoverage("enterprise", "forums", 0.3, domain="security"),
        ExpectedSourceCoverage("enterprise", "rss", 0.2, domain="security"),
    ]
    observed = [
        ObservedSignalSourceCount("enterprise", "github", 9, domain="security"),
        ObservedSignalSourceCount("enterprise", "forums", 1, domain="security"),
    ]

    report = build_signal_source_coverage_drift_report(
        expected,
        observed,
        warning_drift_threshold=0.15,
        critical_drift_threshold=0.30,
    )
    repeated = build_signal_source_coverage_drift_report(
        expected,
        observed,
        warning_drift_threshold=0.15,
        critical_drift_threshold=0.30,
    )

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "coverage_row_count": 3,
        "critical_count": 2,
        "warning_count": 1,
        "healthy_count": 0,
        "zero_observed_expected_count": 1,
    }
    assert [row["source"] for row in report["rows"]] == ["rss", "github", "forums"]
    rss = report["rows"][0]
    assert rss == {
        "profile": "enterprise",
        "domain": "security",
        "source": "rss",
        "expected_share": 0.2,
        "observed_share": 0.0,
        "absolute_drift": 0.2,
        "observed_count": 0,
        "severity_band": "critical",
    }
    github = report["rows"][1]
    assert github["expected_share"] == 0.5
    assert github["observed_share"] == 0.9
    assert github["absolute_drift"] == 0.4
    assert github["severity_band"] == "critical"


def test_signal_source_coverage_drift_accepts_mapping_records_and_renders() -> None:
    report = build_signal_source_coverage_drift_report(
        [{"profile": "growth", "domain": "ai", "source_adapter": "hn", "expected_share": "0.5"}],
        [
            {"profile": "growth", "domain": "ai", "source_adapter": "hn", "signal_count": 2},
            {"profile": "growth", "domain": "ai", "source_adapter": "github", "signal_count": 2},
        ],
    )

    assert json.loads(render_signal_source_coverage_drift_report(report, fmt="json")) == report

    markdown = render_signal_source_coverage_drift_report(report, fmt="markdown")
    assert markdown.startswith("# Signal Source Coverage Drift")
    assert "| `growth` | `ai` | `github` | 0.000 | 0.500 | 0.500 | 2 | critical |" in markdown

    rendered_csv = render_signal_source_coverage_drift_report(report, fmt="csv")
    assert rendered_csv.splitlines()[0] == (
        "profile,domain,source,expected_share,observed_share,absolute_drift,"
        "observed_count,severity_band"
    )
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert [row["source"] for row in rows] == ["github", "hn"]
    assert rows[0]["severity_band"] == "critical"

    with pytest.raises(ValueError, match="Unsupported signal source coverage drift report format: yaml"):
        render_signal_source_coverage_drift_report(report, fmt="yaml")


def test_signal_source_coverage_drift_validates_thresholds() -> None:
    with pytest.raises(ValueError, match="warning_drift_threshold must be non-negative"):
        build_signal_source_coverage_drift_report([], [], warning_drift_threshold=-0.1)
    with pytest.raises(ValueError, match="critical_drift_threshold must be greater than or equal"):
        build_signal_source_coverage_drift_report([], [], warning_drift_threshold=0.2, critical_drift_threshold=0.1)
