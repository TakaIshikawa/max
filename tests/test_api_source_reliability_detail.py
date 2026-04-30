"""Tests for adapter-specific source reliability REST details."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _client(db_path: str) -> TestClient:
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _signal(
    signal_id: str,
    adapter: str,
    source_type: SignalSourceType,
    *,
    fetched_at: datetime,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"Signal {signal_id}",
        content="Teams report repeated operational pain.",
        url=f"https://example.com/{signal_id}",
        credibility=0.8,
        fetched_at=fetched_at,
    )


def _seed_reliability_data(db_path: str) -> None:
    now = datetime.now(timezone.utc)
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            _signal(
                "sig-hn-recent",
                "hackernews",
                SignalSourceType.FORUM,
                fetched_at=now - timedelta(hours=2),
            )
        )
        store.insert_signal(
            _signal(
                "sig-hn-old",
                "hackernews",
                SignalSourceType.FORUM,
                fetched_at=now - timedelta(days=10),
            )
        )
        store.insert_signal(
            _signal(
                "sig-reddit-recent",
                "reddit",
                SignalSourceType.FORUM,
                fetched_at=now - timedelta(hours=1),
            )
        )
        store.insert_insight(
            Insight(
                id="ins-hn",
                category=InsightCategory.GAP,
                title="Hacker News insight",
                summary="HN evidence points to a repeated pain.",
                evidence=["sig-hn-recent"],
                confidence=0.8,
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-hn",
                title="Reliability Idea",
                one_liner="Improve reliability diagnostics",
                category=BuildableCategory.APPLICATION,
                problem="Operators cannot debug adapter reliability.",
                solution="Show focused adapter reliability details.",
                value_proposition="Faster source debugging.",
                evidence_signals=["sig-hn-recent"],
            )
        )
        store.insert_feedback("bu-hn", "approved")
        store.insert_pipeline_run("run-hn", {})
        store.update_pipeline_run(
            "run-hn",
            adapter_metrics={
                "hackernews": {"status": "ok"},
                "reddit": {"status": "ok"},
            },
        )
    finally:
        store.close()


def test_source_reliability_detail_returns_adapter_metrics_and_freshness(tmp_path) -> None:
    db_path = str(tmp_path / "source-reliability-detail.db")
    _seed_reliability_data(db_path)
    client = _client(db_path)

    with (
        patch("max.server.api.list_adapters", return_value=["hackernews", "reddit"]),
        patch(
            "max.analysis.source_reliability.list_adapters",
            return_value=["hackernews", "reddit"],
        ),
        patch(
            "max.analysis.source_reliability.snapshot_circuit_breakers",
            return_value=[
                SimpleNamespace(adapter_name="hackernews", state="closed"),
                SimpleNamespace(adapter_name="reddit", state="closed"),
            ],
        ),
    ):
        response = client.get(
            "/api/v1/source-reliability/hackernews",
            params={"signal_limit": 10, "time_window": "7d"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter_name"] == "hackernews"
    assert payload["registered"] is True
    assert payload["signal_limit"] == 10
    assert payload["time_window"] == "7d"
    assert payload["fetched_since"]
    assert payload["total_signals"] == 1
    assert payload["recent_signal_count"] == 1
    assert payload["source_types"][0]["source_type"] == "forum"
    assert payload["source_types"][0]["source_adapters"] == ["hackernews"]
    assert payload["metrics"]["adapter_health_score"] == 1.0
    assert payload["metrics"]["signal_usefulness_score"] == 1.0
    assert payload["metrics"]["downstream_idea_conversion_rate"] == 1.0
    assert payload["approval_stats"]["total_feedbacked"] == 1
    assert payload["approval_stats"]["approved"] == 1
    assert payload["freshness"]["signal_count"] == 1
    assert payload["freshness"]["newest_fetched_at"]
    assert payload["freshness"]["oldest_age_days"] < 7
    assert payload["recommendations"]


def test_source_reliability_detail_returns_404_for_unknown_adapter(tmp_path) -> None:
    db_path = str(tmp_path / "source-reliability-missing.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    with patch("max.server.api.list_adapters", return_value=["hackernews"]):
        response = client.get("/api/v1/source-reliability/not_real")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source adapter not found: not_real"


def test_source_reliability_detail_does_not_change_aggregate_response(tmp_path) -> None:
    db_path = str(tmp_path / "source-reliability-aggregate.db")
    _seed_reliability_data(db_path)
    client = _client(db_path)

    with (
        patch("max.server.api.list_adapters", return_value=["hackernews", "reddit"]),
        patch(
            "max.analysis.source_reliability.list_adapters",
            return_value=["hackernews", "reddit"],
        ),
        patch(
            "max.analysis.source_reliability.snapshot_circuit_breakers",
            return_value=[
                SimpleNamespace(adapter_name="hackernews", state="closed"),
                SimpleNamespace(adapter_name="reddit", state="closed"),
            ],
        ),
    ):
        aggregate = client.get("/api/v1/source-reliability", params={"signal_limit": 10})
        detail = client.get("/api/v1/source-reliability/hackernews")

    assert aggregate.status_code == 200
    assert detail.status_code == 200
    assert set(aggregate.json()) == {
        "generated_at",
        "signal_limit",
        "total_signals",
        "source_types",
    }
    assert "adapter_name" not in aggregate.json()
