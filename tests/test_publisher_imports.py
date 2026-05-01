"""Tests for publisher package exports."""

from __future__ import annotations

from max.publisher import (
    GitLabMergeRequestCommentPayload,
    GitLabMergeRequestCommentPublisher,
    GitLabMergeRequestCommentPublishError,
    GitLabMergeRequestCommentPublishResult,
    GitLabMergeRequestCommentsPublisher,
    ServiceNowIncidentPayload,
    ServiceNowIncidentPublisher,
    ServiceNowIncidentPublishError,
    ServiceNowIncidentPublishResult,
    ServiceNowIncidentsPublisher,
)
from max.publisher.gitlab_merge_request_comments import (
    GitLabMergeRequestCommentPublisher as ModuleGitLabMergeRequestCommentPublisher,
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


def test_servicenow_incident_publisher_exports() -> None:
    assert ServiceNowIncidentPublisher is ModuleServiceNowIncidentPublisher
    assert ServiceNowIncidentsPublisher is ServiceNowIncidentPublisher
    assert ServiceNowIncidentPayload
    assert ServiceNowIncidentPublishError
    assert ServiceNowIncidentPublishResult
