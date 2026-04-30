"""Focused tests for prior-art REST endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_api_prior_art.db")
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


def _seed_prior_art(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-prior-art-api",
            title="Prior Art API",
            one_liner="Expose stored prior art through REST",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Agents cannot fetch persisted novelty checks.",
            solution="Add JSON and Markdown prior-art endpoints.",
            value_proposition="Dashboards can screen duplicate ideas.",
        )
        store.insert_buildable_unit(unit)
        store.insert_prior_art_match(
            unit.id,
            {
                "source": "github",
                "title": "existing-prior-art-api",
                "url": "https://github.com/example/existing-prior-art-api",
                "description": "A stored prior-art match.",
                "relevance_score": 0.88,
                "match_signals": {"stars": 42},
                "search_query": "prior art api",
            },
        )
        store.update_prior_art_status(unit.id, "weak_match")
    finally:
        store.close()


def test_get_idea_prior_art_returns_persisted_report(client, db_path) -> None:
    _seed_prior_art(db_path)

    response = client.get("/api/v1/ideas/bu-prior-art-api/prior-art")

    assert response.status_code == 200
    payload = response.json()
    assert payload["idea_id"] == "bu-prior-art-api"
    assert payload["prior_art_status"] == "weak_match"
    assert payload["matches"][0]["title"] == "existing-prior-art-api"
    assert payload["matches"][0]["match_signals"] == {"stars": 42}


def test_get_idea_prior_art_markdown_download(client, db_path) -> None:
    _seed_prior_art(db_path)

    response = client.get("/api/v1/ideas/bu-prior-art-api/prior-art.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="bu-prior-art-api-prior-art.md"'
    )
    assert "# Prior Art Report: Prior Art API" in response.text
    assert "existing-prior-art-api" in response.text
    assert "Status: `weak_match`" in response.text


def test_missing_idea_prior_art_returns_404_without_analysis(client) -> None:
    with patch("max.analysis.prior_art.check_prior_art") as mock_check:
        response = client.get("/api/v1/ideas/missing-idea/prior-art")

    assert response.status_code == 404
    mock_check.assert_not_called()


def test_missing_idea_prior_art_markdown_returns_404_without_analysis(client) -> None:
    with patch("max.analysis.prior_art.check_prior_art") as mock_check:
        response = client.get("/api/v1/ideas/missing-idea/prior-art.md")

    assert response.status_code == 404
    mock_check.assert_not_called()
