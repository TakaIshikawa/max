from __future__ import annotations

import json

from max.exports import build_source_adapter_coverage_gap_report as exported_builder
from max.exports.source_adapter_coverage_gap_report import (
    KIND,
    SCHEMA_VERSION,
    build_source_adapter_coverage_gap_report,
    render_source_adapter_coverage_gap_report_json,
    render_source_adapter_coverage_gap_report_markdown,
)


def test_source_adapter_coverage_gap_report_normalizes_aliases_and_sections() -> None:
    records = [
        {
            "profile": "growth",
            "source": "forums",
            "adapter": "hackernews",
            "expected_count": "10",
            "observed_count": "10",
            "metadata": {"owner": "imports"},
        },
        {
            "profile": "growth",
            "source": "forums",
            "adapter_name": "reddit",
            "expected_count": "8",
            "observed_count": "0",
        },
        {
            "profile_name": "platform",
            "source_name": "registries",
            "adapter_name": "npm_registry",
            "expected_count": 12,
            "observed_count": 5,
        },
    ]

    report = build_source_adapter_coverage_gap_report(
        records,
        generated_at="2026-05-21T00:00:00+00:00",
        metadata={"environment": "test"},
    )

    assert report == build_source_adapter_coverage_gap_report(
        records,
        generated_at="2026-05-21T00:00:00+00:00",
        metadata={"environment": "test"},
    )
    assert exported_builder(records)["schema_version"] == SCHEMA_VERSION
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["generated_at"] == "2026-05-21T00:00:00+00:00"
    assert report["metadata"] == {"environment": "test"}
    assert report["summary"]["coverage_row_count"] == 3
    assert report["summary"]["expected_count"] == 30
    assert report["summary"]["observed_count"] == 15
    assert report["summary"]["missing_adapter_count"] == 1
    assert report["summary"]["under_sampled_adapter_count"] == 1
    assert [row["adapter"] for row in report["coverage_rows"]] == [
        "reddit",
        "npm_registry",
        "hackernews",
    ]
    assert report["missing_adapters"][0]["adapter"] == "reddit"
    assert report["under_sampled_adapters"][0]["adapter"] == "npm_registry"
    assert report["coverage_rows"][2]["metadata"] == {"owner": "imports"}
    assert report["totals"]["profiles"][0]["profile"] == "growth"
    assert report["totals"]["sources"][0]["source"] == "forums"
    assert report["next_actions"][0]["type"] == "restore_missing_adapter"

    rendered = render_source_adapter_coverage_gap_report_json(report)
    assert json.loads(rendered)["summary"]["gap_count"] == 15
    assert rendered.endswith("\n")
    assert "Missing adapters: 1" in render_source_adapter_coverage_gap_report_markdown(report)


def test_source_adapter_coverage_gap_report_empty_input_is_stable() -> None:
    report = build_source_adapter_coverage_gap_report([])

    assert report["summary"]["coverage_row_count"] == 0
    assert report["summary"]["expected_count"] == 0
    assert report["summary"]["observed_count"] == 0
    assert report["summary"]["coverage_ratio"] == 0.0
    assert report["totals"] == {"profiles": [], "sources": [], "adapters": []}
    assert report["missing_adapters"] == []
    assert report["under_sampled_adapters"] == []
    assert report["next_actions"] == []
    assert "No source adapter coverage gaps detected." in render_source_adapter_coverage_gap_report_markdown(report)

