"""Tests for Bitbucket deployments import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.bitbucket_deployments_adapter import (
    BitbucketDeploymentsAdapter,
    BitbucketDeploymentsImportAdapter,
)
from max.types.signal import SignalSourceType


DEPLOYMENT = {
    "uuid": "{deployment-uuid}",
    "state": {"name": "SUCCESSFUL", "type": "deployment_state"},
    "environment": {"uuid": "{env-uuid}", "name": "production", "slug": "production"},
    "step": {"uuid": "{step-uuid}", "name": "Deploy"},
    "commit": {"hash": "abc1234", "links": {"html": {"href": "https://bitbucket.org/example/tool/commits/abc1234"}}},
    "deployer": {"display_name": "Ada", "nickname": "ada", "uuid": "{user-uuid}"},
    "release": {"version": "2026.05.1", "name": "May release"},
    "links": {"html": {"href": "https://bitbucket.org/example/tool/deployments/{deployment-uuid}"}},
    "started_on": "2026-05-01T10:00:00+00:00",
    "completed_on": "2026-05-01T10:05:00+00:00",
    "created_on": "2026-05-01T09:59:00+00:00",
    "updated_on": "2026-05-01T10:05:00+00:00",
}


@pytest.mark.asyncio
async def test_bitbucket_deployments_bearer_fetches_filters_follows_next_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "values": [DEPLOYMENT],
                    "next": "https://api.bitbucket.test/2.0/repositories/example/tool/deployments/?page=2",
                },
            )
        return httpx.Response(
            200,
            json={"values": [{**DEPLOYMENT, "uuid": "{deployment-uuid-2}", "state": {"name": "FAILED"}}]},
        )

    adapter = BitbucketDeploymentsAdapter(
        bearer_token="bb-token",
        api_url="https://api.bitbucket.test/2.0",
        config={
            "workspace": "example",
            "repo_slug": "tool",
            "environments": ["production", "staging"],
            "statuses": ["SUCCESSFUL", "FAILED"],
            "page_size": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert BitbucketDeploymentsImportAdapter is BitbucketDeploymentsAdapter
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer bb-token"
    assert requests[0].headers["User-Agent"] == "max-bitbucket-deployments-import/1"
    assert requests[0].url.path == "/2.0/repositories/example/tool/deployments/"
    assert requests[0].url.params["pagelen"] == "1"
    assert requests[0].url.params.get_list("environment") == ["production", "staging"]
    assert requests[0].url.params.get_list("status") == ["SUCCESSFUL", "FAILED"]
    assert requests[1].url.params["page"] == "2"
    assert "environment" not in requests[1].url.params
    assert "status" not in requests[1].url.params
    assert [signal.metadata["deployment_uuid"] for signal in signals] == ["{deployment-uuid}", "{deployment-uuid-2}"]
    signal = signals[0]
    assert signal.id == "bitbucket-deployment:example:tool:{deployment-uuid}"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "bitbucket_deployments_import"
    assert signal.title == "example/tool deployment SUCCESSFUL"
    assert signal.content == "status SUCCESSFUL, environment production, release 2026.05.1, commit abc1234"
    assert signal.url.endswith("/deployments/{deployment-uuid}")
    assert signal.author == "Ada"
    assert signal.published_at is not None
    assert signal.metadata["workspace"] == "example"
    assert signal.metadata["repository"] == "tool"
    assert signal.metadata["status"] == "SUCCESSFUL"
    assert signal.metadata["environment_name"] == "production"
    assert signal.metadata["step"]["name"] == "Deploy"
    assert signal.metadata["commit"]["hash"] == "abc1234"
    assert signal.metadata["deployer"]["display_name"] == "Ada"
    assert signal.metadata["release_version"] == "2026.05.1"
    assert signal.metadata["started_on"] == "2026-05-01T10:00:00+00:00"
    assert signal.metadata["completed_on"] == "2026-05-01T10:05:00+00:00"
    assert signal.metadata["raw"]["uuid"] == "{deployment-uuid}"
    assert "deployment" in signal.tags
    assert "production" in signal.tags
    assert "successful" in signal.tags


@pytest.mark.asyncio
async def test_bitbucket_deployments_supports_repository_and_basic_auth_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "values": [
                    DEPLOYMENT,
                    {**DEPLOYMENT, "uuid": "{deployment-uuid-2}"},
                ]
            },
        )

    adapter = BitbucketDeploymentsAdapter(
        config={
            "workspace": "example",
            "repository": "team/tool",
            "username": "ada",
            "app_password": "app-pass",
            "page_len": 50,
            "environment": "production",
            "status": "SUCCESSFUL",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    expected = "Basic " + base64.b64encode(b"ada:app-pass").decode()
    assert requests[0].headers["Authorization"] == expected
    assert requests[0].url.path == "/2.0/repositories/example/tool/deployments/"
    assert requests[0].url.params["pagelen"] == "1"
    assert requests[0].url.params["environment"] == "production"
    assert requests[0].url.params["status"] == "SUCCESSFUL"
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_bitbucket_deployments_empty_without_config_auth_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    monkeypatch.delenv("BITBUCKET_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)

    assert await BitbucketDeploymentsAdapter(config={"workspace": "example", "repo_slug": "tool"}).fetch() == []
    assert await BitbucketDeploymentsAdapter(bearer_token="token", config={"workspace": "example"}).fetch() == []
    assert await BitbucketDeploymentsAdapter(bearer_token="token", config={"workspace": "example", "repo_slug": "tool"}).fetch(limit=0) == []

    empty = BitbucketDeploymentsAdapter(
        bearer_token="token",
        config={"workspace": "example", "repo_slug": "tool"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"values": []}))),
    )
    assert await empty.fetch(limit=2) == []

    failing = BitbucketDeploymentsAdapter(
        bearer_token="token",
        config={"workspace": "example", "repo_slug": "tool"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
