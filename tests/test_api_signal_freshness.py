"""Focused tests for signal freshness REST endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_api_signal_freshness.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
    from max.server.dependencies import get_store

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
    idx: int,
    *,
    adapter: str,
    source_type: SignalSourceType = SignalSourceType.FORUM,
    age_days: int,
    tags: list[str] | None = None,
    role: str = "",
) -> Signal:
    timestamp = datetime.now(timezone.utc) - timedelta(days=age_days)
    metadata = {"signal_role": role} if role else {}
    return Signal(
        id=f"sig-api-fresh-{idx:03d}",
        source_type=source_type,
        source_adapter=adapter,
        title=f"Freshness API Signal {idx}",
        content="Signal freshness API fixture",
        url=f"https://example.com/api-freshness/{idx}",
        published_at=timestamp,
        fetched_at=timestamp,
        tags=tags or [],
        metadata=metadata,
    )


def _seed_signals(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            _signal(
                1,
                adapter="hackernews",
                age_days=2,
                tags=["devtools"],
                role="market",
            )
        )
        store.insert_signal(
            _signal(
                2,
                adapter="hackernews",
                age_days=45,
                tags=["devtools", "ai"],
                role="market",
            )
        )
        store.insert_signal(
            _signal(
                3,
                adapter="npm_registry",
                source_type=SignalSourceType.REGISTRY,
                age_days=90,
                tags=["devtools"],
                role="solution",
            )
        )
    finally:
        store.close()


def test_get_signal_freshness_returns_grouped_report(client, db_path) -> None:
    _seed_signals(db_path)

    response = client.get("/api/v1/signals/freshness", params={"max_age_days": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["max_age_days"] == 30
    assert payload["source_adapter_filters"] == []
    assert payload["total_signals"] == 3
    assert payload["stale_signals"] == 2

    by_adapter = {item["key"]: item for item in payload["by_source_adapter"]}
    assert by_adapter["hackernews"]["total_count"] == 2
    assert by_adapter["hackernews"]["stale_count"] == 1
    assert by_adapter["npm_registry"]["stale_count"] == 1

    by_source_type = {item["key"]: item for item in payload["by_source_type"]}
    assert by_source_type["forum"]["total_count"] == 2
    assert by_source_type["registry"]["total_count"] == 1

    by_domain_tag = {item["key"]: item for item in payload["by_domain_tag"]}
    assert by_domain_tag["devtools"]["total_count"] == 3
    assert by_domain_tag["ai"]["total_count"] == 1

    by_signal_role = {item["key"]: item for item in payload["by_signal_role"]}
    assert by_signal_role["market"]["total_count"] == 2
    assert by_signal_role["solution"]["total_count"] == 1

    assert [item["source_adapter"] for item in payload["recommendations"]] == [
        "npm_registry",
        "hackernews",
    ]
    assert payload["recommendations"][0]["stale_count"] == 1
    assert "30 days old" in payload["recommendations"][0]["reason"]


def test_get_signal_freshness_filters_repeated_and_comma_separated_adapters(
    client,
    db_path,
) -> None:
    _seed_signals(db_path)

    repeated = client.get(
        "/api/v1/signals/freshness",
        params=[
            ("max_age_days", "30"),
            ("source_adapter", "hackernews"),
            ("source_adapter", "npm_registry"),
        ],
    )
    comma_separated = client.get(
        "/api/v1/signals/freshness",
        params={
            "max_age_days": "30",
            "source_adapter": "hackernews,npm_registry",
        },
    )

    assert repeated.status_code == 200
    assert comma_separated.status_code == 200
    repeated_payload = repeated.json()
    comma_payload = comma_separated.json()
    assert repeated_payload["generated_at"]
    assert comma_payload["generated_at"]
    repeated_payload.pop("generated_at")
    comma_payload.pop("generated_at")
    assert repeated_payload == comma_payload
    assert repeated_payload["source_adapter_filters"] == ["hackernews", "npm_registry"]


@pytest.mark.parametrize("max_age_days", ["0", "-1"])
def test_get_signal_freshness_rejects_invalid_max_age_days(client, max_age_days) -> None:
    response = client.get(
        "/api/v1/signals/freshness",
        params={"max_age_days": max_age_days},
    )

    assert response.status_code == 422


def test_get_signal_freshness_empty_store_returns_zero_count_report(client) -> None:
    response = client.get("/api/v1/signals/freshness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_signals"] == 0
    assert payload["stale_signals"] == 0
    assert payload["by_source_adapter"] == []
    assert payload["by_source_type"] == []
    assert payload["by_domain_tag"] == []
    assert payload["by_signal_role"] == []
    assert payload["recommendations"] == []
