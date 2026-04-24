"""Tests for GitHub Octoverse report adapter."""

from __future__ import annotations

import json

import pytest

from max.sources.github_octoverse import GitHubOctoverseAdapter
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_markdown_headings_are_extracted_as_report_signals(tmp_path):
    report_path = tmp_path / "octoverse-2024.md"
    report_path.write_text(
        "# Octoverse 2024\n\n"
        "Overview text for the report.\n\n"
        "## AI development\n\n"
        "Developers are adopting AI coding tools across more repositories.\n\n"
        "## Open source sustainability\n\n"
        "Maintainer funding and governance remain visible ecosystem themes.\n",
        encoding="utf-8",
    )
    adapter = GitHubOctoverseAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    by_section = {signal.metadata["section"]: signal for signal in signals}
    assert set(by_section) == {"Octoverse 2024", "AI development", "Open source sustainability"}
    ai_signal = by_section["AI development"]
    assert ai_signal.source_type == SignalSourceType.REPORT
    assert ai_signal.source_adapter == "github_octoverse"
    assert ai_signal.title == "AI development"
    assert ai_signal.content == "Developers are adopting AI coding tools across more repositories."
    assert ai_signal.metadata["heading_level"] == 2
    assert ai_signal.metadata["year"] == 2024
    assert ai_signal.metadata["signal_role"] == "market"
    assert ai_signal.credibility == 0.85
    assert {"github", "octoverse", "report", "development"}.issubset(set(ai_signal.tags))


@pytest.mark.asyncio
async def test_json_items_are_ingested_as_distinct_report_signals(tmp_path):
    report_path = tmp_path / "octoverse.json"
    report_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Python growth",
                        "section": "Languages",
                        "summary": "Python remained a top language for AI projects.",
                        "topics": ["python", "ai"],
                        "year": 2025,
                    },
                    {
                        "name": "Security automation",
                        "category": "Security",
                        "description": "Code scanning adoption increased across organizations.",
                        "keywords": ["security", "automation"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = GitHubOctoverseAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Python growth", "Security automation"]
    assert signals[0].metadata["section"] == "Languages"
    assert signals[0].metadata["year"] == 2025
    assert {"python", "ai"}.issubset(set(signals[0].tags))
    assert signals[1].metadata["section"] == "Security"
    assert "code scanning adoption" in signals[1].content.lower()


@pytest.mark.asyncio
async def test_section_and_keyword_filters_are_applied_deterministically(tmp_path):
    report_path = tmp_path / "octoverse.md"
    report_path.write_text(
        "## AI development\n\n"
        "Developers are adopting assistants for code review and tests.\n\n"
        "## Security\n\n"
        "Vulnerability remediation remains important.\n\n"
        "## AI infrastructure\n\n"
        "Model serving work increased, but this does not mention the selected term.\n",
        encoding="utf-8",
    )
    adapter = GitHubOctoverseAdapter(
        config={
            "local_paths": [str(report_path)],
            "sections": ["AI"],
            "keywords": ["assistants"],
        }
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["section"] for signal in signals] == ["AI development"]
    assert signals[0].metadata["matched_keywords"] == ["assistants"]


@pytest.mark.asyncio
async def test_json_items_with_missing_optional_fields_still_parse(tmp_path):
    report_path = tmp_path / "octoverse.json"
    report_path.write_text(
        json.dumps(
            {
                "sections": {
                    "Developer Experience": [
                        {
                            "title": "Faster builds",
                            "content": "Teams continue to invest in build and CI performance.",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    adapter = GitHubOctoverseAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "Faster builds"
    assert signal.url.startswith("file://")
    assert signal.author == "GitHub Octoverse"
    assert signal.published_at is None
    assert signal.metadata["section"] == "Developer Experience"


@pytest.mark.asyncio
async def test_max_items_caps_results(tmp_path):
    report_path = tmp_path / "octoverse.md"
    report_path.write_text(
        "## One\n\nFirst section.\n\n"
        "## Two\n\nSecond section.\n\n",
        encoding="utf-8",
    )
    adapter = GitHubOctoverseAdapter(config={"local_paths": [str(report_path)], "max_items": 1})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "One"
