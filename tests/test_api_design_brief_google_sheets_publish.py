"""Tests for publishing design briefs to Google Sheets through the REST API."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_google_sheets_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
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


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-sheets-brief",
            title="Sheets Brief Source",
            one_liner="Publish design briefs to Sheets",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Portfolio reviews need a spreadsheet row.",
            solution="Create a stable Google Sheets row from the persisted brief.",
            value_proposition="Stakeholders can review design briefs in Sheets.",
            buyer="Product lead",
            specific_user="Portfolio reviewer",
            workflow_context="Portfolio review",
            evidence_rationale="Teams requested Sheets handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Sheets Design Brief",
                domain="devtools",
                theme="portfolio-review",
                lead=Candidate(unit=unit),
                readiness_score=86.0,
                why_this_now="Reviewers already consolidate candidates in Sheets.",
                merged_product_concept="A Google Sheets publisher for design briefs.",
                synthesis_rationale="The source idea is ready for portfolio review.",
                mvp_scope=["Render row payload", "Append to Google Sheets"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then append through a fake transport.",
                risks=["Incorrect Google Sheets credentials"],
                source_idea_ids=["bu-sheets-brief"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_google_sheets_dry_run_returns_deterministic_row(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GOOGLE_SHEETS_ACCESS_TOKEN", raising=False)

    body = {
        "spreadsheet_id": "spreadsheet-123",
        "sheet": "Design Briefs",
        "range": "A:J",
        "dry_run": True,
    }
    first = client.post(f"/api/v1/design-briefs/{brief_id}/publish/google-sheets", json=body)
    second = client.post(f"/api/v1/design-briefs/{brief_id}/publish/google-sheets", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    data = first.json()
    row = data["payload"]["values"][0]
    assert data["design_brief_id"] == brief_id
    assert data["spreadsheet_id"] == "spreadsheet-123"
    assert data["range"] == "Design Briefs!A:J"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["payload"]["range"] == "Design Briefs!A:J"
    assert data["payload"]["majorDimension"] == "ROWS"
    assert row[:9] == [
        brief_id,
        "Sheets Design Brief",
        "devtools",
        "portfolio-review",
        "bu-sheets-brief",
        "bu-sheets-brief",
        86.0,
        1,
        "candidate",
    ]
    assert row[9] == second.json()["payload"]["values"][0][9]
    assert row[9].startswith("# Sheets Design Brief")
    assert "Dry run, then append through a fake transport." in row[9]
    assert data["provider_metadata"]["columns"] == [
        "design_brief_id",
        "title",
        "domain",
        "theme",
        "lead_idea_id",
        "source_idea_ids",
        "readiness_score",
        "evidence_count",
        "status",
        "markdown_summary",
    ]
    assert data["request_summary"]["access_token"] is None
    assert data["publication_attempt"]["target_type"] == "google_sheets_row"
    assert data["publication_attempt"]["idea_id"] == brief_id
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_google_sheets_live_success_with_fake_transport(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"updates": {"updatedRange": "Design Briefs!A2:J2", "updatedRows": 1}},
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
        f"/api/v1/design-briefs/{brief_id}/publish/google-sheets",
        json={
            "spreadsheet_id": "spreadsheet-123",
            "sheet": "Design Briefs",
            "range": "A:J",
            "access_token": "sheets_token",
            "markdown_summary_url": "https://example.com/brief.md",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["updated_range"] == "Design Briefs!A2:J2"
    assert data["updated_rows"] == 1
    assert data["payload"]["values"][0][9] == "https://example.com/brief.md"
    assert data["request_summary"]["access_token"] == "[redacted]"
    assert data["provider_metadata"]["target_url"] == "Design Briefs!A2:J2"
    assert data["publication_attempt"]["target_type"] == "google_sheets_row"
    assert data["publication_attempt"]["target_url"] == "Design Briefs!A2:J2"
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 200
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer sheets_token"
    assert json.loads(requests[0].content)["values"][0][0] == brief_id

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
    finally:
        store.close()
    assert attempts[0]["status"] == "success"
    assert attempts[0]["target_url"] == "Design Briefs!A2:J2"


def test_publish_design_brief_google_sheets_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Google Sheets publisher")

    monkeypatch.setattr("max.server.api.GoogleSheetsRowPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/google-sheets",
        json={"spreadsheet_id": "spreadsheet-123", "range": "Design Briefs!A:J"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_google_sheets_missing_spreadsheet_or_range_returns_400(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_RANGE", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/google-sheets",
        json={"range": "Design Briefs!A:J", "dry_run": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Google Sheets spreadsheet_id is required; pass spreadsheet_id or set "
        "GOOGLE_SHEETS_SPREADSHEET_ID"
    )

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/google-sheets",
        json={"spreadsheet_id": "spreadsheet-123", "dry_run": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Google Sheets range is required; pass range or set GOOGLE_SHEETS_RANGE"
    )


def test_publish_design_brief_google_sheets_live_requires_auth_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("GOOGLE_SHEETS_ACCESS_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/google-sheets",
        json={
            "spreadsheet_id": "spreadsheet-123",
            "range": "Design Briefs!A:J",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "GOOGLE_SHEETS_ACCESS_TOKEN is required" in detail["message"]
    assert detail["request_summary"]["access_token"] is None
    assert detail["publication_attempt"]["target_type"] == "google_sheets_row"
    assert detail["publication_attempt"]["idea_id"] == brief_id
    assert detail["publication_attempt"]["status"] == "failure"


def test_publish_design_brief_google_sheets_provider_error_records_failure_and_redacts(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

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
        f"/api/v1/design-briefs/{brief_id}/publish/google-sheets",
        json={
            "spreadsheet_id": "spreadsheet-123",
            "range": "Design Briefs!A:J",
            "access_token": "sheets_token",
            "dry_run": False,
        },
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "Google Sheets row publish failed with HTTP 403" in detail["message"]
    assert "sheets_token" not in detail["message"]
    assert detail["request_summary"]["access_token"] == "[redacted]"
    assert detail["publication_attempt"]["target_type"] == "google_sheets_row"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403
    assert "sheets_token" not in detail["publication_attempt"]["error"]
