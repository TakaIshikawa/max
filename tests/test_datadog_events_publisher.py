from __future__ import annotations

import httpx
import pytest

from max.publisher.datadog_events import DatadogEventPublishError, DatadogEventPublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_dry_run_builds_event_payload() -> None:
    result = DatadogEventPublisher(api_url="https://dd.example/api/v1").publish(_spec(), tags=["Team A", "team-a"])
    assert result.payload["endpoint"] == "https://dd.example/api/v1/events"
    assert result.payload["event"]["tags"] == ["team-a"]


def test_from_env_url_and_live_post(monkeypatch) -> None:
    monkeypatch.setenv("DATADOG_API_KEY", "key")
    monkeypatch.setenv("DATADOG_SITE", "datadoghq.eu")
    requests: list[httpx.Request] = []
    publisher = DatadogEventPublisher.from_env(client=httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(202, json={"event_id": "evt"}))))
    assert publisher.publish(_spec(), dry_run=False).event_id == "evt"
    assert str(requests[0].url) == "https://api.datadoghq.eu/api/v1/events"
    assert requests[0].headers["DD-API-KEY"] == "key"


def test_invalid_alert_type_and_redaction() -> None:
    with pytest.raises(DatadogEventPublishError):
        DatadogEventPublisher(alert_type="critical")
    publisher = DatadogEventPublisher(api_key="key", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text="bad key"))))
    with pytest.raises(DatadogEventPublishError) as exc:
        publisher.publish(_spec(), dry_run=False)
    assert "key" not in str(exc.value)
