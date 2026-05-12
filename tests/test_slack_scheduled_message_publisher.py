from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.slack_scheduled_messages import (
    SlackScheduledMessagePublishError,
    SlackScheduledMessagePublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": "dbf-slack001",
            "idea_id": "bu-slack001",
            "domain": "platform",
            "category": "launch",
        },
        "project": {"title": "Slack Scheduled Message Publisher", "summary": "Queue review notifications for launch windows."},
        "evidence": {"rationale": "Launch reviews need timed Slack reminders.", "insight_ids": ["ins-1"]},
        "quality": {"quality_score": 8.0, "rejection_tags": ["timing_risk"]},
        "evaluation": {"overall_score": 87.0, "recommendation": "yes"},
    }


def test_dry_run_builds_deterministic_schedule_message_payload() -> None:
    publisher = SlackScheduledMessagePublisher(
        token="xoxb-token",
        channel="C123",
        post_at=1_800_000_000,
        username="Max",
        icon_emoji=":rocket:",
        metadata={"run_id": "run-1"},
    )

    first = publisher.publish(_tact_spec(), dry_run=True)
    second = publisher.publish(_tact_spec(), dry_run=True)

    assert first.payload == second.payload
    assert first.dry_run is True
    assert first.endpoint == "https://slack.com/api/chat.scheduleMessage"
    assert first.channel == "C123"
    assert first.payload["channel"] == "C123"
    assert first.payload["post_at"] == 1_800_000_000
    assert "Slack Scheduled Message Publisher" in first.payload["text"]
    assert first.payload["blocks"][0]["type"] == "section"
    assert first.payload["metadata"]["event_type"] == "max_scheduled_message"
    assert first.payload["metadata"]["event_payload"]["publisher"] == "max.slack_scheduled_messages"
    assert first.payload["metadata"]["event_payload"]["run_id"] == "run-1"
    assert first.payload["username"] == "Max"
    assert first.payload["icon_emoji"] == ":rocket:"


def test_live_publish_posts_schedule_message_with_bearer_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "scheduled_message_id": "Q123", "channel": "C123"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SlackScheduledMessagePublisher(
        token="xoxb-token",
        channel="C123",
        post_at="1800000001",
        api_url="https://slack.example.test/api",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.scheduled_message_id == "Q123"
    assert result.channel == "C123"
    assert requests[0].url == "https://slack.example.test/api/chat.scheduleMessage"
    assert requests[0].headers["Authorization"] == "Bearer xoxb-token"
    posted = json.loads(requests[0].read())
    assert posted["channel"] == "C123"
    assert posted["post_at"] == 1_800_000_001
    assert posted["metadata"]["event_payload"]["source_id"] == "dbf-slack001"


def test_from_env_reads_slack_scheduled_message_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "env-token")
    monkeypatch.setenv("SLACK_CHANNEL", "CENV")
    monkeypatch.setenv("SLACK_SCHEDULED_POST_AT", "1800000002")
    monkeypatch.setenv("SLACK_API_URL", "https://slack.env.test/api")

    publisher = SlackScheduledMessagePublisher.from_env()

    assert publisher.token == "env-token"
    assert publisher.channel == "CENV"
    assert publisher.post_at == 1_800_000_002
    assert publisher.endpoint == "https://slack.env.test/api/chat.scheduleMessage"


def test_validation_provider_errors_and_secret_redaction() -> None:
    with pytest.raises(SlackScheduledMessagePublishError, match="post_at"):
        SlackScheduledMessagePublisher(channel="C123", post_at="tomorrow")

    with pytest.raises(SlackScheduledMessagePublishError, match="SLACK_CHANNEL"):
        SlackScheduledMessagePublisher(post_at=1).publish(_tact_spec())

    with pytest.raises(SlackScheduledMessagePublishError, match="SLACK_BOT_TOKEN"):
        SlackScheduledMessagePublisher(channel="C123", post_at=1).publish(_tact_spec(), dry_run=False)

    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": False, "error": "bad_auth", "token": "xoxb-secret"})))
    publisher = SlackScheduledMessagePublisher(token="xoxb-secret", channel="C123", post_at=1, client=client)
    with pytest.raises(SlackScheduledMessagePublishError, match="bad_auth") as exc:
        publisher.publish(_tact_spec(), dry_run=False)
    assert "xoxb-secret" not in str(exc.value)

    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="failed token=xoxb-secret")))
    publisher = SlackScheduledMessagePublisher(token="xoxb-secret", channel="C123", post_at=1, client=client)
    with pytest.raises(SlackScheduledMessagePublishError, match="HTTP 500") as exc:
        publisher.publish(_tact_spec(), dry_run=False)
    assert "xoxb-secret" not in str(exc.value)
