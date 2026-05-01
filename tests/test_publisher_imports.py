"""Tests for publisher package exports."""

from __future__ import annotations

from max.publisher import (
    GitLabMergeRequestCommentPayload,
    GitLabMergeRequestCommentPublisher,
    GitLabMergeRequestCommentPublishError,
    GitLabMergeRequestCommentPublishResult,
    GitLabMergeRequestCommentsPublisher,
)
from max.publisher.gitlab_merge_request_comments import (
    GitLabMergeRequestCommentPublisher as ModuleGitLabMergeRequestCommentPublisher,
)


def test_gitlab_merge_request_comment_publisher_exports() -> None:
    assert GitLabMergeRequestCommentPublisher is ModuleGitLabMergeRequestCommentPublisher
    assert GitLabMergeRequestCommentsPublisher is GitLabMergeRequestCommentPublisher
    assert GitLabMergeRequestCommentPayload
    assert GitLabMergeRequestCommentPublishError
    assert GitLabMergeRequestCommentPublishResult
