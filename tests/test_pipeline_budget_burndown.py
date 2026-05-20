"""Tests for pipeline budget burn-down analysis digests."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.pipeline_budget_burndown import (
    KIND,
    SCHEMA_VERSION,
    build_pipeline_budget_burndown,
    render_pipeline_budget_burndown,
)
from max.store.db import Store


def test_build_pipeline_budget_burndown_sorts_and_bands_runs(store: Store) -> None:
    _seed_budget_runs(store)

    report = build_pipeline_budget_burndown(
        store,
        limit=10,
        budget_limit_usd=0.03,
        profile_limits_usd={"growth": 0.03},
        domain_limits_usd={"finops": 0.02},
    )
    repeated = build_pipeline_budget_burndown(
        store,
        limit=10,
        budget_limit_usd=0.03,
        profile_limits_usd={"growth": 0.03},
        domain_limits_usd={"finops": 0.02},
    )

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert [row["id"] for row in report["runs"]] == [
        "run-expensive",
        "run-watch",
        "run-low",
        "run-missing",
    ]
    assert report["budget_bands"] == {
        "over_limit": ["run-expensive"],
        "watch": ["run-watch"],
        "ok": ["run-low"],
        "missing_usage": ["run-missing"],
    }
    assert report["summary"]["run_count"] == 4
    assert report["summary"]["total_estimated_cost_usd"] == pytest.approx(0.085)
    assert report["summary"]["cost_trend"] == "increasing"
    assert report["summary"]["profiles"][0] == {
        "profile": "growth",
        "run_count": 3,
        "estimated_cost_usd": 0.085,
        "over_limit_count": 1,
        "missing_usage_count": 0,
    }
    assert report["summary"]["domains"][0]["domain"] == "finops"
    assert any("Fix token usage capture" in action for action in report["next_actions"])
    assert any("estimated run cost is increasing" in action for action in report["next_actions"])
    assert any("Throttle or split over-limit runs" in action for action in report["next_actions"])


def test_pipeline_budget_burndown_empty_store_returns_guidance(store: Store) -> None:
    report = build_pipeline_budget_burndown(store)

    assert report["runs"] == []
    assert report["summary"]["run_count"] == 0
    assert report["summary"]["profiles"] == []
    assert report["summary"]["domains"] == []
    assert report["next_actions"] == [
        "Run the pipeline with token usage tracking enabled before reviewing budget burn-down."
    ]


def test_render_pipeline_budget_burndown_json_markdown_csv_and_invalid_format(
    store: Store,
) -> None:
    _seed_budget_runs(store)
    report = build_pipeline_budget_burndown(store, limit=10, budget_limit_usd=0.03)

    assert json.loads(render_pipeline_budget_burndown(report, fmt="json")) == report

    markdown = render_pipeline_budget_burndown(report, fmt="markdown")
    assert markdown.startswith("# Pipeline Budget Burndown")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Profile Rollup" in markdown
    assert "| `run-expensive` | 0.050000 | 0.030000 | 1.667 | over_limit |" in markdown
    assert "## Next Actions" in markdown

    rendered_csv = render_pipeline_budget_burndown(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert rendered_csv.splitlines()[0] == (
        "run_id,started_at,status,profile,domain,estimated_cost_usd,total_tokens,"
        "budget_limit_usd,budget_usage_ratio,budget_band,missing_usage"
    )
    assert [row["run_id"] for row in rows] == [
        "run-expensive",
        "run-watch",
        "run-low",
        "run-missing",
    ]
    assert rows[0]["budget_band"] == "over_limit"
    assert rows[3]["missing_usage"] == "True"

    with pytest.raises(ValueError, match="Unsupported pipeline budget burndown format: yaml"):
        render_pipeline_budget_burndown(report, fmt="yaml")


def test_pipeline_budget_burndown_validates_limits(store: Store) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_pipeline_budget_burndown(store, limit=0)
    with pytest.raises(ValueError, match="budget_limit_usd must be greater than 0"):
        build_pipeline_budget_burndown(store, budget_limit_usd=0)
    with pytest.raises(ValueError, match=r"profile_limits_usd\[growth\] must be greater than 0"):
        build_pipeline_budget_burndown(store, profile_limits_usd={"growth": -1})
    with pytest.raises(ValueError, match=r"domain_limits_usd\[finops\] must be greater than 0"):
        build_pipeline_budget_burndown(store, domain_limits_usd={"finops": 0})


def _seed_budget_runs(store: Store) -> None:
    _insert_run(
        store,
        "run-low",
        "2026-05-01T00:00:00",
        {"profile": "growth", "domain": "sales"},
        {"input": 100, "output": 20, "estimated_cost_usd": 0.01},
    )
    _insert_run(
        store,
        "run-watch",
        "2026-05-02T00:00:00",
        {"profile": "growth", "domain": "sales"},
        {"input": 200, "output": 30, "estimated_cost_usd": 0.025},
    )
    _insert_run(
        store,
        "run-expensive",
        "2026-05-03T00:00:00",
        {"profile": "growth", "domain": "finops"},
        {"input": 300, "output": 40, "estimated_cost_usd": 0.05},
    )
    _insert_run(
        store,
        "run-missing",
        "2026-05-04T00:00:00",
        {"profile": "ops", "domain": "support"},
        {},
    )


def _insert_run(
    store: Store,
    run_id: str,
    started_at: str,
    config: dict[str, str],
    token_usage: dict[str, float],
) -> None:
    store.insert_pipeline_run(run_id, config)
    store.update_pipeline_run(run_id, signals_fetched=5, token_usage=token_usage)
    store.conn.execute(
        "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, started_at, run_id),
    )
    store._commit()
