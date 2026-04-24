"""Tests for Trello card publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.trello_cards import TrelloCardPublishError, TrelloCardPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-trello001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Trello Publish Idea",
            "summary": "Publish implementation-ready ideas to Trello",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create Trello cards through REST"},
        "execution": {
            "mvp_scope": ["Trello publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test list.",
        },
        "evidence": {
            "rationale": "Teams triage lightweight work in Trello.",
            "insight_ids": ["ins-trello001"],
            "signal_ids": ["sig-trello001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
        },
    }


def test_build_card_payload_maps_tact_spec_fields() -> None:
    publisher = TrelloCardPublisher(
        "list-123",
        labels=["label-delivery"],
        due="2026-05-01T00:00:00.000Z",
    )

    payload = publisher.build_card_payload(_tact_spec()).to_dict()

    assert payload["name"] == "[Max] Trello Publish Idea"
    assert payload["idList"] == "list-123"
    assert "label-delivery" in payload["labels"]
    assert payload["due"] == "2026-05-01T00:00:00.000Z"
    assert "Idea ID: bu-trello001" in payload["desc"]
    assert "Publish one approved idea" in payload["desc"]
    assert payload["metadata"]["idea_id"] == "bu-trello001"
    assert payload["metadata"]["publisher"] == "max.trello_cards"


def test_dry_run_returns_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloCardPublisher(
        "list-123",
        key="trello_key",
        token="trello_token",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.card_id is None
    assert result.card_url is None
    assert result.payload["metadata"]["idea_id"] == "bu-trello001"


def test_live_publish_posts_trello_card_with_auth_params() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "card-123",
                "url": "https://trello.com/c/card123/1-trello-publish-idea",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloCardPublisher(
        "list-123",
        key="trello_key",
        token="trello_token",
        labels=["label-1", "label-2"],
        due="2026-05-01",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.card_id == "card-123"
    assert result.card_url == "https://trello.com/c/card123/1-trello-publish-idea"
    assert requests[0].url == (
        "https://api.trello.com/1/cards?key=trello_key&token=trello_token"
    )
    posted = _json_from_request(requests[0])
    assert posted["name"] == "[Max] Trello Publish Idea"
    assert posted["idList"] == "list-123"
    assert "label-1" in posted["idLabels"]
    assert "label-2" in posted["idLabels"]
    assert posted["due"] == "2026-05-01"
    assert "Max Metadata" in posted["desc"]
    assert result.payload["metadata"]["trello_card_id"] == "card-123"


def test_live_publish_retries_transient_failures() -> None:
    statuses = [503, 429, 200]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status = statuses.pop(0)
        if status == 200:
            return httpx.Response(200, json={"id": "card-123", "shortUrl": "https://trello.com/c/x"})
        return httpx.Response(status, json={"error": "try again"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloCardPublisher(
        "list-123",
        key="trello_key",
        token="trello_token",
        max_retries=2,
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.card_id == "card-123"
    assert len(requests) == 3


def test_live_publish_requires_credentials() -> None:
    publisher = TrelloCardPublisher("list-123")

    with pytest.raises(TrelloCardPublishError, match="TRELLO_KEY and TRELLO_TOKEN are required"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_redacts_secrets_in_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="bad token=trello_secret key=trello_key "
            "https://api.trello.com/1/cards?token=url_secret&key=url_key&safe=yes",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = TrelloCardPublisher(
        "list-123",
        api_url="https://api.trello.com/1?token=api_url_secret",
        key="trello_key",
        token="trello_token",
        client=client,
    )

    with pytest.raises(TrelloCardPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert "trello_secret" not in message
    assert "url_secret" not in message
    assert "url_key" not in message
    assert "api_url_secret" not in message
    assert "token=%3Credacted%3E" in message
    assert "key=%3Credacted%3E" in message


def test_from_env_reads_trello_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRELLO_LIST_ID", "env-list")
    monkeypatch.setenv("TRELLO_KEY", "env-key")
    monkeypatch.setenv("TRELLO_TOKEN", "env-token")

    publisher = TrelloCardPublisher.from_env()

    assert publisher.list_id == "env-list"
    assert publisher.key == "env-key"
    assert publisher.token == "env-token"


def test_from_env_requires_list_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRELLO_LIST_ID", raising=False)

    with pytest.raises(TrelloCardPublishError, match="pass list_id or set TRELLO_LIST_ID"):
        TrelloCardPublisher.from_env()


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
