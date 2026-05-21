from __future__ import annotations

import json

from max.exports.prompt_cache_efficiency_report import (
    KIND,
    build_prompt_cache_efficiency_report,
    render_prompt_cache_efficiency_report_json,
    render_prompt_cache_efficiency_report_markdown,
)


def test_prompt_cache_efficiency_report_groups_stage_and_model_totals() -> None:
    report = build_prompt_cache_efficiency_report(
        [
            {"stage": "rank", "model": "gpt-b", "request_count": 4, "cache_hit_count": 1, "input_tokens": 100, "cached_tokens": 25, "estimated_saved_cost": "0.12555"},
            {"stage": "draft", "model": "gpt-a", "request_count": 10, "cache_hit_count": 9, "input_tokens": 1000, "cached_tokens": 750, "estimated_saved_cost": 1.2},
            {"stage": "classify", "model": "gpt-a", "request_count": 5, "cache_hit_count": 5, "input_tokens": 200, "cached_tokens": 200, "estimated_saved_tokens": 180},
        ],
        low_efficiency_hit_rate_threshold=0.5,
    )

    assert report == build_prompt_cache_efficiency_report(
        [
            {"stage": "rank", "model": "gpt-b", "request_count": 4, "cache_hit_count": 1, "input_tokens": 100, "cached_tokens": 25, "estimated_saved_cost": "0.12555"},
            {"stage": "draft", "model": "gpt-a", "request_count": 10, "cache_hit_count": 9, "input_tokens": 1000, "cached_tokens": 750, "estimated_saved_cost": 1.2},
            {"stage": "classify", "model": "gpt-a", "request_count": 5, "cache_hit_count": 5, "input_tokens": 200, "cached_tokens": 200, "estimated_saved_tokens": 180},
        ],
        low_efficiency_hit_rate_threshold=0.5,
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert [row["stage"] for row in report["stage_efficiency"]] == ["classify", "draft", "rank"]
    assert report["summary"]["request_count"] == 19
    assert report["summary"]["hit_rate"] == 0.7895
    assert report["summary"]["cached_token_share"] == 0.75
    assert report["summary"]["estimated_saved_tokens"] == 955
    assert report["summary"]["estimated_saved_cost"] == 1.3255
    assert [row["stage"] for row in report["low_efficiency_stages"]] == ["rank"]
    assert report["model_totals"][0]["model"] == "gpt-a"
    assert report["model_totals"][0]["hit_rate"] == 0.9333


def test_prompt_cache_efficiency_report_defaults_missing_fields() -> None:
    report = build_prompt_cache_efficiency_report([{}])

    row = report["stage_efficiency"][0]
    assert row["stage"] == "unknown-stage"
    assert row["model"] == "unknown-model"
    assert row["request_count"] == 0
    assert row["cache_hit_count"] == 0
    assert row["hit_rate"] == 0.0
    assert row["cached_token_share"] == 0.0
    assert row["estimated_saved_cost"] == 0.0
    assert report["summary"]["low_efficiency_stage_count"] == 1


def test_prompt_cache_efficiency_report_threshold_can_be_configured() -> None:
    report = build_prompt_cache_efficiency_report(
        [
            {"stage": "draft", "model": "gpt-a", "request_count": 10, "cache_hit_count": 7},
            {"stage": "rank", "model": "gpt-a", "request_count": 10, "cache_hit_count": 4},
        ],
        low_efficiency_hit_rate_threshold=0.6,
    )

    assert report["summary"]["low_efficiency_hit_rate_threshold"] == 0.6
    assert [row["stage"] for row in report["low_efficiency_stages"]] == ["rank"]


def test_prompt_cache_efficiency_report_markdown_and_json_rendering() -> None:
    report = build_prompt_cache_efficiency_report(
        [{"stage": "rank", "model": "gpt-b", "request_count": 4, "cache_hit_count": 1, "input_tokens": 100, "cached_tokens": 25}]
    )

    markdown = render_prompt_cache_efficiency_report_markdown(report)
    assert "- Requests: 4" in markdown
    assert "- Low-efficiency stages: 1" in markdown
    assert "- rank (gpt-b): hit rate 0.25, cached token share 0.25" in markdown

    rendered_json = render_prompt_cache_efficiency_report_json(report)
    assert rendered_json.endswith("\n")
    assert json.loads(rendered_json)["summary"]["cache_hit_count"] == 1
