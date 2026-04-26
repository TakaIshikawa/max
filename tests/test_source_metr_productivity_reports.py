"""Tests for METR productivity report adapter."""

from __future__ import annotations

import json

import pytest

from max.sources.metr_productivity_reports import MetrProductivityReportsAdapter
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_markdown_report_preserves_metric_values_caveats_and_findings(tmp_path) -> None:
    report_path = tmp_path / "metr-ai-productivity-2025.md"
    report_path.write_text(
        "# METR AI Productivity Report 2025\n\n"
        "## Developer task results\n\n"
        "| Metric | Value | Task class | Participants | Finding | Caveat |\n"
        "| --- | ---: | --- | --- | --- | --- |\n"
        "| Completion time delta | -19% | real-world engineering tasks | "
        "experienced developers | \"AI made participants slower on average\" | "
        "Caveat: tasks were selected from mature open-source repositories. |\n\n"
        "## Workflow observations\n\n"
        "Review throughput was 1.4x faster for small workflow tasks, "
        "with a caveat that confidence intervals were wide.\n",
        encoding="utf-8",
    )
    adapter = MetrProductivityReportsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert all(signal.source_type == SignalSourceType.REPORT for signal in signals)
    assert all(signal.source_adapter == "metr_productivity_reports" for signal in signals)

    by_value = {signal.metadata["value"]: signal for signal in signals}
    completion_time = by_value[-19.0]
    assert completion_time.metadata["metric_name"] == "Completion time delta"
    assert completion_time.metadata["unit"] == "delta_percent"
    assert completion_time.metadata["section"] == "Developer task results"
    assert completion_time.metadata["report_title"] == "METR AI Productivity Report 2025"
    assert completion_time.metadata["task_class"] == "real-world engineering tasks"
    assert completion_time.metadata["participant_segment"] == "experienced developers"
    assert completion_time.metadata["quoted_finding"] == "AI made participants slower on average"
    assert completion_time.metadata["caveats"] == [
        "Completion time delta | -19% | real-world engineering tasks | experienced "
        "developers | \"AI made participants slower on average\" | Caveat: tasks "
        "were selected from mature open-source repositories."
    ]
    assert {"metr", "productivity", "ai-code", "completion-time-delta"}.issubset(
        set(completion_time.tags)
    )
    assert completion_time.url.startswith("file://")

    throughput = by_value[1.4]
    assert throughput.metadata["unit"] == "multiplier"
    assert throughput.metadata["task_class"] == "developer workflow"
    assert throughput.metadata["caveats"]


@pytest.mark.asyncio
async def test_json_report_extracts_stable_ids_and_useful_tags(tmp_path) -> None:
    report_path = tmp_path / "metr-productivity.json"
    report = {
        "report_title": "METR Developer Productivity Evidence",
        "report_date": "2025-07-10",
        "source_url": "https://example.test/metr/productivity",
        "metrics": [
            {
                "section": "Measured task outcomes",
                "metric_name": "Completion time delta",
                "value": -19,
                "unit": "delta_percent",
                "task_class": "real-world engineering tasks",
                "participant_segment": "experienced developers",
                "finding": "AI assistance reduced measured productivity on selected tasks.",
                "caveats": ["Participants forecast speedups before starting."],
                "tags": ["field-study"],
            },
            {
                "section": "Workflow observations",
                "metric_name": "Review throughput",
                "value": 1.4,
                "unit": "multiplier",
                "finding": "Review throughput improved for small tasks.",
            },
        ],
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    adapter = MetrProductivityReportsAdapter(config={"local_paths": [str(report_path)]})

    first = await adapter.fetch(limit=10)
    second = await adapter.fetch(limit=10)

    assert [signal.id for signal in first] == [signal.id for signal in second]
    assert [signal.title for signal in first] == [
        "Completion time delta: -19%",
        "Review throughput: 1.4x",
    ]

    completion_time = first[0]
    assert completion_time.url == "https://example.test/metr/productivity"
    assert completion_time.published_at is not None
    assert completion_time.metadata["value"] == -19.0
    assert completion_time.metadata["unit"] == "delta_percent"
    assert completion_time.metadata["caveats"] == [
        "Participants forecast speedups before starting."
    ]
    assert {"metr", "productivity", "ai-code", "completion-time-delta", "field-study"}.issubset(
        set(completion_time.tags)
    )


@pytest.mark.asyncio
async def test_metric_names_and_keyword_filters_work_together(tmp_path) -> None:
    report_path = tmp_path / "metr-filter.md"
    report_path.write_text(
        "# METR Productivity Evidence\n\n"
        "## Developer task results\n\n"
        "Completion time delta was -19% for experienced developers using assistants.\n"
        "Bug fix success rate was 42% for experienced developers using assistants.\n"
        "Completion time delta was +8% for unrelated onboarding tasks.\n",
        encoding="utf-8",
    )
    adapter = MetrProductivityReportsAdapter(
        config={
            "local_paths": [str(report_path)],
            "sections": ["Developer task"],
            "keywords": ["assistants"],
            "metric_names": ["Completion time"],
        }
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["metric_name"] == "Completion time delta"
    assert signals[0].metadata["value"] == -19.0
    assert signals[0].metadata["matched_keywords"] == ["assistants"]
    assert signals[0].metadata["matched_metric_names"] == ["Completion time"]


@pytest.mark.asyncio
async def test_keyword_filter_applies_to_json_metric_text(tmp_path) -> None:
    report_path = tmp_path / "metr-keywords.json"
    report_path.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "section": "Measured task outcomes",
                        "metric_name": "Completion time delta",
                        "value": -19,
                        "unit": "delta_percent",
                        "finding": "Experienced developers were slower with assistants.",
                    },
                    {
                        "section": "Measured task outcomes",
                        "metric_name": "Planning time delta",
                        "value": 12,
                        "unit": "delta_percent",
                        "finding": "Teams reported unrelated planning gains.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = MetrProductivityReportsAdapter(
        config={"local_paths": [str(report_path)], "keywords": ["assistants"]}
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["metric_name"] == "Completion time delta"
    assert signals[0].metadata["matched_keywords"] == ["assistants"]


@pytest.mark.asyncio
async def test_malformed_json_metric_rows_do_not_abort_fetch(tmp_path) -> None:
    report_path = tmp_path / "metr-malformed.json"
    report_path.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "section": "Measured task outcomes",
                        "metric_name": "Completion time delta",
                        "value": "not measured",
                        "unit": "delta_percent",
                        "finding": "This row has no parseable metric value.",
                    },
                    {
                        "section": "Measured task outcomes",
                        "metric_name": "Valid completion time delta",
                        "value": -19,
                        "unit": "delta_percent",
                        "finding": "Experienced developers were slower with assistants.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    adapter = MetrProductivityReportsAdapter(config={"local_paths": [str(report_path)]})

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["metric_name"] == "Valid completion time delta"
    assert signals[0].metadata["value"] == -19.0
