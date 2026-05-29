from __future__ import annotations

import httpx
import pytest

from max.publisher.pagerduty_change_events import PagerDutyChangeEventPublishError, PagerDutyChangeEventPublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_dry_run_builds_change_event_payload() -> None:
    result = PagerDutyChangeEventPublisher(routing_key="rk").publish(_spec(), links=[{"href": "https://x", "text": "run"}], custom_details={"env": "prod"})
    assert result.payload["change_event"]["payload"]["summary"] == "Zoom Chat Publisher"
    assert result.payload["change_event"]["links"][0]["text"] == "run"
    assert result.payload["change_event"]["payload"]["custom_details"]["env"] == "prod"


def test_live_publish_returns_dedup_key() -> None:
    publisher = PagerDutyChangeEventPublisher(routing_key="rk", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(202, json={"dedup_key": "dedup"}))))
    assert publisher.publish(_spec(), dry_run=False).dedup_key == "dedup"


def test_missing_key_and_http_error() -> None:
    with pytest.raises(PagerDutyChangeEventPublishError, match="ROUTING"):
        PagerDutyChangeEventPublisher().publish(_spec(), dry_run=False)
    publisher = PagerDutyChangeEventPublisher(routing_key="rk", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="bad rk"))))
    with pytest.raises(PagerDutyChangeEventPublishError) as exc:
        publisher.publish(_spec(), dry_run=False)
    assert "rk" not in str(exc.value)
