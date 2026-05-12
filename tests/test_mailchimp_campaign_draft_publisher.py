from __future__ import annotations

import httpx

from max.publisher.mailchimp_campaign_drafts import MailchimpCampaignDraftPublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_builds_mailchimp_campaign_payload() -> None:
    publisher = MailchimpCampaignDraftPublisher(server_prefix="us7", list_id="list_123")

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert publisher.campaigns_endpoint == "https://us7.api.mailchimp.com/3.0/campaigns"
    assert result.payload["campaign"]["type"] == "regular"
    assert result.payload["campaign"]["recipients"]["list_id"] == "list_123"
    assert "[Max] Intercom Conversation Note Publisher" == result.payload["campaign"]["settings"]["subject_line"]
    assert "Support teams need handoff context" in result.payload["content"]["plain_text"]


def test_live_publish_posts_campaign_create_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "camp_123", "web_id": 456})

    publisher = MailchimpCampaignDraftPublisher(
        server_prefix="us7",
        list_id="list_123",
        api_key="key-us7",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.campaign_id == "camp_123"
    assert result.web_id == "456"
    assert requests[0].url == "https://us7.api.mailchimp.com/3.0/campaigns"
    assert requests[0].headers["Authorization"].startswith("Basic ")
