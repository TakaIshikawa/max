"""Outbound publishing integrations."""

from max.publisher.github_issues import (
    GitHubIssuePayload,
    GitHubIssuePublisher,
    GitHubIssuePublishError,
    GitHubIssuePublishResult,
    GitHubIssuesPublisher,
)
from max.publisher.discord_webhook import (
    DiscordWebhookPublisher,
    DiscordWebhookPublishError,
    DiscordWebhookPublishResult,
)
from max.publisher.slack_webhook import (
    SlackWebhookPublisher,
    SlackWebhookPublishError,
    SlackWebhookPublishResult,
)
from max.publisher.webhook import WebhookPublishError, WebhookPublisher, WebhookPublishResult

__all__ = [
    "GitHubIssuePayload",
    "GitHubIssuePublisher",
    "GitHubIssuePublishError",
    "GitHubIssuePublishResult",
    "GitHubIssuesPublisher",
    "DiscordWebhookPublisher",
    "DiscordWebhookPublishError",
    "DiscordWebhookPublishResult",
    "SlackWebhookPublisher",
    "SlackWebhookPublishError",
    "SlackWebhookPublishResult",
    "WebhookPublisher",
    "WebhookPublishError",
    "WebhookPublishResult",
]
