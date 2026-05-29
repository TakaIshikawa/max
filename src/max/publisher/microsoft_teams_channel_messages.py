"""Microsoft Teams Graph channel message publisher compatibility module."""

from __future__ import annotations

import os
from typing import Any

from max.publisher.teams_channel_messages import DEFAULT_GRAPH_API_URL, DEFAULT_TIMEOUT_SECONDS
from max.publisher.teams_channel_messages import TeamsChannelMessagePublishError as MicrosoftTeamsChannelMessagePublishError
from max.publisher.teams_channel_messages import TeamsChannelMessagePublisher


class MicrosoftTeamsChannelMessagePublisher(TeamsChannelMessagePublisher):
    @classmethod
    def from_env(cls, **kwargs: Any) -> MicrosoftTeamsChannelMessagePublisher:
        return cls(
            access_token=kwargs.get("access_token") or os.getenv("MICROSOFT_GRAPH_TOKEN") or os.getenv("MICROSOFT_GRAPH_ACCESS_TOKEN"),
            team_id=kwargs.get("team_id") or os.getenv("TEAMS_TEAM_ID"),
            channel_id=kwargs.get("channel_id") or os.getenv("TEAMS_CHANNEL_ID"),
            api_url=kwargs.get("api_url") or os.getenv("MICROSOFT_GRAPH_API_URL") or os.getenv("TEAMS_GRAPH_API_URL") or DEFAULT_GRAPH_API_URL,
            subject=kwargs.get("subject"),
            importance=kwargs.get("importance"),
            content_type=kwargs.get("content_type") or "html",
            timeout=kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS),
            client=kwargs.get("client"),
        )

MicrosoftTeamsChannelMessagesPublisher = MicrosoftTeamsChannelMessagePublisher

__all__ = ["MicrosoftTeamsChannelMessagePublisher", "MicrosoftTeamsChannelMessagesPublisher", "MicrosoftTeamsChannelMessagePublishError"]
