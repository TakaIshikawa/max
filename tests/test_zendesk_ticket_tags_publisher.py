from __future__ import annotations

import httpx
import pytest

from max.publisher.zendesk_ticket_tags import ZendeskTicketTagPublishError, ZendeskTicketTagPublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_dry_run_sorts_and_deduplicates_tags() -> None:
    result = ZendeskTicketTagPublisher(base_url="https://zd.example", ticket_id="42").publish(_spec(), tags=["Beta Tag", "beta-tag"])
    assert result.payload["payload"]["ticket"]["tags"] == ["beta-tag", "max-idea", "source-bu-zoom001"]


def test_from_env_and_live_put(monkeypatch) -> None:
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "acme")
    monkeypatch.setenv("ZENDESK_EMAIL", "a@example.com")
    monkeypatch.setenv("ZENDESK_API_TOKEN", "tok")
    monkeypatch.setenv("ZENDESK_TICKET_ID", "42")
    requests: list[httpx.Request] = []
    publisher = ZendeskTicketTagPublisher.from_env(client=httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200, json={"ticket": {"id": 42}}))))
    assert publisher.publish(_spec(), dry_run=False).status_code == 200
    assert str(requests[0].url) == "https://acme.zendesk.com/api/v2/tickets/42.json"


def test_http_failure_redacts_token() -> None:
    publisher = ZendeskTicketTagPublisher(base_url="https://zd.example", ticket_id="42", email="a", api_token="tok", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="bad tok"))))
    with pytest.raises(ZendeskTicketTagPublishError) as exc:
        publisher.publish(_spec(), dry_run=False)
    assert "tok" not in str(exc.value)
