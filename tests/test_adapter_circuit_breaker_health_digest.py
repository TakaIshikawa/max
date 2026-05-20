"""Tests for adapter circuit breaker health digests."""

from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.adapter_circuit_breaker_health_digest import (
    KIND,
    SCHEMA_VERSION,
    build_adapter_circuit_breaker_health_digest,
    render_adapter_circuit_breaker_health_digest,
)
from max.store.db import Store


def test_adapter_circuit_breaker_health_digest_ranks_open_before_healthy(store: Store) -> None:
    _seed_adapter_runs(store)

    report = build_adapter_circuit_breaker_health_digest(store, limit=10)
    repeated = build_adapter_circuit_breaker_health_digest(store, limit=10)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "run_count": 4,
        "adapter_count": 3,
        "open_count": 1,
        "at_risk_count": 1,
        "healthy_count": 1,
        "latest_run_started_at": "2026-05-04T00:00:00",
    }
    assert report["health_bands"] == {
        "open": ["broken_adapter"],
        "at_risk": ["flaky_adapter"],
        "healthy": ["healthy_adapter"],
    }
    assert [row["adapter"] for row in report["adapters"]] == [
        "broken_adapter",
        "flaky_adapter",
        "healthy_adapter",
    ]
    rows = {row["adapter"]: row for row in report["adapters"]}
    assert rows["broken_adapter"]["consecutive_failure_count"] == 2
    assert rows["broken_adapter"]["failure_rate"] == 0.5
    assert rows["broken_adapter"]["last_error"] == "HTTP 503"
    assert rows["broken_adapter"]["recommended_action"].startswith("Throttle `broken_adapter`")
    assert rows["flaky_adapter"]["health_band"] == "at_risk"
    assert any("Check credentials" in action for action in report["next_actions"])


def test_adapter_circuit_breaker_health_digest_missing_metrics_returns_setup_guidance(
    store: Store,
) -> None:
    store.insert_pipeline_run("run-no-metrics", {"profile": "ops"})

    report = build_adapter_circuit_breaker_health_digest(store)

    assert report["adapters"] == []
    assert report["summary"]["run_count"] == 1
    assert report["health_bands"] == {"open": [], "at_risk": [], "healthy": []}
    assert report["next_actions"] == [
        "Enable adapter_metrics persistence on pipeline runs before reviewing circuit breaker health."
    ]


def test_adapter_circuit_breaker_health_digest_empty_store_returns_guidance(store: Store) -> None:
    report = build_adapter_circuit_breaker_health_digest(store)

    assert report["adapters"] == []
    assert report["summary"]["run_count"] == 0
    assert report["next_actions"] == [
        "Run the pipeline with adapter metrics enabled before reviewing circuit breaker health."
    ]


def test_render_adapter_circuit_breaker_health_digest_json_markdown_csv_and_invalid_format(
    store: Store,
) -> None:
    _seed_adapter_runs(store)
    report = build_adapter_circuit_breaker_health_digest(store, limit=10)

    assert json.loads(render_adapter_circuit_breaker_health_digest(report, fmt="json")) == report

    markdown = render_adapter_circuit_breaker_health_digest(report, fmt="markdown")
    assert markdown.startswith("# Adapter Circuit Breaker Health Digest")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "| `broken_adapter` | open | 4 | 2 | 2 | `error` | HTTP 503 |" in markdown

    rendered_csv = render_adapter_circuit_breaker_health_digest(report, fmt="csv")
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert rendered_csv.splitlines()[0] == (
        "adapter,health_band,run_count,success_count,failure_count,failure_rate,"
        "consecutive_failure_count,latest_status,latest_run_id,latest_run_started_at,"
        "last_error,recommended_action"
    )
    assert [row["adapter"] for row in rows] == [
        "broken_adapter",
        "flaky_adapter",
        "healthy_adapter",
    ]
    assert rows[0]["health_band"] == "open"
    assert rows[0]["last_error"] == "HTTP 503"

    with pytest.raises(ValueError, match="Unsupported adapter circuit breaker health digest format: yaml"):
        render_adapter_circuit_breaker_health_digest(report, fmt="yaml")
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_adapter_circuit_breaker_health_digest(store, limit=0)


def _seed_adapter_runs(store: Store) -> None:
    for index, started_at in enumerate(
        [
            "2026-05-01T00:00:00",
            "2026-05-02T00:00:00",
            "2026-05-03T00:00:00",
            "2026-05-04T00:00:00",
        ],
        start=1,
    ):
        run_id = f"run-adapter-{index}"
        store.insert_pipeline_run(run_id, {"profile": "ops"})
        store.update_pipeline_run(
            run_id,
            adapter_metrics={
                "healthy_adapter": {"status": "ok", "signal_count": 5},
                "broken_adapter": {
                    "status": "error" if index >= 3 else "ok",
                    "signal_count": 0 if index >= 3 else 2,
                    "error_message": "HTTP 503" if index == 4 else "timeout" if index == 3 else "",
                },
                "flaky_adapter": {
                    "status": "error" if index == 2 else "ok",
                    "signal_count": 1,
                    "error_message": "rate limited" if index == 2 else "",
                },
            },
        )
        store.conn.execute(
            "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
            (started_at, started_at, run_id),
        )
        store._commit()
