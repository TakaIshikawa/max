"""Tests for Sentry project release files import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_project_release_files_adapter import SentryProjectReleaseFilesAdapter


def _artifact(file_id: str = "file-1") -> dict:
    return {
        "id": file_id,
        "name": "~/app.js",
        "dist": "web",
        "size": 12345,
        "sha1": "abc123",
        "headers": {"Content-Type": "application/javascript"},
        "dateCreated": "2026-05-01T10:00:00Z",
        "url": f"https://sentry.example/files/{file_id}",
    }


@pytest.mark.asyncio
async def test_sentry_release_files_fetches_pages_and_maps_artifact_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_artifact("file-1")],
                headers={"Link": '<https://sentry.example/api/0/projects/acme/web/releases/1.0.0/files/?cursor=next>; rel="next"; results="true"'},
            )
        return httpx.Response(
            200,
            json=[_artifact("file-2")],
            headers={"Link": '<https://sentry.example/api/0/projects/acme/web/releases/1.0.0/files/?cursor=end>; rel="next"; results="false"'},
        )

    adapter = SentryProjectReleaseFilesAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"organization_slug": "acme", "project_slugs": ["web"], "release_versions": ["1.0.0"], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/projects/acme/web/releases/1.0.0/files/"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[1].url.params["cursor"] == "next"
    assert [signal.metadata["file_id"] for signal in signals] == ["file-1", "file-2"]
    signal = signals[0]
    assert signal.id == "sentry-release-file:acme:web:1.0.0:file-1"
    assert signal.source_adapter == "sentry_project_release_files_import"
    assert signal.title == "web release 1.0.0 file ~/app.js"
    assert signal.url == "https://sentry.example/files/file-1"
    assert "dist web" in signal.content
    assert "12345 bytes" in signal.content
    assert "sha abc123" in signal.content
    assert signal.metadata["sentry_organization_slug"] == "acme"
    assert signal.metadata["sentry_project_slug"] == "web"
    assert signal.metadata["release_version"] == "1.0.0"
    assert signal.metadata["file_name"] == "~/app.js"
    assert signal.metadata["dist"] == "web"
    assert signal.metadata["size"] == 12345
    assert signal.metadata["sha"] == "abc123"
    assert signal.metadata["headers"]["Content-Type"] == "application/javascript"
    assert signal.metadata["raw"]["id"] == "file-1"


@pytest.mark.asyncio
async def test_sentry_release_files_handles_missing_optional_dist_and_headers() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"name": "bundle.css", "hash": "def456", "createdAt": "2026-05-02T10:00:00Z"}],
        )

    adapter = SentryProjectReleaseFilesAdapter(
        token="sentry-token",
        config={"org": "acme", "projects": ["web"], "releases": ["2.0.0"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert signals[0].id == "sentry-release-file:acme:web:2.0.0:bundle.css"
    assert signals[0].content == "Sentry web release 2.0.0 file bundle.css; sha def456; created 2026-05-02T10:00:00Z"
    assert signals[0].metadata["dist"] is None
    assert signals[0].metadata["headers"] == {}
    assert signals[0].metadata["sha"] == "def456"


@pytest.mark.asyncio
async def test_sentry_release_files_empty_lists_required_config_auth_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    assert await SentryProjectReleaseFilesAdapter(config={"org": "acme", "projects": ["web"], "releases": ["1"]}).fetch() == []
    assert await SentryProjectReleaseFilesAdapter(auth_token="token", config={"projects": ["web"], "releases": ["1"]}).fetch() == []
    assert await SentryProjectReleaseFilesAdapter(auth_token="token", config={"org": "acme", "releases": ["1"]}).fetch() == []
    assert await SentryProjectReleaseFilesAdapter(auth_token="token", config={"org": "acme", "projects": ["web"]}).fetch() == []
    assert await SentryProjectReleaseFilesAdapter(auth_token="token", config={"org": "acme", "projects": ["web"], "releases": ["1"]}).fetch(limit=0) == []

    empty = SentryProjectReleaseFilesAdapter(
        auth_token="token",
        config={"org": "acme", "projects": ["web"], "releases": ["1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))),
    )
    assert await empty.fetch(limit=10) == []

    failing = SentryProjectReleaseFilesAdapter(
        auth_token="token",
        config={"org": "acme", "projects": ["web"], "releases": ["1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_sentry_release_files_cross_product_projects_and_releases_with_encoded_version() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        project = request.url.path.split("/projects/acme/", 1)[1].split("/", 1)[0]
        return httpx.Response(200, json=[_artifact(f"{project}-{len(requests)}")])

    adapter = SentryProjectReleaseFilesAdapter(
        auth_token="token",
        config={"org": "acme", "projects": ["web", "api"], "version": "frontend@1.0.0+build"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/projects/acme/web/releases/frontend@1.0.0+build/files/"
    assert [signal.metadata["sentry_project_slug"] for signal in signals] == ["web", "api"]
