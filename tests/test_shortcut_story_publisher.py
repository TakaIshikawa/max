"""Tests for Shortcut story publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import ShortcutStoryPublishResult, ShortcutStoriesPublisher
from max.publisher.shortcut_stories import ShortcutStoryPublishError, ShortcutStoryPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-shortcut001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Shortcut Publish Idea",
            "summary": "Publish implementation-ready ideas to Shortcut",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create Shortcut stories through REST"},
        "execution": {
            "mvp_scope": ["Shortcut publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test workflow.",
        },
        "evidence": {
            "rationale": "Teams plan execution in Shortcut.",
            "insight_ids": ["ins-shortcut001"],
            "signal_ids": ["sig-shortcut001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": ["needs_scope"],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
        },
    }


def test_build_story_payload_maps_tact_spec_fields() -> None:
    publisher = ShortcutStoryPublisher(
        workflow_state_id=123,
        epic_id=456,
        labels=["handoff"],
        owner_ids=["user-1", "user-2"],
        story_type="chore",
        estimate=3,
        deadline="2026-05-15",
        iteration_id=789,
    )

    payload = publisher.build_story_payload(_tact_spec()).to_dict()

    assert payload["name"] == "[Max] Shortcut Publish Idea"
    assert payload["story_type"] == "chore"
    assert payload["workflow_state_id"] == 123
    assert payload["epic_id"] == 456
    assert payload["owner_ids"] == ["user-1", "user-2"]
    assert payload["estimate"] == 3
    assert payload["deadline"] == "2026-05-15"
    assert payload["iteration_id"] == 789
    assert "handoff" in payload["labels"]
    assert "quality-needs-scope" in payload["labels"]
    assert "Idea ID: bu-shortcut001" in payload["description"]
    assert "Publish one approved idea" in payload["description"]
    assert payload["metadata"]["publisher"] == "max.shortcut_stories"
    assert payload["metadata"]["idea_id"] == "bu-shortcut001"


def test_dry_run_returns_payload_without_token_or_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ShortcutStoryPublisher(workflow_state_id=123, labels=["handoff"], client=client)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.story_id is None
    assert result.story_url is None
    assert result.payload["name"] == "[Max] Shortcut Publish Idea"
    assert result.payload["workflow_state_id"] == 123
    assert result.payload["labels"][-1] == "handoff"


def test_live_publish_posts_shortcut_story_request_shape() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": 42,
                "app_url": "https://app.shortcut.com/acme/story/42/shortcut-publish-idea",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ShortcutStoryPublisher(
        api_token="shortcut_secret",
        workflow_state_id=123,
        epic_id=456,
        labels=["handoff"],
        owner_ids=["user-1"],
        story_type="feature",
        estimate="5",
        deadline="2026-05-15",
        iteration_id="789",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.story_id == 42
    assert result.story_url == "https://app.shortcut.com/acme/story/42/shortcut-publish-idea"
    assert result.payload["metadata"]["shortcut_story_id"] == 42
    assert requests[0].url == "https://api.app.shortcut.com/api/v3/stories"
    assert requests[0].headers["Shortcut-Token"] == "shortcut_secret"
    posted = _json_from_request(requests[0])
    assert posted["name"] == "[Max] Shortcut Publish Idea"
    assert posted["story_type"] == "feature"
    assert posted["workflow_state_id"] == 123
    assert posted["epic_id"] == 456
    assert posted["owner_ids"] == ["user-1"]
    assert posted["estimate"] == 5
    assert posted["deadline"] == "2026-05-15"
    assert posted["iteration_id"] == 789
    assert {"name": "handoff"} in posted["labels"]
    assert "metadata" not in posted
    assert "Create Shortcut stories through REST" in posted["description"]


def test_live_publish_reports_story_url_when_id_is_absent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": "https://app.shortcut.com/acme/story/42"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ShortcutStoryPublisher(api_token="shortcut_secret", client=client)

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.story_id is None
    assert result.story_url == "https://app.shortcut.com/acme/story/42"


def test_live_publish_requires_api_token_before_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing token should fail before network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ShortcutStoryPublisher(client=client)

    with pytest.raises(ShortcutStoryPublishError, match="SHORTCUT_API_TOKEN is required"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_live_publish_raises_structured_error_and_redacts_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="bad token=shortcut_secret "
            "https://api.app.shortcut.com/api/v3/stories?token=url_secret&safe=yes",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ShortcutStoryPublisher(
        api_token="shortcut_secret",
        api_url="https://api.app.shortcut.com/api/v3?token=site_secret",
        client=client,
    )

    with pytest.raises(ShortcutStoryPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert exc.value.status_code == 401
    assert "HTTP 401" in message
    assert "shortcut_secret" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "token=%3Credacted%3E" in message


def test_from_env_reads_shortcut_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHORTCUT_API_TOKEN", "env-token")
    monkeypatch.setenv("SHORTCUT_API_URL", "https://shortcut.test/api/v3")
    monkeypatch.setenv("SHORTCUT_WORKFLOW_STATE_ID", "123")
    monkeypatch.setenv("SHORTCUT_EPIC_ID", "456")
    monkeypatch.setenv("SHORTCUT_LABELS", "one,two")
    monkeypatch.setenv("SHORTCUT_OWNER_IDS", "user-1,user-2")
    monkeypatch.setenv("SHORTCUT_STORY_TYPE", "bug")
    monkeypatch.setenv("SHORTCUT_ESTIMATE", "8")
    monkeypatch.setenv("SHORTCUT_DEADLINE", "2026-05-15")
    monkeypatch.setenv("SHORTCUT_ITERATION_ID", "789")

    publisher = ShortcutStoryPublisher.from_env()

    assert publisher.api_token == "env-token"
    assert publisher.api_url == "https://shortcut.test/api/v3"
    assert publisher.workflow_state_id == 123
    assert publisher.epic_id == 456
    assert publisher.labels == ["one", "two"]
    assert publisher.owner_ids == ["user-1", "user-2"]
    assert publisher.story_type == "bug"
    assert publisher.estimate == 8
    assert publisher.deadline == "2026-05-15"
    assert publisher.iteration_id == 789


def test_exported_aliases_are_available() -> None:
    assert ShortcutStoriesPublisher is ShortcutStoryPublisher
    assert ShortcutStoryPublishResult.__name__ == "ShortcutStoryPublishResult"


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
