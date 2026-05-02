"""API tests for design brief data-room index exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_data_room_index import SCHEMA_VERSION
from max.server.app import create_app
from max.store.db import Store
from tests.test_design_brief_bundle import _seed_design_brief


@pytest.fixture
def data_room_client(tmp_path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "api_design_brief_data_room_index.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        brief_id = _seed_design_brief(store)
    finally:
        store.close()

    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_data_room_index_returns_stable_json_payload(
    data_room_client: tuple[TestClient, str],
) -> None:
    client, brief_id = data_room_client

    response = client.get(f"/api/v1/design-briefs/{brief_id}/data-room-index")

    assert response.status_code == 200
    data = response.json()
    assert list(data.keys()) == [
        "schema_version",
        "kind",
        "source",
        "design_brief",
        "summary",
        "sections",
        "artifacts",
    ]
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.data_room_index"
    assert data["source"]["id"] == brief_id
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Bundle Export Brief"
    assert data["summary"]["available_formats"] == ["json", "markdown", "csv"]
    assert data["summary"]["artifact_count"] == len(data["artifacts"])
    assert {artifact["key"] for artifact in data["artifacts"]} >= {
        "design_brief",
        "bundle",
        "validation_plan",
        "evidence_matrix",
        "risk_register",
        "roadmap",
        "prd",
        "market_sizing",
        "competitive_landscape",
    }
    bundle = next(artifact for artifact in data["artifacts"] if artifact["key"] == "bundle")
    assert bundle["formats"] == ["json", "markdown"]
    assert bundle["urls"]["json"] == f"/api/v1/design-briefs/{brief_id}/bundle"
    assert bundle["urls"]["markdown"] == f"/api/v1/design-briefs/{brief_id}/bundle.md"


def test_get_design_brief_data_room_index_missing_brief_returns_404(
    data_room_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = data_room_client

    response = client.get("/api/v1/design-briefs/dbf-missing/data-room-index")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_data_room_index_does_not_build_unrelated_artifacts(
    data_room_client: tuple[TestClient, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, brief_id = data_room_client

    def fail_unrelated_builder(*args, **kwargs):
        raise AssertionError("unrelated artifact builder should not run")

    monkeypatch.setattr("max.server.api.build_design_brief_bundle", fail_unrelated_builder)
    monkeypatch.setattr("max.server.api.build_design_brief_prd", fail_unrelated_builder)
    monkeypatch.setattr("max.server.api.build_market_sizing_report", fail_unrelated_builder)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/data-room-index")

    assert response.status_code == 200
    assert response.json()["design_brief"]["id"] == brief_id
