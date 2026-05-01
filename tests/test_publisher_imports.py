"""Tests for publisher package exports."""

from __future__ import annotations

from max.publisher import (
    GitHubPullRequestReviewCommentPayload,
    GitHubPullRequestReviewCommentPublisher,
    GitHubPullRequestReviewCommentPublishError,
    GitHubPullRequestReviewCommentPublishResult,
    GitHubPullRequestReviewCommentsPublisher,
    GitHubReleasePayload,
    GitHubReleasePublisher,
    GitHubReleasePublishError,
    GitHubReleasePublishResult,
    GitHubReleasesPublisher,
    GitLabSnippetPayload,
    GitLabSnippetPublisher,
    GitLabSnippetPublishError,
    GitLabSnippetPublishResult,
    GitLabSnippetsPublisher,
    GitLabMergeRequestCommentPayload,
    GitLabMergeRequestCommentPublisher,
    GitLabMergeRequestCommentPublishError,
    GitLabMergeRequestCommentPublishResult,
    GitLabMergeRequestCommentsPublisher,
    MattermostWebhookPayload,
    MattermostWebhookPublisher,
    MattermostWebhookPublishError,
    MattermostWebhookPublishResult,
    MattermostWebhooksPublisher,
    WebexWebhookPayload,
    WebexWebhookPublisher,
    WebexWebhookPublishError,
    WebexWebhookPublishResult,
    WebexWebhooksPublisher,
    OpsgenieAlertPayload,
    OpsgenieAlertPublisher,
    OpsgenieAlertPublishError,
    OpsgenieAlertPublishResult,
    OpsgenieAlertsPublisher,
    ServiceNowIncidentPayload,
    ServiceNowIncidentPublisher,
    ServiceNowIncidentPublishError,
    ServiceNowIncidentPublishResult,
    ServiceNowIncidentsPublisher,
)
from max.publisher.github_pull_request_review_comments import (
    GitHubPullRequestReviewCommentPublisher as ModuleGitHubPullRequestReviewCommentPublisher,
)
from max.publisher.github_releases import (
    GitHubReleasePublisher as ModuleGitHubReleasePublisher,
)
from max.publisher.gitlab_merge_request_comments import (
    GitLabMergeRequestCommentPublisher as ModuleGitLabMergeRequestCommentPublisher,
)
from max.publisher.gitlab_snippets import (
    GitLabSnippetPublisher as ModuleGitLabSnippetPublisher,
)
from max.publisher.mattermost_webhook import (
    MattermostWebhookPublisher as ModuleMattermostWebhookPublisher,
)
from max.publisher.webex_webhook import (
    WebexWebhookPublisher as ModuleWebexWebhookPublisher,
)
from max.publisher.opsgenie_alerts import (
    OpsgenieAlertPublisher as ModuleOpsgenieAlertPublisher,
)
from max.publisher.servicenow_incidents import (
    ServiceNowIncidentPublisher as ModuleServiceNowIncidentPublisher,
)


def test_gitlab_merge_request_comment_publisher_exports() -> None:
    assert GitLabMergeRequestCommentPublisher is ModuleGitLabMergeRequestCommentPublisher
    assert GitLabMergeRequestCommentsPublisher is GitLabMergeRequestCommentPublisher
    assert GitLabMergeRequestCommentPayload
    assert GitLabMergeRequestCommentPublishError
    assert GitLabMergeRequestCommentPublishResult


def test_gitlab_snippet_publisher_exports() -> None:
    assert GitLabSnippetPublisher is ModuleGitLabSnippetPublisher
    assert GitLabSnippetsPublisher is GitLabSnippetPublisher
    assert GitLabSnippetPayload
    assert GitLabSnippetPublishError
    assert GitLabSnippetPublishResult


def test_github_pull_request_review_comment_publisher_exports() -> None:
    assert (
        GitHubPullRequestReviewCommentPublisher
        is ModuleGitHubPullRequestReviewCommentPublisher
    )
    assert GitHubPullRequestReviewCommentsPublisher is GitHubPullRequestReviewCommentPublisher
    assert GitHubPullRequestReviewCommentPayload
    assert GitHubPullRequestReviewCommentPublishError
    assert GitHubPullRequestReviewCommentPublishResult


def test_github_release_publisher_exports() -> None:
    assert GitHubReleasePublisher is ModuleGitHubReleasePublisher
    assert GitHubReleasesPublisher is GitHubReleasePublisher
    assert GitHubReleasePayload
    assert GitHubReleasePublishError
    assert GitHubReleasePublishResult


def test_servicenow_incident_publisher_exports() -> None:
    assert ServiceNowIncidentPublisher is ModuleServiceNowIncidentPublisher
    assert ServiceNowIncidentsPublisher is ServiceNowIncidentPublisher
    assert ServiceNowIncidentPayload
    assert ServiceNowIncidentPublishError
    assert ServiceNowIncidentPublishResult


def test_opsgenie_alert_publisher_exports() -> None:
    assert OpsgenieAlertPublisher is ModuleOpsgenieAlertPublisher
    assert OpsgenieAlertsPublisher is OpsgenieAlertPublisher
    assert OpsgenieAlertPayload
    assert OpsgenieAlertPublishError
    assert OpsgenieAlertPublishResult


def test_mattermost_webhook_publisher_exports() -> None:
    assert MattermostWebhookPublisher is ModuleMattermostWebhookPublisher
    assert MattermostWebhooksPublisher is MattermostWebhookPublisher
    assert MattermostWebhookPayload
    assert MattermostWebhookPublishError
    assert MattermostWebhookPublishResult


def test_webex_webhook_publisher_exports() -> None:
    assert WebexWebhookPublisher is ModuleWebexWebhookPublisher
    assert WebexWebhooksPublisher is WebexWebhookPublisher
    assert WebexWebhookPayload
    assert WebexWebhookPublishError
    assert WebexWebhookPublishResult
