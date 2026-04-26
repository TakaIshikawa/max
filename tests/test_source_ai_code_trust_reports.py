"""Tests for AI code trust report adapter."""

from __future__ import annotations

import json

import pytest

from max.sources.ai_code_trust_reports import AICodeTrustReportsAdapter
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_markdown_report_extracts_percent_multiplier_and_delta_stats(tmp_path) -> None:
    report_path = tmp_path / "srlabs-ai-code-trust-2026.md"
    report_path.write_text(
        "# SRLabs AI Code Trust Report 2026\n\n"
        "## Trust and verification\n\n"
        "| Metric | Value | Source |\n"
        "| --- | ---: | --- |\n"
        "| Developers not trusting AI code | 96% | SRLabs |\n"
        "| AI code verification gap | 48% don't verify before commit | SRLabs |\n\n"
        "## Review operations\n\n"
        "AI-generated PR review wait is 4.6x longer than human-authored work.\n\n"
        "## Productivity deltas\n\n"
        "AI-heavy projects showed +39% code churn and -19% actual productivity.\n",
        encoding="utf-8",
    )
    adapter = AICodeTrustReportsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=20)

    assert len(signals) == 5
    assert all(signal.source_type == SignalSourceType.REPORT for signal in signals)
    assert all(signal.source_adapter == "ai_code_trust_reports" for signal in signals)

    by_unit_value = {(signal.metadata["unit"], signal.metadata["value"]): signal for signal in signals}
    distrust = by_unit_value[("percent", 96.0)]
    assert distrust.metadata["section"] == "Trust and verification"
    assert distrust.metadata["report_title"] == "SRLabs AI Code Trust Report 2026"
    assert distrust.metadata["population"] == "developers"
    assert distrust.metadata["signal_role"] == "trust"
    assert distrust.metadata["statistic_text"] == "Developers not trusting AI code 96% SRLabs"
    assert distrust.url.startswith("file://")

    review_wait = by_unit_value[("multiplier", 4.6)]
    assert review_wait.metadata["section"] == "Review operations"
    assert "4.6x longer" in review_wait.metadata["statistic_text"]

    assert ("delta_percent", 39.0) in by_unit_value
    assert ("delta_percent", -19.0) in by_unit_value


@pytest.mark.asyncio
async def test_json_snapshot_extracts_equivalent_report_statistics(tmp_path) -> None:
    report_path = tmp_path / "ai-code-trust-snapshot.json"
    report_path.write_text(
        json.dumps(
            {
                "report_title": "AI Code Verification Benchmark Summary",
                "report_date": "2026-03-15",
                "source_url": "https://example.test/reports/ai-code-trust",
                "statistics": [
                    {
                        "section": "Trust",
                        "statistic_label": "Developers not trusting AI code",
                        "value": 96,
                        "unit": "percent",
                        "population": "developers",
                        "statistic_text": "96% of developers do not trust AI code without review.",
                    },
                    {
                        "section": "Security",
                        "statistic_label": "Security findings increase",
                        "value": 10,
                        "unit": "multiplier",
                        "population": "Fortune 50 organizations",
                        "statistic_text": "Security findings increased 10x in six months.",
                    },
                    {
                        "section": "Productivity",
                        "statistic_label": "Actual productivity delta",
                        "value": -19,
                        "unit": "delta_percent",
                        "population": "developers",
                        "statistic_text": "Developers were -19% slower on measured tasks.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    adapter = AICodeTrustReportsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=20)

    by_label = {signal.metadata["statistic_label"]: signal for signal in signals}
    assert set(by_label) == {
        "Developers not trusting AI code",
        "Security findings increase",
        "Actual productivity delta",
    }
    trust = by_label["Developers not trusting AI code"]
    assert trust.url == "https://example.test/reports/ai-code-trust"
    assert trust.metadata["value"] == 96.0
    assert trust.metadata["unit"] == "percent"
    assert trust.metadata["report_title"] == "AI Code Verification Benchmark Summary"
    assert trust.published_at is not None

    security = by_label["Security findings increase"]
    assert security.metadata["unit"] == "multiplier"
    assert security.metadata["value"] == 10.0
    assert security.metadata["signal_role"] == "risk"


@pytest.mark.asyncio
async def test_filters_apply_to_sections_keywords_and_min_percent(tmp_path) -> None:
    report_path = tmp_path / "trust-filter.md"
    report_path.write_text(
        "# AI Trust Metrics\n\n"
        "## Trust\n\n"
        "Developers not trusting AI code reached 96% in the survey.\n"
        "Only 12% mentioned unrelated onboarding friction.\n\n"
        "## Security\n\n"
        "Security findings increased 10x in six months.\n",
        encoding="utf-8",
    )
    adapter = AICodeTrustReportsAdapter(
        config={
            "local_paths": [str(report_path)],
            "sections": ["Trust"],
            "keywords": ["survey"],
            "min_percent": 50,
        }
    )

    signals = await adapter.fetch(limit=20)

    assert len(signals) == 1
    assert signals[0].metadata["value"] == 96.0
    assert signals[0].metadata["matched_keywords"] == ["survey"]
    assert signals[0].metadata["section"] == "Trust"


@pytest.mark.asyncio
async def test_max_items_caps_extracted_statistics(tmp_path) -> None:
    report_path = tmp_path / "trust-max.md"
    report_path.write_text(
        "# AI Trust Metrics\n\n"
        "## Trust\n\n"
        "Developers not trusting AI code reached 96%.\n"
        "AI code verification gap remained 48%.\n",
        encoding="utf-8",
    )
    adapter = AICodeTrustReportsAdapter(
        config={"local_paths": [str(report_path)], "max_items": 1}
    )

    signals = await adapter.fetch(limit=20)

    assert len(signals) == 1
    assert signals[0].metadata["value"] == 96.0
