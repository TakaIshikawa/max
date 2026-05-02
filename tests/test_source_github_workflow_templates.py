"""Tests for GitHub workflow templates source adapter."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.errors import SourceAuthError, SourceRateLimitError
from max.sources.github_workflow_templates import GitHubWorkflowTemplatesAdapter
from max.types.signal import SignalSourceType


WORKFLOW_CONTENT = """\
name: Node.js CI
on:
  - push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""

PROPERTIES_CONTENT = {
    "name": "Node.js",
    "description": "Build and test a Node.js project.",
    "categories": ["JavaScript", "npm", "CI"],
}


def _encoded(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _response(payload: object, *, status_code: int = 200, headers: dict | None = None) -> MagicMock:
    request = httpx.Request("GET", "https://api.github.test/repos/actions/starter-workflows")
    response = httpx.Response(status_code, json=payload, headers=headers or {}, request=request)
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = response.headers
    resp.json.side_effect = response.json
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=request,
            response=response,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def _file_response(content: str, *, path: str, sha: str = "sha-file") -> MagicMock:
    return _response(
        {
            "type": "file",
            "name": path.rsplit("/", 1)[-1],
            "path": path,
            "sha": sha,
            "encoding": "base64",
            "content": _encoded(content),
            "html_url": f"https://github.com/actions/starter-workflows/blob/main/{path}",
        }
    )


@pytest.mark.asyncio
async def test_fetch_normalizes_default_starter_workflow_templates() -> None:
    adapter = GitHubWorkflowTemplatesAdapter(
        config={"api_url": "https://api.github.test", "paths": ["ci"], "timeout": 9}
    )
    requests: list[dict] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        if url.endswith("/contents/ci"):
            return _response(
                [
                    {
                        "type": "file",
                        "name": "node.js.yml",
                        "path": "ci/node.js.yml",
                        "sha": "workflow-sha",
                        "html_url": "https://github.com/actions/starter-workflows/blob/main/ci/node.js.yml",
                        "download_url": "https://raw.githubusercontent.test/ci/node.js.yml",
                    },
                    {
                        "type": "file",
                        "name": "node.js.properties.json",
                        "path": "ci/node.js.properties.json",
                        "sha": "properties-sha",
                    },
                ]
            )
        if url.endswith("/contents/ci/node.js.yml"):
            return _file_response(WORKFLOW_CONTENT, path="ci/node.js.yml")
        if url.endswith("/contents/ci/node.js.properties.json"):
            return _file_response(json.dumps(PROPERTIES_CONTENT), path="ci/node.js.properties.json")
        if url.endswith("/commits"):
            return _response(
                [
                    {
                        "sha": "commit-sha",
                        "html_url": "https://github.com/actions/starter-workflows/commit/commit-sha",
                        "commit": {
                            "author": {"name": "GitHub", "date": "2026-04-20T12:00:00Z"},
                            "committer": {"date": "2026-04-21T12:00:00Z"},
                        },
                    }
                ]
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_workflow_templates.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert mock_cls.call_args.kwargs["timeout"] == 9.0
    assert requests[0]["url"] == "https://api.github.test/repos/actions/starter-workflows/contents/ci"
    assert requests[-1]["params"] == {"path": "ci/node.js.yml", "per_page": 1}

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "github-workflow-template:actions/starter-workflows:ci/node.js.yml:workflow-sha"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "github_workflow_templates"
    assert signal.title == "actions/starter-workflows workflow template: Node.js"
    assert signal.url == "https://github.com/actions/starter-workflows/blob/main/ci/node.js.yml"
    assert signal.published_at is not None
    assert "javascript" in signal.tags
    assert "ci" in signal.tags
    assert signal.metadata["repository"] == "actions/starter-workflows"
    assert signal.metadata["path"] == "ci/node.js.yml"
    assert signal.metadata["language"] == "JavaScript"
    assert signal.metadata["category"] == "JavaScript"
    assert signal.metadata["categories"] == ["JavaScript", "npm", "CI"]
    assert signal.metadata["events"] == ["push"]
    assert signal.metadata["job_count"] == 1
    assert signal.metadata["latest_commit_sha"] == "commit-sha"
    assert signal.metadata["latest_commit_at"] == "2026-04-21T12:00:00+00:00"
    assert signal.metadata["signal_role"] == "market"


@pytest.mark.asyncio
async def test_fetch_uses_configured_repositories_and_skips_malformed_entries() -> None:
    adapter = GitHubWorkflowTemplatesAdapter(
        config={
            "repositories": [" example/workflows ", {"repository": "example/other"}, ""],
            "paths": "templates",
            "api_url": "https://api.github.test",
            "max_templates_per_repo": 1,
        }
    )
    requests: list[str] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append(url)
        if url.endswith("/example/workflows/contents/templates"):
            return _response(
                [
                    {"type": "file", "name": "bad.yml"},
                    {
                        "type": "file",
                        "name": "python.yml",
                        "path": "templates/python.yml",
                        "sha": "python-sha",
                    },
                    {"type": "file", "name": "python.properties.json", "path": "templates/python.properties.json"},
                ]
            )
        if url.endswith("/contents/templates/python.yml"):
            return _file_response("name: Python CI\non: push\njobs: {test: {runs-on: ubuntu-latest}}\n", path="templates/python.yml")
        if url.endswith("/contents/templates/python.properties.json"):
            return _file_response("{not-json", path="templates/python.properties.json")
        if url.endswith("/commits"):
            return _response([])
        if url.endswith("/example/other/contents/templates"):
            return _response([])
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.github_workflow_templates.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert adapter.repositories == ["example/workflows", "example/other"]
    assert adapter.paths == ["templates"]
    assert len(signals) == 1
    assert signals[0].metadata["repository"] == "example/workflows"
    assert signals[0].metadata["path"] == "templates/python.yml"
    assert signals[0].metadata["language"] == "python"
    assert "example/other" in requests[-1]


@pytest.mark.asyncio
async def test_fetch_tolerates_transient_directory_errors() -> None:
    adapter = GitHubWorkflowTemplatesAdapter(
        config={"repositories": ["example/bad", "example/ok"], "paths": ["ci"], "api_url": "https://api.github.test"}
    )
    requests: list[str] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        requests.append(url)
        if "example/bad" in url:
            return _response({"message": "server error"}, status_code=500)
        if url.endswith("/contents/ci"):
            return _response([{"type": "file", "name": "go.yml", "path": "ci/go.yml", "sha": "go-sha"}])
        if url.endswith("/contents/ci/go.yml"):
            return _file_response("name: Go\non: push\njobs: {build: {runs-on: ubuntu-latest}}\n", path="ci/go.yml")
        if url.endswith("/commits"):
            return _response([])
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock), \
         patch("max.sources.github_workflow_templates.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len([url for url in requests if "example/bad" in url]) == 4
    assert len(signals) == 1
    assert signals[0].metadata["repository"] == "example/ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "headers", "expected_error"),
    [
        (401, {}, SourceAuthError),
        (403, {}, SourceAuthError),
        (429, {"Retry-After": "0"}, SourceRateLimitError),
        (403, {"X-RateLimit-Remaining": "0"}, SourceRateLimitError),
    ],
)
async def test_fetch_raises_auth_and_rate_limit_errors(status_code, headers, expected_error) -> None:
    adapter = GitHubWorkflowTemplatesAdapter(
        config={"repositories": ["example/tool"], "paths": ["ci"], "api_url": "https://api.github.test"}
    )

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return _response({"message": "error"}, status_code=status_code, headers=headers)

    with patch("max.sources.retry.asyncio.sleep", new_callable=AsyncMock), \
         patch("max.sources.github_workflow_templates.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(expected_error):
            await adapter.fetch(limit=10)


def test_config_parsing_and_token_resolution(monkeypatch) -> None:
    monkeypatch.setenv("ALT_GITHUB_TOKEN", "env-token")
    adapter = GitHubWorkflowTemplatesAdapter(
        config={
            "repositories": [" example/tool ", "example/tool", "", 1],
            "paths": [" ci ", "ci", "", 2],
            "max_templates_per_repo": "12",
            "token_env": "ALT_GITHUB_TOKEN",
            "api_url": "https://github.enterprise.test/api/v3/",
            "timeout": "7.5",
        }
    )

    assert adapter.repositories == ["example/tool"]
    assert adapter.paths == ["ci"]
    assert adapter.max_templates_per_repo == 12
    assert adapter.token == "env-token"
    assert adapter.api_url == "https://github.enterprise.test/api/v3"
    assert adapter.timeout == 7.5
