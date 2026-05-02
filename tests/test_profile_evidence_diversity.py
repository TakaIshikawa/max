"""Tests for profile evidence diversity analysis."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO

import pytest

from max.analysis import build_profile_evidence_diversity_report as exported_build_report
from max.analysis import render_profile_evidence_diversity_csv as exported_render_csv
from max.analysis import render_profile_evidence_diversity_markdown as exported_render_markdown
from max.analysis.profile_evidence_diversity import (
    PROFILE_EVIDENCE_DIVERSITY_CSV_COLUMNS,
    build_profile_evidence_diversity_report,
    render_profile_evidence_diversity_csv,
    render_profile_evidence_diversity_markdown,
    render_profile_evidence_diversity_report,
)
from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.types.signal import Signal, SignalSourceType


def _profile() -> PipelineProfile:
    return PipelineProfile(
        name="diversity",
        domain=DomainContext(
            name="developer-tools",
            description="Developer tools",
            categories=["agent testing", "workflow automation", "security"],
            target_user_types=["developers"],
            workflows=["ci review"],
        ),
        sources=[
            SourceConfig(
                adapter="hackernews",
                watchlist=["agent testing"],
                params={"filter_keywords": ["developer workflow"]},
            ),
            SourceConfig(adapter="reddit", params={"queries": ["workflow automation"]}),
            SourceConfig(adapter="github_issues", params={"topics": ["security"]}),
        ],
    )


def _signal(
    signal_id: str,
    *,
    adapter: str,
    source_type: SignalSourceType = SignalSourceType.FORUM,
    title: str = "Agent testing workflow",
    content: str = "Teams repeat agent testing during CI review.",
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=title,
        content=content,
        url=f"https://example.com/{signal_id}",
        tags=tags or ["agent testing"],
        metadata=metadata or {},
    )


def test_profile_evidence_diversity_reports_concentration_and_repeated_terms() -> None:
    now = datetime(2026, 4, 30, tzinfo=timezone.utc)
    signals = [
        _signal("sig-1", adapter="hackernews"),
        _signal("sig-2", adapter="hackernews", title="Agent testing gaps"),
        _signal("sig-3", adapter="hackernews", title="CI review for agent testing"),
        _signal(
            "sig-4",
            adapter="reddit",
            title="Workflow automation feedback",
            tags=["workflow automation"],
            metadata={"category": "workflow automation"},
        ),
    ]

    report = build_profile_evidence_diversity_report(_profile(), signals, now=now)

    assert report["generated_at"] == "2026-04-30T00:00:00+00:00"
    assert report["summary"] == {
        "total_signals": 4,
        "unique_source_count": 2,
        "unique_category_count": 2,
        "top_source_share": 0.75,
        "top_category_share": 0.75,
        "warning_count": 4,
    }
    assert report["source_diversity"][0] == {
        "source": "hackernews",
        "count": 3,
        "share": 0.75,
    }
    assert report["category_diversity"][0] == {
        "category": "agent testing",
        "count": 3,
        "share": 0.75,
    }
    warnings = {
        (warning["type"], warning["value"])
        for warning in report["concentration_warnings"]
    }
    assert ("source_concentration", "hackernews") in warnings
    assert ("category_concentration", "agent testing") in warnings
    assert ("repeated_term", "agent testing") in warnings
    assert all(
        warning["severity"] in {"high", "medium"}
        for warning in report["concentration_warnings"]
    )
    assert all(warning["recommendation"] for warning in report["concentration_warnings"])
    assert report["underused_sources"] == [
        {
            "source": "github_issues",
            "count": 0,
            "share": 0.0,
            "recommendation": "Retune or allocate more fetch budget to `github_issues`.",
        }
    ]
    assert any("github_issues" in item for item in report["recommended_source_mix_adjustments"])


def test_profile_evidence_diversity_accepts_mapping_rows_and_renders_markdown() -> None:
    report = build_profile_evidence_diversity_report(
        _profile(),
        [
            {
                "source_adapter": "reddit",
                "source_type": "forum",
                "title": "Workflow automation request",
                "content": "Developer workflow automation pain",
                "tags": ["workflow automation"],
                "metadata": {"category": "workflow automation"},
            },
            {
                "source_adapter": "github_issues",
                "source_type": "forum",
                "title": "Security automation issue",
                "content": "Security workflow automation",
                "tags": ["security"],
            },
        ],
        now=datetime(2026, 4, 30, tzinfo=timezone.utc),
    )

    first = render_profile_evidence_diversity_markdown(report)
    second = render_profile_evidence_diversity_markdown(report)

    assert first == second
    assert "# Profile Evidence Diversity: diversity" in first
    assert "## Summary" in first
    assert "## Concentration Warnings" in first
    assert "## Recommended Source Mix Adjustments" in first
    assert "| workflow automation | 2 | `github_issues`, `reddit` |" in first
    assert exported_render_markdown(report) == first


def test_profile_evidence_diversity_empty_input_has_no_evidence_warning() -> None:
    report = exported_build_report(
        _profile(),
        [],
        now=datetime(2026, 4, 30, tzinfo=timezone.utc),
    )

    assert report["summary"]["total_signals"] == 0
    assert report["summary"]["unique_source_count"] == 0
    assert report["concentration_warnings"] == [
        {
            "type": "no_evidence",
            "severity": "high",
            "value": "none",
            "share": 0.0,
            "threshold": 0.0,
            "message": "No recent evidence signals were provided for this profile.",
            "recommendation": (
                "Run enabled sources or import recent signals before generating ideas "
                "from this profile."
            ),
        }
    ]

    markdown = render_profile_evidence_diversity_markdown(report)
    assert "No source evidence is available." in markdown
    assert "No category evidence is available." in markdown
    assert "No recent evidence signals were provided" in markdown
    assert "`hackernews`, `reddit`, `github_issues`" in markdown


def test_profile_evidence_diversity_json_renderer_and_validation() -> None:
    report = build_profile_evidence_diversity_report(
        _profile(),
        [],
        now=datetime(2026, 4, 30, tzinfo=timezone.utc),
    )

    parsed = json.loads(render_profile_evidence_diversity_report(report, fmt="json"))
    assert parsed["schema_version"] == "max.profile.evidence_diversity.v1"

    with pytest.raises(ValueError, match="Unsupported profile evidence diversity report format"):
        render_profile_evidence_diversity_report(report, fmt="yaml")
    with pytest.raises(ValueError, match="source_concentration_threshold"):
        build_profile_evidence_diversity_report(_profile(), [], source_concentration_threshold=0)


def test_profile_evidence_diversity_csv_renderer_has_stable_columns_and_rows() -> None:
    report = build_profile_evidence_diversity_report(
        _profile(),
        [
            _signal("sig-1", adapter="hackernews"),
            _signal("sig-2", adapter="hackernews", title="Agent testing gaps"),
            _signal(
                "sig-3",
                adapter="reddit",
                title="Workflow automation feedback",
                tags=["workflow automation"],
                metadata={"category": "workflow automation"},
            ),
        ],
        now=datetime(2026, 4, 30, tzinfo=timezone.utc),
    )

    csv_text = render_profile_evidence_diversity_csv(report)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == render_profile_evidence_diversity_csv(report)
    assert csv_text.splitlines()[0] == ",".join(PROFILE_EVIDENCE_DIVERSITY_CSV_COLUMNS)
    assert rows[0] == {
        "schema_version": "max.profile.evidence_diversity.v1",
        "kind": "max.profile.evidence_diversity",
        "generated_at": "2026-04-30T00:00:00+00:00",
        "profile": "diversity",
        "domain": "developer-tools",
        "section": "profile",
        "item": "summary",
        "source": "",
        "source_count": "2",
        "source_share": "0.6667",
        "category": "",
        "category_count": "2",
        "category_share": "0.6667",
        "term": "",
        "term_count": "",
        "term_sources": "",
        "warning_type": "",
        "warning_severity": "",
        "warning_value": "",
        "warning_count": "3",
        "warning_share": "",
        "warning_threshold": "",
        "warning_message": "",
        "recommendation": "",
    }
    assert {
        (row["section"], row["source"], row["source_count"], row["source_share"])
        for row in rows
    } >= {
        ("source_mix", "hackernews", "2", "0.6667"),
        ("source_mix", "reddit", "1", "0.3333"),
        ("underused_source", "github_issues", "0", "0.0"),
    }
    assert {
        (row["section"], row["category"], row["category_count"], row["category_share"])
        for row in rows
    } >= {
        ("category_coverage", "agent testing", "2", "0.6667"),
        ("category_coverage", "workflow automation", "1", "0.3333"),
    }
    assert any(
        row["section"] == "repeated_term_coverage"
        and row["term"] == "agent testing"
        and row["term_sources"] == "hackernews, reddit"
        and row["term_count"] == "3"
        for row in rows
    )
    assert any(
        row["section"] == "warning"
        and row["warning_type"] == "source_concentration"
        and row["recommendation"]
        for row in rows
    )
    assert any(
        row["section"] == "recommendation"
        and "underused enabled sources" in row["recommendation"]
        for row in rows
    )
    assert render_profile_evidence_diversity_report(report, fmt="csv") == csv_text
    assert exported_render_csv(report) == csv_text


def test_profile_evidence_diversity_csv_renderer_escapes_special_values() -> None:
    report = build_profile_evidence_diversity_report(
        _profile(),
        [
            {
                "source_adapter": 'forum, "alpha"',
                "source_type": "forum",
                "title": 'Security, automation "request"',
                "content": "Workflow automation\nneeds imports",
                "tags": ["security, automation"],
                "metadata": {"category": 'security, "automation"\ntriage'},
            }
        ],
        now=datetime(2026, 4, 30, tzinfo=timezone.utc),
    )

    csv_text = render_profile_evidence_diversity_csv(report)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"forum, ""alpha"""' in csv_text
    assert '"security, ""automation""\ntriage"' in csv_text
    assert any(
        row["section"] == "source_mix" and row["source"] == 'forum, "alpha"'
        for row in rows
    )
    assert any(
        row["section"] == "category_coverage"
        and row["category"] == 'security, "automation"\ntriage'
        for row in rows
    )


def test_profile_evidence_diversity_empty_csv_renderer_includes_empty_sections() -> None:
    report = build_profile_evidence_diversity_report(
        _profile(),
        [],
        now=datetime(2026, 4, 30, tzinfo=timezone.utc),
    )

    rows = list(csv.DictReader(StringIO(render_profile_evidence_diversity_csv(report))))

    assert [row["section"] for row in rows[:4]] == [
        "profile",
        "source_mix",
        "category_coverage",
        "repeated_term_coverage",
    ]
    assert rows[1]["item"] == "none"
    assert rows[1]["recommendation"] == "No source evidence is available."
    assert rows[2]["item"] == "none"
    assert rows[2]["recommendation"] == "No category evidence is available."
    assert any(row["section"] == "warning" and row["warning_type"] == "no_evidence" for row in rows)
    assert any(
        row["section"] == "recommendation"
        and "`hackernews`, `reddit`, `github_issues`" in row["recommendation"]
        for row in rows
    )
