"""Tests for publisher package exports."""

from __future__ import annotations

from max.publisher import (
    GitHubPullRequestReviewCommentPayload,
    GitHubPullRequestReviewCommentPublisher,
    GitHubPullRequestReviewCommentPublishError,
    GitHubPullRequestReviewCommentPublishResult,
    GitHubPullRequestReviewCommentsPublisher,
    GitLabMergeRequestCommentPayload,
    GitLabMergeRequestCommentPublisher,
    GitLabMergeRequestCommentPublishError,
    GitLabMergeRequestCommentPublishResult,
    GitLabMergeRequestCommentsPublisher,
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
from max.publisher.gitlab_merge_request_comments import (
    GitLabMergeRequestCommentPublisher as ModuleGitLabMergeRequestCommentPublisher,
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


def test_github_pull_request_review_comment_publisher_exports() -> None:
    assert (
        GitHubPullRequestReviewCommentPublisher
        is ModuleGitHubPullRequestReviewCommentPublisher
    )
    assert GitHubPullRequestReviewCommentsPublisher is GitHubPullRequestReviewCommentPublisher
    assert GitHubPullRequestReviewCommentPayload
    assert GitHubPullRequestReviewCommentPublishError
    assert GitHubPullRequestReviewCommentPublishResult


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
