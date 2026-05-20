from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.llm_budget_exception_digest import (
    KIND,
    SCHEMA_VERSION,
    LLMBudgetEvent,
    build_llm_budget_exception_digest,
    render_llm_budget_exception_digest,
)


def test_llm_budget_exception_digest_groups_events_and_prioritizes_severity() -> None:
    events = [
        LLMBudgetEvent("enterprise", "synthesis", "gpt-5", "near_limit", "near_limit", 1.25, 88.0, "2026-05-19T01:00:00Z"),
        LLMBudgetEvent("enterprise", "synthesis", "gpt-5", "near_limit", "near_limit", 1.50, 93.5, "2026-05-19T02:00:00Z"),
        LLMBudgetEvent("enterprise", "evaluation", "gpt-5-mini", "budget_exceeded", "hard_failure", 0.75, 101.0, "2026-05-20T01:00:00Z"),
        LLMBudgetEvent("growth", "synthesis", "gpt-5", "near_limit", "near_limit", 0.25, 70.0, "2026-05-18T01:00:00Z"),
    ]

    report = build_llm_budget_exception_digest(events, high_event_count=2)
    repeated = build_llm_budget_exception_digest(events, high_event_count=2)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "group_count": 3,
        "event_count": 4,
        "hard_failure_event_count": 1,
        "near_limit_event_count": 3,
        "critical_group_count": 1,
        "high_group_count": 1,
        "watch_group_count": 1,
    }
    assert [row["priority_band"] for row in report["rows"]] == ["critical", "high", "watch"]
    critical = report["rows"][0]
    assert critical["profile"] == "enterprise"
    assert critical["stage"] == "evaluation"
    assert critical["model"] == "gpt-5-mini"
    assert critical["exception_type"] == "budget_exceeded"
    assert critical["severity"] == "hard_failure"
    high = report["rows"][1]
    assert high["event_count"] == 2
    assert high["total_estimated_cost"] == 2.75
    assert high["max_utilization_percent"] == 93.5
    assert high["latest_event_timestamp"] == "2026-05-19T02:00:00Z"


def test_llm_budget_exception_digest_accepts_mapping_records_and_renders() -> None:
    report = build_llm_budget_exception_digest(
        [
            {
                "profile": "enterprise",
                "stage": "ideation",
                "model": "gpt-5",
                "exception_type": "hard_budget_failure",
                "estimated_cost": "2.5",
                "budget_utilization_percent": "110",
                "created_at": "2026-05-20T03:00:00+00:00",
            }
        ]
    )

    assert json.loads(render_llm_budget_exception_digest(report, fmt="json")) == report

    markdown = render_llm_budget_exception_digest(report, fmt="markdown")
    assert markdown.startswith("# LLM Budget Exception Digest")
    assert "| `enterprise` | `ideation` | `gpt-5` | `hard_budget_failure` | hard_failure | 1 | 2.5000 | 110.0 | `2026-05-20T03:00:00Z` | critical |" in markdown

    rendered_csv = render_llm_budget_exception_digest(report, fmt="csv")
    assert rendered_csv.splitlines()[0] == (
        "profile,stage,model,exception_type,severity,event_count,total_estimated_cost,"
        "max_utilization_percent,latest_event_timestamp,priority_band"
    )
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert rows[0]["severity"] == "hard_failure"
    assert rows[0]["priority_band"] == "critical"

    with pytest.raises(ValueError, match="Unsupported LLM budget exception digest format: yaml"):
        render_llm_budget_exception_digest(report, fmt="yaml")


def test_llm_budget_exception_digest_validates_arguments() -> None:
    with pytest.raises(ValueError, match="high_event_count must be at least 1"):
        build_llm_budget_exception_digest([], high_event_count=0)
    with pytest.raises(ValueError, match="critical_utilization_percent must be non-negative"):
        build_llm_budget_exception_digest([], critical_utilization_percent=-1)
