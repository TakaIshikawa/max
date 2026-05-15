"""Tests for HubSpot feedback submissions import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_feedback_submissions_adapter import (
    HubSpotFeedbackSubmissionAdapter,
    HubSpotFeedbackSubmissionsAdapter,
)


def _submission(
    submission_id: str,
    *,
    name: str | None = None,
    content: str | None = None,
    sentiment: str = "POSITIVE",
    archived: bool = False,
) -> dict:
    return {
        "id": submission_id,
        "archived": archived,
        "createdAt": "2026-05-01T10:00:00Z",
        "updatedAt": "2026-05-02T11:00:00Z",
        "properties": {
            "hs_submission_name": name or f"Submission {submission_id}",
            "hs_content": f"Feedback body {submission_id}" if content is None else content,
            "hs_feedback_rating": "5",
            "hs_feedback_sentiment": sentiment,
            "hs_feedback_source": "survey",
            "hs_createdate": "2026-05-01T10:00:00Z",
            "hs_lastmodifieddate": "2026-05-02T11:00:00Z",
            "hubspot_owner_id": "owner-1",
        },
        "associations": {
            "contacts": {
                "results": [{"id": "contact-1", "type": "feedback_submission_to_contact"}],
            }
        },
        "url": f"https://hubspot.example/feedback/{submission_id}",
    }


@pytest.mark.asyncio
async def test_hubspot_feedback_submissions_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "results": [
                        _submission(
                            "feedback-1",
                            name="NPS response",
                            content="Buyer wants stronger reporting.",
                            sentiment="NEGATIVE",
                        )
                    ],
                    "paging": {"next": {"after": "cursor-2"}},
                },
            )
        return httpx.Response(200, json={"results": [_submission("feedback-2", archived=True)]})

    adapter = HubSpotFeedbackSubmissionsAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={
            "page_size": 1,
            "archived": "false",
            "after": "cursor-1",
            "associations": ["contacts", "tickets"],
            "properties": ["hs_submission_name", "hs_content", "hs_feedback_sentiment"],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert HubSpotFeedbackSubmissionAdapter is HubSpotFeedbackSubmissionsAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/crm/v3/objects/feedback_submissions"
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].headers["User-Agent"] == "max-hubspot-feedback-submissions-import/1"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["after"] == "cursor-1"
    assert requests[0].url.params["archived"] == "false"
    assert set(requests[0].url.params.get_list("properties")) == {
        "hs_submission_name",
        "hs_content",
        "hs_feedback_sentiment",
    }
    assert set(requests[0].url.params.get_list("associations")) == {"contacts", "tickets"}
    assert requests[1].url.params["after"] == "cursor-2"

    assert [signal.metadata["feedback_submission_id"] for signal in signals] == ["feedback-1", "feedback-2"]
    signal = signals[0]
    assert signal.id == "hubspot-feedback-submission:feedback-1"
    assert signal.source_adapter == "hubspot_feedback_submissions_import"
    assert signal.source_type.value == "market"
    assert signal.title == "NPS response"
    assert signal.content == "Buyer wants stronger reporting."
    assert signal.url == "https://hubspot.example/feedback/feedback-1"
    assert signal.author == "owner-1"
    assert signal.metadata["signal_role"] == "problem"
    assert signal.metadata["properties"]["hs_feedback_sentiment"] == "NEGATIVE"
    assert signal.metadata["associations"]["contacts"]["results"][0]["id"] == "contact-1"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["raw"]["id"] == "feedback-1"
    assert "hubspot" in signal.tags
    assert "feedback-submission" in signal.tags


@pytest.mark.asyncio
async def test_hubspot_feedback_submissions_respects_limit_and_builds_summary_content() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    _submission("feedback-3", content="", sentiment="neutral"),
                    _submission("feedback-4"),
                ],
                "paging": {"next": {"after": "cursor-2"}},
            },
        )

    adapter = HubSpotFeedbackSubmissionsAdapter(
        access_token="hubspot-token",
        config={"page_size": 50, "properties": "hs_submission_name,hs_feedback_rating,hs_feedback_sentiment"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params.get_list("properties") == [
        "hs_submission_name",
        "hs_feedback_rating",
        "hs_feedback_sentiment",
    ]
    assert [signal.metadata["feedback_submission_id"] for signal in signals] == ["feedback-3"]
    assert signals[0].content == "HubSpot feedback submission; Submission feedback-3; rating 5; neutral; source survey"


@pytest.mark.asyncio
async def test_hubspot_feedback_submissions_empty_without_auth_or_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_PRIVATE_APP_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotFeedbackSubmissionsAdapter().fetch() == []
    assert await HubSpotFeedbackSubmissionsAdapter(token="token").fetch(limit=0) == []

    failing = HubSpotFeedbackSubmissionsAdapter(
        token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
