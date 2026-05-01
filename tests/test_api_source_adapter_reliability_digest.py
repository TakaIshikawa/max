"""REST API tests for source adapter reliability digest."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from max.profiles.schema import DomainContext, PipelineProfile, SourceConfig
from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store


@pytest.fixture
def digest_db(tmp_path) -> str:
    db_path = str(tmp_path / "source-adapter-reliability-digest.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        _seed_runs(store)
    finally:
        store.close()
    return db_path


@pytest.fixture
def empty_digest_db(tmp_path) -> str:
    db_path = str(tmp_path / "source-adapter-reliability-empty.db")
    Store(db_path=db_path, wal_mode=True).close()
    return db_path


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


def test_source_adapter_reliability_digest_json_returns_summary_rows_and_actions(
    digest_db: str,
) -> None:
    response = _client(digest_db).get(
        "/api/v1/source-adapters/reliability-digest",
        params={"limit": 5, "min_runs": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "max.source_adapter.reliability_digest.v1"
    assert payload["kind"] == "max.source_adapter.reliability_digest"
    assert payload["filters"] == {
        "limit": 5,
        "min_runs": 1,
        "profile": None,
        "domain": None,
        "source_adapters": None,
    }
    assert payload["summary"]["run_count"] == 2
    assert payload["summary"]["adapter_count"] == 3
    assert set(payload["reliability_bands"]) == {"failing", "low_yield", "watch", "healthy"}
    rows = {row["adapter"]: row for row in payload["adapters"]}
    assert rows["healthy_adapter"]["success_count"] == 2
    assert rows["broken_adapter"]["reliability_band"] == "failing"
    assert payload["next_actions"]


def test_source_adapter_reliability_digest_filters_adapters_and_profile(
    digest_db: str,
) -> None:
    profile = PipelineProfile(
        name="ops",
        domain=DomainContext(
            name="operations",
            description="Operational diagnostics",
            categories=["application"],
            target_user_types=["operators"],
        ),
        sources=[
            SourceConfig(adapter="healthy_adapter"),
            SourceConfig(adapter="broken_adapter", enabled=False),
        ],
    )

    with patch("max.profiles.loader.load_profile", return_value=profile):
        response = _client(digest_db).get(
            "/api/v1/source-adapters/reliability-digest",
            params={
                "profile": "ops",
                "source_adapter": "healthy_adapter,broken_adapter",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["profile"] == "ops"
    assert payload["filters"]["domain"] == "operations"
    assert payload["filters"]["source_adapters"] == ["healthy_adapter"]
    assert [row["adapter"] for row in payload["adapters"]] == ["healthy_adapter"]


def test_source_adapter_reliability_digest_markdown_download(digest_db: str) -> None:
    response = _client(digest_db).get(
        "/api/v1/source-adapters/reliability-digest",
        params={"format": "markdown"},
    )
    extension_response = _client(digest_db).get(
        "/api/v1/source-adapters/reliability-digest.md"
    )

    for markdown_response in (response, extension_response):
        assert markdown_response.status_code == 200
        assert markdown_response.headers["content-type"].startswith("text/markdown")
        assert (
            markdown_response.headers["content-disposition"]
            == 'attachment; filename="source-adapter-reliability-digest.md"'
        )
        assert markdown_response.text.startswith("# Source Adapter Reliability Digest")
        assert "## Adapter Rankings" in markdown_response.text


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=1001",
        "min_runs=0",
        "min_runs=1001",
        "format=yaml",
        "source_adapter=",
    ],
)
def test_source_adapter_reliability_digest_rejects_invalid_query(
    digest_db: str,
    query: str,
) -> None:
    response = _client(digest_db).get(f"/api/v1/source-adapters/reliability-digest?{query}")

    assert response.status_code == 422


def test_source_adapter_reliability_digest_empty_store_returns_empty_digest(
    empty_digest_db: str,
) -> None:
    response = _client(empty_digest_db).get("/api/v1/source-adapters/reliability-digest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["run_count"] == 0
    assert payload["summary"]["adapter_count"] == 0
    assert payload["adapters"] == []
    assert payload["reliability_bands"] == {
        "failing": [],
        "low_yield": [],
        "watch": [],
        "healthy": [],
    }
    assert payload["next_actions"] == [
        "Run the pipeline with adapter metrics enabled, then synthesize signals to populate utilization stats."
    ]


def _seed_runs(store: Store) -> None:
    for index in range(2):
        run_id = f"run-digest-api-{index}"
        store.insert_pipeline_run(run_id, {"signal_limit": 20})
        store.update_pipeline_run(
            run_id,
            signals_fetched=5,
            adapter_metrics={
                "healthy_adapter": {
                    "status": "ok",
                    "signal_count": 5,
                    "duration_ms": 100,
                },
                "broken_adapter": {
                    "status": "error",
                    "signal_count": 0,
                    "error_message": "HTTP 500",
                    "duration_ms": 500,
                },
                "low_yield_adapter": {
                    "status": "ok",
                    "signal_count": 0,
                    "duration_ms": 75,
                },
            },
        )
