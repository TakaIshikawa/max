"""Tests for publishing ideas to Google Sheets through the REST API."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_google_sheets_api.db")
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


def _seed_idea(db_path: str, *, with_evaluation: bool = True) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-sheets001",
                title="Sheets Publish Idea",
                one_liner="Append reviewed ideas to a prioritization sheet",
                category=BuildableCategory.APPLICATION,
                problem="Stakeholders review ideas in spreadsheets.",
                solution="Append Max idea summaries with the Sheets API.",
                value_proposition="Portfolio reviews can happen in the tools stakeholders use.",
                validation_plan="Append one row to a test sheet.",
                domain="devtools",
                status="approved",
                evidence_rationale="Portfolio review needs spreadsheet handoff.",
                evidence_signals=["sig-sheets001"],
                inspiring_insights=["ins-sheets001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-sheets001"))
    finally:
        store.close()


def _evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=82.0,
        recommendation="yes",
    )


def test_publish_google_sheets_dry_run_returns_append_payload_without_token_or_http(
    client,
    db_path,
) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-sheets001/publish/google-sheets",
        json={
            "spreadsheet_id": "spreadsheet-123",
            "range": "Ideas!A:G",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["spreadsheet_id"] == "spreadsheet-123"
    assert data["range"] == "Ideas!A:G"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["updated_range"] is None
    assert data["updated_rows"] is None
    assert data["payload"]["range"] == "Ideas!A:G"
    assert data["payload"]["majorDimension"] == "ROWS"
    row = data["payload"]["values"][0]
    assert row[:6] == [
        "Sheets Publish Idea",
        "# Sheets Publish Idea\n\nAppend reviewed ideas to a prioritization sheet\n\nIdea ID: bu-sheets001\nStatus: approved\nDomain: devtools\nCategory: application\nScore: 82.0\nRecommendation: yes\nEvidence: insights=ins-sheets001; signals=sig-sheets001\nSource ideas: None\nValidation plan: Append one row to a test sheet.",
        "idea",
        "bu-sheets001",
        "bu-sheets001",
        "",
    ]
    assert row[6].endswith("+00:00")
    assert data["publication_attempt"]["target_type"] == "google_sheets_row"
    assert data["publication_attempt"]["status"] == "success"


def test_publish_google_sheets_dry_run_allows_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-sheets001/publish/google-sheets",
        json={
            "spreadsheet_id": "spreadsheet-123",
            "range": "Ideas!A:G",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    row = response.json()["payload"]["values"][0]
    assert row[2] == "idea"
    assert "Recommendation:" in row[1]


def test_publish_google_sheets_live_success_records_publication_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"updates": {"updatedRange": "Ideas!A2:G2", "updatedRows": 1}},
        )

    def publisher_from_env(**kwargs):
        from max.publisher.google_sheets_rows import GoogleSheetsRowPublisher

        return GoogleSheetsRowPublisher(
            kwargs["spreadsheet_id"],
            kwargs["range"],
            access_token=kwargs["access_token"],
            api_url=kwargs["api_url"] or "https://sheets.googleapis.com",
            value_input_option=kwargs["value_input_option"],
            insert_data_option=kwargs["insert_data_option"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GoogleSheetsRowPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-sheets001/publish/google-sheets",
        json={
            "spreadsheet_id": "spreadsheet-123",
            "range": "Ideas!A:G",
            "access_token": "sheets_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["updated_range"] == "Ideas!A2:G2"
    assert data["updated_rows"] == 1
    assert data["publication_attempt"]["target_type"] == "google_sheets_row"
    assert data["publication_attempt"]["target_url"] == "Ideas!A2:G2"
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 200
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer sheets_token"


def test_publish_google_sheets_http_4xx_maps_to_matching_api_status_and_redacts(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text="Authorization: Bearer sheets_token access_token=sheets_token",
        )

    def publisher_from_env(**kwargs):
        from max.publisher.google_sheets_rows import GoogleSheetsRowPublisher

        return GoogleSheetsRowPublisher(
            kwargs["spreadsheet_id"],
            kwargs["range"],
            access_token=kwargs["access_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.GoogleSheetsRowPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/bu-sheets001/publish/google-sheets",
        json={
            "spreadsheet_id": "spreadsheet-123",
            "range": "Ideas!A:G",
            "access_token": "sheets_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "Google Sheets row publish failed with HTTP 403" in detail["message"]
    assert "sheets_token" not in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "google_sheets_row"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403
    assert "sheets_token" not in detail["publication_attempt"]["error"]


def test_publish_google_sheets_missing_spreadsheet_id_or_range_returns_400(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_RANGE", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-sheets001/publish/google-sheets",
        json={"range": "Ideas!A:G", "dry_run": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Google Sheets spreadsheet_id is required; pass spreadsheet_id or set "
        "GOOGLE_SHEETS_SPREADSHEET_ID"
    )

    response = client.post(
        "/api/v1/ideas/bu-sheets001/publish/google-sheets",
        json={"spreadsheet_id": "spreadsheet-123", "dry_run": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Google Sheets range is required; pass range or set GOOGLE_SHEETS_RANGE"
    )


def test_publish_google_sheets_live_requires_auth_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("GOOGLE_SHEETS_ACCESS_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-sheets001/publish/google-sheets",
        json={
            "spreadsheet_id": "spreadsheet-123",
            "range": "Ideas!A:G",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "GOOGLE_SHEETS_ACCESS_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "google_sheets_row"
    assert detail["publication_attempt"]["status"] == "failure"


def test_publish_google_sheets_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Google Sheets publisher")

    monkeypatch.setattr("max.server.api.GoogleSheetsRowPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/ideas/missing/publish/google-sheets",
        json={"spreadsheet_id": "spreadsheet-123", "range": "Ideas!A:G"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"
