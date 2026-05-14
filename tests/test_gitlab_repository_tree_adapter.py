"""Tests for GitLab repository tree import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_repository_tree_adapter import GitLabRepositoryTreeAdapter


TREE_ENTRY = {
    "id": "8b137891791fe96927ad78e64b0aad7bded08bdc",
    "name": "app.py",
    "type": "blob",
    "path": "src/app.py",
    "mode": "100644",
    "web_url": "https://gitlab.example/acme/api/-/blob/main/src/app.py",
}


@pytest.mark.asyncio
async def test_gitlab_repository_tree_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=[TREE_ENTRY])
        return httpx.Response(200, json=[{**TREE_ENTRY, "id": "dir-sha", "name": "lib", "type": "tree", "path": "src/lib"}])

    adapter = GitLabRepositoryTreeAdapter(
        token="gl-token",
        api_url="https://gitlab.example",
        config={"project_path": "acme/api", "path": "src", "ref": "main", "recursive": True, "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.raw_path.startswith(b"/api/v4/projects/acme%2Fapi/repository/tree")
    assert requests[0].headers["PRIVATE-TOKEN"] == "gl-token"
    assert requests[0].headers["User-Agent"] == "max-gitlab-repository-tree-import/1"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["path"] == "src"
    assert requests[0].url.params["ref"] == "main"
    assert requests[0].url.params["recursive"] == "true"
    assert requests[1].url.params["page"] == "2"

    signal = signals[0]
    assert signal.id == f"gitlab-repository-tree:acme/api:{TREE_ENTRY['id']}"
    assert signal.source_adapter == "gitlab_repository_tree_import"
    assert signal.title == "acme/api blob src/app.py"
    assert signal.content == "GitLab repository tree entry for acme/api; src/app.py; blob; mode 100644"
    assert signal.url == TREE_ENTRY["web_url"]
    assert signal.metadata["project_id"] == "acme/api"
    assert signal.metadata["project_path"] == "acme/api"
    assert signal.metadata["path"] == "src/app.py"
    assert signal.metadata["name"] == "app.py"
    assert signal.metadata["type"] == "blob"
    assert signal.metadata["mode"] == "100644"
    assert signal.metadata["id"] == TREE_ENTRY["id"]
    assert signal.metadata["ref"] == "main"
    assert signal.metadata["filter_path"] == "src"
    assert signal.metadata["raw"] == TREE_ENTRY


@pytest.mark.asyncio
async def test_gitlab_repository_tree_respects_multiple_projects_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        project = request.url.path.split("/projects/", 1)[1].split("/repository", 1)[0]
        return httpx.Response(200, json=[{**TREE_ENTRY, "id": project, "path": f"{project}/README.md"}])

    adapter = GitLabRepositoryTreeAdapter(
        token="gl-token",
        config={"projects": ["acme/api", "acme/web"], "per_page": 100},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.raw_path.startswith(b"/api/v4/projects/acme%2Fapi/repository/tree")
    assert requests[0].url.params["per_page"] == "2"
    assert requests[1].url.raw_path.startswith(b"/api/v4/projects/acme%2Fweb/repository/tree")
    assert requests[1].url.params["per_page"] == "1"
    assert [signal.metadata["project_path"] for signal in signals] == ["acme/api", "acme/web"]


@pytest.mark.asyncio
async def test_gitlab_repository_tree_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabRepositoryTreeAdapter(config={"project_path": "acme/api"}).fetch() == []
    assert await GitLabRepositoryTreeAdapter(token="token").fetch() == []
    assert await GitLabRepositoryTreeAdapter(token="token", config={"project_path": "acme/api"}).fetch(limit=0) == []

    failing = GitLabRepositoryTreeAdapter(
        token="bad",
        config={"project_path": "acme/api"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
