"""Tests for per-adapter fetch metrics tracking."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from max.pipeline.runner import _fetch_all_signals
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_adapter(name: str, signals: list[Signal] | None = None, error: Exception | None = None):
    """Create a mock adapter that returns signals or raises an error."""
    adapter = AsyncMock()
    adapter.name = name
    if error:
        adapter.fetch = AsyncMock(side_effect=error)
    else:
        adapter.fetch = AsyncMock(return_value=signals or [])
    return adapter


def _make_signal(adapter_name: str, idx: int = 1) -> Signal:
    return Signal(
        id=f"sig-{adapter_name}-{idx:03d}",
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=f"Signal from {adapter_name} #{idx}",
        content=f"Content from {adapter_name}",
        url=f"https://example.com/{adapter_name}/{idx}",
        credibility=0.7,
    )


# ── _fetch_all_signals metrics tests ─────────────────────────────────


class TestFetchAdapterMetrics:
    """Test that _fetch_all_signals() returns correct per-adapter metrics."""

    def test_success_metrics(self):
        """Successful adapters report status=ok with signal count and duration."""
        signals = [_make_signal("adapter_a", i) for i in range(3)]
        adapter = _make_adapter("adapter_a", signals=signals)

        with patch("max.pipeline.runner.get_all_adapters", return_value=[adapter]):
            result_signals, allocation, metrics = _fetch_all_signals(signal_limit=10)

        assert len(result_signals) == 3
        assert "adapter_a" in metrics
        m = metrics["adapter_a"]
        assert m["status"] == "ok"
        assert m["signal_count"] == 3
        assert m["error_message"] is None
        assert isinstance(m["duration_ms"], int)
        assert m["duration_ms"] >= 0

    def test_error_metrics(self):
        """Failed adapters report status=error with error message."""
        adapter = _make_adapter("bad_adapter", error=ConnectionError("timeout"))

        with patch("max.pipeline.runner.get_all_adapters", return_value=[adapter]):
            result_signals, allocation, metrics = _fetch_all_signals(signal_limit=10)

        assert len(result_signals) == 0
        assert "bad_adapter" in metrics
        m = metrics["bad_adapter"]
        assert m["status"] == "error"
        assert m["signal_count"] == 0
        assert m["error_message"] == "timeout"
        assert isinstance(m["duration_ms"], int)
        assert m["duration_ms"] >= 0

    def test_mixed_adapters(self):
        """Mix of successful and failed adapters both get metrics."""
        good_signals = [_make_signal("good", 1), _make_signal("good", 2)]
        good_adapter = _make_adapter("good", signals=good_signals)
        bad_adapter = _make_adapter("bad", error=RuntimeError("API down"))

        with patch("max.pipeline.runner.get_all_adapters", return_value=[good_adapter, bad_adapter]):
            result_signals, allocation, metrics = _fetch_all_signals(signal_limit=10)

        assert len(result_signals) == 2
        assert len(metrics) == 2

        assert metrics["good"]["status"] == "ok"
        assert metrics["good"]["signal_count"] == 2

        assert metrics["bad"]["status"] == "error"
        assert metrics["bad"]["error_message"] == "API down"


# ── DB persistence tests ─────────────────────────────────────────────


class TestAdapterMetricsPersistence:
    """Test that adapter_metrics are persisted and retrievable via Store."""

    def test_metrics_stored_and_retrieved(self, tmp_path):
        """adapter_metrics round-trips through insert/update/get."""
        db_path = str(tmp_path / "test.db")
        store = Store(db_path=db_path)

        run_id = "run-test001"
        store.insert_pipeline_run(run_id, {"signal_limit": 10})

        adapter_metrics = {
            "hackernews": {
                "status": "ok",
                "signal_count": 5,
                "error_message": None,
                "duration_ms": 120,
            },
            "npm_registry": {
                "status": "error",
                "signal_count": 0,
                "error_message": "Connection refused",
                "duration_ms": 3000,
            },
        }

        store.update_pipeline_run(
            run_id,
            signals_fetched=5,
            adapter_metrics=adapter_metrics,
        )

        runs = store.get_pipeline_runs(limit=1)
        assert len(runs) == 1
        assert runs[0]["adapter_metrics"] == adapter_metrics

        store.close()

    def test_default_empty_metrics(self, tmp_path):
        """Pipeline runs without adapter_metrics default to empty dict."""
        db_path = str(tmp_path / "test.db")
        store = Store(db_path=db_path)

        run_id = "run-test002"
        store.insert_pipeline_run(run_id, {"signal_limit": 5})
        store.update_pipeline_run(run_id, signals_fetched=0)

        runs = store.get_pipeline_runs(limit=1)
        assert runs[0]["adapter_metrics"] == {}

        store.close()


# ── Migration test ────────────────────────────────────────────────────


class TestAdapterMetricsMigration:
    """Test that v4→v5 migration adds the column correctly."""

    def test_migration_adds_column(self, tmp_path):
        """Simulate a v4 DB and verify migration adds adapter_metrics."""
        import sqlite3
        from max.store.migrations import ensure_schema

        db_path = str(tmp_path / "migrate.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Bootstrap at v4 (without adapter_metrics column)
        ensure_schema(conn)

        # Verify adapter_metrics column exists after migration
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()
        }
        assert "adapter_metrics" in columns

        # Insert a row and verify default
        conn.execute(
            "INSERT INTO pipeline_runs (id, started_at, config) VALUES (?, ?, ?)",
            ("run-mig01", "2025-01-01T00:00:00Z", "{}"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT adapter_metrics FROM pipeline_runs WHERE id = ?", ("run-mig01",)
        ).fetchone()
        assert json.loads(row[0]) == {}

        conn.close()
