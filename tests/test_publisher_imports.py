"""Tests for publisher package exports."""

from __future__ import annotations

from max.publisher import (
    GitHubPullRequestReviewCommentPayload,
    GitHubPullRequestReviewCommentPublisher,
    GitHubPullRequestReviewCommentPublishError,
    GitHubPullRequestReviewCommentPublishResult,
    GitHubPullRequestReviewCommentsPublisher,
    GitHubReleasePayload,
    GitHubReleaseNotePublisher,
    GitHubReleaseNotePublishError,
    GitHubReleaseNotePublishResult,
    GitHubReleaseNotesPublisher,
    GitHubReleasePublisher,
    GitHubReleasePublishError,
    GitHubReleasePublishResult,
    GitHubReleasesPublisher,
    FigmaDevResourcePublisher,
    FigmaDevResourcePublishError,
    FigmaDevResourcePublishResult,
    FigmaDevResourcesPublisher,
    DropboxPaperDocCommentPublisher,
    DropboxPaperDocCommentPublishError,
    DropboxPaperDocCommentPublishResult,
    DropboxPaperDocCommentsPublisher,
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
    GitLabEpicPayload,
    GitLabEpicPublisher,
    GitLabEpicPublishError,
    GitLabEpicPublishResult,
    GitLabEpicsPublisher,
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
    GoogleChatWebhookPayload,
    GoogleChatWebhookPublisher,
    GoogleChatWebhookPublishError,
    GoogleChatWebhookPublishResult,
    GoogleChatWebhooksPublisher,
    TelegramWebhookPayload,
    TelegramWebhookPublisher,
    TelegramWebhookPublishError,
    TelegramWebhookPublishResult,
    TelegramWebhooksPublisher,
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
    BitbucketIssueCommentPayload,
    BitbucketIssueCommentPublisher,
    BitbucketIssueCommentPublishError,
    BitbucketIssueCommentPublishResult,
    BitbucketIssueCommentsPublisher,
)
from max.publisher.github_pull_request_review_comments import (
    GitHubPullRequestReviewCommentPublisher as ModuleGitHubPullRequestReviewCommentPublisher,
)
from max.publisher.github_releases import (
    GitHubReleasePublisher as ModuleGitHubReleasePublisher,
)
from max.publisher.github_release_notes import (
    GitHubReleaseNotePublisher as ModuleGitHubReleaseNotePublisher,
)
from max.publisher.figma_dev_resources import (
    FigmaDevResourcePublisher as ModuleFigmaDevResourcePublisher,
)
from max.publisher.dropbox_paper_doc_comments import (
    DropboxPaperDocCommentPublisher as ModuleDropboxPaperDocCommentPublisher,
)
from max.publisher.gitlab_merge_request_comments import (
    GitLabMergeRequestCommentPublisher as ModuleGitLabMergeRequestCommentPublisher,
)
from max.publisher.gitlab_epics import (
    GitLabEpicPublisher as ModuleGitLabEpicPublisher,
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
from max.publisher.google_chat_webhook import (
    GoogleChatWebhookPublisher as ModuleGoogleChatWebhookPublisher,
)
from max.publisher.telegram_webhook import (
    TelegramWebhookPublisher as ModuleTelegramWebhookPublisher,
)
from max.publisher.opsgenie_alerts import (
    OpsgenieAlertPublisher as ModuleOpsgenieAlertPublisher,
)
from max.publisher.servicenow_incidents import (
    ServiceNowIncidentPublisher as ModuleServiceNowIncidentPublisher,
)
from max.publisher.bitbucket_issue_comments import (
    BitbucketIssueCommentPublisher as ModuleBitbucketIssueCommentPublisher,
)


def test_gitlab_merge_request_comment_publisher_exports() -> None:
    assert GitLabMergeRequestCommentPublisher is ModuleGitLabMergeRequestCommentPublisher
    assert GitLabMergeRequestCommentsPublisher is GitLabMergeRequestCommentPublisher
    assert GitLabMergeRequestCommentPayload
    assert GitLabMergeRequestCommentPublishError
    assert GitLabMergeRequestCommentPublishResult


def test_gitlab_epic_publisher_exports() -> None:
    assert GitLabEpicPublisher is ModuleGitLabEpicPublisher
    assert GitLabEpicsPublisher is GitLabEpicPublisher
    assert GitLabEpicPayload
    assert GitLabEpicPublishError
    assert GitLabEpicPublishResult


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


def test_github_release_note_publisher_exports() -> None:
    assert GitHubReleaseNotePublisher is ModuleGitHubReleaseNotePublisher
    assert GitHubReleaseNotesPublisher is GitHubReleaseNotePublisher
    assert GitHubReleaseNotePublishError
    assert GitHubReleaseNotePublishResult


def test_figma_dev_resource_publisher_exports() -> None:
    assert FigmaDevResourcePublisher is ModuleFigmaDevResourcePublisher
    assert FigmaDevResourcesPublisher is FigmaDevResourcePublisher
    assert FigmaDevResourcePublishError
    assert FigmaDevResourcePublishResult


def test_dropbox_paper_doc_comment_publisher_exports() -> None:
    assert DropboxPaperDocCommentPublisher is ModuleDropboxPaperDocCommentPublisher
    assert DropboxPaperDocCommentsPublisher is DropboxPaperDocCommentPublisher
    assert DropboxPaperDocCommentPublishError
    assert DropboxPaperDocCommentPublishResult


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


def test_google_chat_webhook_publisher_exports() -> None:
    assert GoogleChatWebhookPublisher is ModuleGoogleChatWebhookPublisher
    assert GoogleChatWebhooksPublisher is GoogleChatWebhookPublisher
    assert GoogleChatWebhookPayload
    assert GoogleChatWebhookPublishError
    assert GoogleChatWebhookPublishResult


def test_telegram_webhook_publisher_exports() -> None:
    assert TelegramWebhookPublisher is ModuleTelegramWebhookPublisher
    assert TelegramWebhooksPublisher is TelegramWebhookPublisher
    assert TelegramWebhookPayload
    assert TelegramWebhookPublishError
    assert TelegramWebhookPublishResult


def test_bitbucket_issue_comment_publisher_exports() -> None:
    assert BitbucketIssueCommentPublisher is ModuleBitbucketIssueCommentPublisher
    assert BitbucketIssueCommentsPublisher is BitbucketIssueCommentPublisher
    assert BitbucketIssueCommentPayload
    assert BitbucketIssueCommentPublishError
    assert BitbucketIssueCommentPublishResult
