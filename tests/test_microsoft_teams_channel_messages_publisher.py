from __future__ import annotations

import httpx

from max.publisher.microsoft_teams_channel_messages import MicrosoftTeamsChannelMessagePublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_dry_run_builds_graph_endpoint_and_html_body() -> None:
    publisher = MicrosoftTeamsChannelMessagePublisher(team_id="team", channel_id="channel", api_url="https://graph.example/v1.0")
    result = publisher.publish(_spec(), dry_run=True)
    assert result.payload["graph_payload"]["body"]["contentType"] == "html"
    assert publisher.message_endpoint() == "https://graph.example/v1.0/teams/team/channels/channel/messages"


def test_live_publish_posts_with_bearer_auth() -> None:
    requests: list[httpx.Request] = []
    publisher = MicrosoftTeamsChannelMessagePublisher(access_token="token", team_id="team", channel_id="channel", api_url="https://graph.example/v1.0", client=httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(201, json={"id": "msg"}))))
    assert publisher.publish(_spec(), dry_run=False).message_id == "msg"
    assert requests[0].headers["Authorization"] == "Bearer token"


def test_from_env_reads_microsoft_graph_names(monkeypatch) -> None:
    monkeypatch.setenv("MICROSOFT_GRAPH_TOKEN", "token")
    monkeypatch.setenv("TEAMS_TEAM_ID", "team")
    monkeypatch.setenv("TEAMS_CHANNEL_ID", "channel")
    monkeypatch.setenv("MICROSOFT_GRAPH_API_URL", "https://graph.example/v1.0")
    publisher = MicrosoftTeamsChannelMessagePublisher.from_env()
    assert publisher.access_token == "token"
    assert publisher.message_endpoint() == "https://graph.example/v1.0/teams/team/channels/channel/messages"
