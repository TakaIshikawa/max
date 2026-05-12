"""Tests for Intercom conversation note publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.intercom_conversation_notes import (
    IntercomConversationNotePublishError,
    IntercomConversationNotePublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-intercom001",
            "status": "approved",
            "domain": "support",
            "category": "handoff",
        },
        "project": {
            "title": "Intercom Conversation Note Publisher",
            "summary": "Publish generated TactSpecs into support conversations.",
        },
        "execution": {
            "mvp_scope": ["Payload builder", "Live publisher"],
            "validation_plan": "Publish one note to a sandbox conversation.",
        },
        "evidence": {
            "rationale": "Support teams need handoff context in Intercom.",
            "insight_ids": ["ins-intercom001"],
            "signal_ids": ["sig-intercom001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": ["handoff_risk"],
        },
        "evaluation": {"overall_score": 82.0, "recommendation": "yes"},
    }


def test_dry_run_returns_payload_without_credentials_or_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = IntercomConversationNotePublisher(
        conversation_id="conv_123",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.note_id is None
    assert result.payload["conversation_id"] == "conv_123"
    assert result.payload["message_type"] == "note"
    assert result.payload["type"] == "admin"
    body = result.payload["body"]
    assert "# Intercom Conversation Note Publisher" in body
    assert "- Idea ID: bu-intercom001" in body
    assert "- Rationale: Support teams need handoff context in Intercom." in body
    assert "- Quality score: 8.0" in body
    assert "- Recommendation: yes" in body
    assert result.payload["metadata"]["publisher"] == "max.intercom_conversation_notes"


def test_live_publish_posts_authenticated_intercom_reply() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "conv_123",
                "conversation_part": {"id": "part_456"},
            },
        )

    publisher = IntercomConversationNotePublisher(
        conversation_id="conv_123",
        access_token="intercom_token",
        api_url="https://api.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.conversation_id == "conv_123"
    assert result.note_id == "part_456"
    assert requests[0].url == "https://api.example.test/conversations/conv_123/reply"
    assert requests[0].headers["Authorization"] == "Bearer intercom_token"
    posted = json.loads(requests[0].read())
    assert posted["message_type"] == "note"
    assert posted["type"] == "admin"
    assert "Intercom Conversation Note Publisher" in posted["body"]


def test_from_env_reads_intercom_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERCOM_CONVERSATION_ID", "env_conv")
    monkeypatch.setenv("INTERCOM_ACCESS_TOKEN", "env_token")
    monkeypatch.setenv("INTERCOM_API_URL", "https://intercom.example.test")

    publisher = IntercomConversationNotePublisher.from_env()

    assert publisher.conversation_id == "env_conv"
    assert publisher.access_token == "env_token"
    assert publisher.api_url == "https://intercom.example.test"


def test_live_publish_requires_access_token() -> None:
    publisher = IntercomConversationNotePublisher(conversation_id="conv_123")

    with pytest.raises(IntercomConversationNotePublishError, match="INTERCOM_ACCESS_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_missing_conversation_id_is_actionable() -> None:
    publisher = IntercomConversationNotePublisher(access_token="token")

    with pytest.raises(IntercomConversationNotePublishError, match="INTERCOM_CONVERSATION_ID"):
        publisher.publish(_tact_spec(), dry_run=True)


def test_http_error_redacts_bearer_token() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"message": "bad Bearer secret_token"})
        )
    )
    publisher = IntercomConversationNotePublisher(
        conversation_id="conv_123",
        access_token="secret_token",
        client=client,
    )

    with pytest.raises(IntercomConversationNotePublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401
    assert "secret_token" not in str(exc.value)
    assert "Bearer [REDACTED]" in str(exc.value)
