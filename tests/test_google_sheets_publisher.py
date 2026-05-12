"""Tests for Google Sheets row publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.google_sheets_rows import (
    GoogleSheetsRowPublishError,
    GoogleSheetsRowPublisher,
)


def _tact_spec(evaluation: dict | None = None) -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-sheets001",
            "status": "approved",
            "domain": "devtools",
            "category": "application",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Sheets Publish Idea",
            "summary": "Append reviewed ideas to a prioritization sheet",
        },
        "problem": {"statement": "Stakeholders review ideas in spreadsheets."},
        "solution": {"approach": "Append Max idea summaries with the Sheets API."},
        "execution": {"validation_plan": "Append one row to a test sheet."},
        "evidence": {
            "rationale": "Portfolio review needs spreadsheet handoff.",
            "insight_ids": ["ins-sheets001"],
            "signal_ids": ["sig-sheets001"],
            "source_idea_ids": [],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": [],
        },
        "evaluation": evaluation,
    }


def test_build_row_payload_maps_tact_spec_fields_deterministically() -> None:
    publisher = GoogleSheetsRowPublisher("spreadsheet-123", "Ideas!A:G")
    payload = publisher.build_row_payload(
        _tact_spec({"recommendation": "yes", "overall_score": 82.0})
    ).to_dict()

    row = payload["values"][0]
    assert payload["range"] == "Ideas!A:G"
    assert payload["majorDimension"] == "ROWS"
    assert row[:6] == [
        "Sheets Publish Idea",
        "# Sheets Publish Idea\n\nAppend reviewed ideas to a prioritization sheet\n\nIdea ID: bu-sheets001\nStatus: approved\nDomain: devtools\nCategory: application\nScore: 82.0\nRecommendation: yes\nEvidence: insights=ins-sheets001; signals=sig-sheets001\nSource ideas: None\nValidation plan: Append one row to a test sheet.",
        "idea",
        "bu-sheets001",
        "bu-sheets001",
        "",
    ]
    assert row[6].endswith("+00:00")


def test_dry_run_returns_exact_append_payload_without_token_or_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GoogleSheetsRowPublisher("spreadsheet-123", "Ideas!A:G", client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.updated_range is None
    assert result.updated_rows is None
    assert result.updated_cells is None
    assert result.endpoint == (
        "https://sheets.googleapis.com/v4/spreadsheets/spreadsheet-123/values/"
        "Ideas%21A%3AG:append"
    )
    assert result.headers["Authorization"] == "Bearer [REDACTED]"
    expected = publisher.build_row_payload(_tact_spec()).to_dict()
    assert result.payload["range"] == expected["range"]
    assert result.payload["majorDimension"] == expected["majorDimension"]
    assert result.payload["values"][0][:6] == expected["values"][0][:6]
    assert result.payload["values"][0][6].endswith("+00:00")


def test_live_publish_posts_authenticated_append_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "spreadsheetId": "spreadsheet-123",
                "updates": {"updatedRange": "Ideas!A2:G2", "updatedRows": 1, "updatedCells": 7},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GoogleSheetsRowPublisher(
        "spreadsheet-123",
        "Ideas!A:G",
        access_token="sheets_token",
        client=client,
    )

    result = publisher.publish(_tact_spec({"recommendation": "maybe"}), dry_run=False)

    assert result.status_code == 200
    assert result.updated_range == "Ideas!A2:G2"
    assert result.updated_rows == 1
    assert result.updated_cells == 7
    assert result.endpoint.endswith("/v4/spreadsheets/spreadsheet-123/values/Ideas%21A%3AG:append")
    assert result.headers["Authorization"] == "Bearer [REDACTED]"
    assert len(requests) == 1
    assert (
        requests[0].url.raw_path
        == b"/v4/spreadsheets/spreadsheet-123/values/Ideas%21A%3AG:append"
        b"?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    )
    assert str(requests[0].url.params) == "valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    assert requests[0].headers["Authorization"] == "Bearer sheets_token"
    posted = _json_from_request(requests[0])
    assert posted == result.payload
    assert posted["values"][0][0] == "Sheets Publish Idea"
    assert "Recommendation: maybe" in posted["values"][0][1]


def test_live_publish_requires_access_token() -> None:
    publisher = GoogleSheetsRowPublisher("spreadsheet-123", "Ideas!A:G")

    with pytest.raises(GoogleSheetsRowPublishError, match="GOOGLE_ACCESS_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_from_env_reads_google_sheets_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "spreadsheet-env")
    monkeypatch.setenv("GOOGLE_SHEETS_RANGE", "Ideas!A:G")
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "token-env")

    publisher = GoogleSheetsRowPublisher.from_env()

    assert publisher.spreadsheet_id == "spreadsheet-env"
    assert publisher.range == "Ideas!A:G"
    assert publisher.access_token == "token-env"


def test_missing_spreadsheet_id_or_range_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_RANGE", raising=False)

    with pytest.raises(GoogleSheetsRowPublishError, match="spreadsheet_id is required"):
        GoogleSheetsRowPublisher.from_env(range="Ideas!A:G")

    with pytest.raises(GoogleSheetsRowPublishError, match="range is required"):
        GoogleSheetsRowPublisher.from_env(spreadsheet_id="spreadsheet-123")


def test_http_error_redacts_bearer_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text='{"error":"Authorization: Bearer sheets_token access_token=sheets_token"}',
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = GoogleSheetsRowPublisher(
        "spreadsheet-123",
        "Ideas!A:G",
        access_token="sheets_token",
        client=client,
    )

    with pytest.raises(GoogleSheetsRowPublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401
    assert "sheets_token" not in str(exc.value)
    assert "Bearer [REDACTED]" in str(exc.value)


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
