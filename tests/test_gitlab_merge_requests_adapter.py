"""Compatibility tests for the GitLab merge requests adapter path."""

from __future__ import annotations

from max.sources.gitlab_merge_requests import GitLabMergeRequestsAdapter


def test_gitlab_merge_requests_adapter_is_available() -> None:
    adapter = GitLabMergeRequestsAdapter(config={"project_ids": ["example/tool"]})

    assert adapter.name == "gitlab_merge_requests"
    assert "example/tool" in adapter.project_ids
