"""Tests for Bitbucket pipeline runs import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.bitbucket_pipeline_runs_adapter import (
    BitbucketPipelineRunsAdapter,
    BitbucketPipelineRunsImportAdapter,
)
from max.types.signal import SignalSourceType


PIPELINE = {
    "uuid": "{pipeline-uuid}",
    "build_number": 42,
    "state": {"name": "COMPLETED", "type": "pipeline_state_completed", "result": {"name": "FAILED"}},
    "target": {
        "type": "pipeline_ref_target",
        "ref_name": "main",
        "ref_type": "branch",
        "commit": {
            "hash": "abcdef1234567890",
            "links": {"html": {"href": "https://bitbucket.org/example/tool/commits/abcdef1234567890"}},
        },
    },
    "trigger": {"name": "PUSH"},
    "duration_in_seconds": 123,
    "creator": {"display_name": "Ada", "nickname": "ada", "uuid": "{user-uuid}"},
    "links": {"html": {"href": "https://bitbucket.org/example/tool/pipelines/results/42"}},
    "created_on": "2026-05-01T10:00:00+00:00",
    "started_on": "2026-05-01T10:01:00+00:00",
    "completed_on": "2026-05-01T10:03:03+00:00",
}


@pytest.mark.asyncio
async def test_bitbucket_pipeline_runs_bearer_fetches_filters_follows_next_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "values": [PIPELINE],
                    "next": "https://api.bitbucket.test/2.0/repositories/example/tool/pipelines/?page=2",
                },
            )
        return httpx.Response(
            200,
            json={"values": [{**PIPELINE, "uuid": "{pipeline-uuid-2}", "build_number": 43}]},
        )

    adapter = BitbucketPipelineRunsImportAdapter(
        token="bb-token",
        api_url="https://api.bitbucket.test/2.0",
        config={
            "workspace": "example",
            "repositories": ["tool"],
            "branches": ["main", "release"],
            "statuses": ["FAILED", "SUCCESSFUL"],
            "page_size": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert BitbucketPipelineRunsAdapter is BitbucketPipelineRunsImportAdapter
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer bb-token"
    assert requests[0].headers["User-Agent"] == "max-bitbucket-pipeline-runs-import/1"
    assert requests[0].url.path == "/2.0/repositories/example/tool/pipelines/"
    assert requests[0].url.params["pagelen"] == "1"
    assert requests[0].url.params.get_list("target.ref_name") == ["main", "release"]
    assert requests[0].url.params.get_list("status") == ["FAILED", "SUCCESSFUL"]
    assert requests[1].url.params["page"] == "2"
    assert "target.ref_name" not in requests[1].url.params
    assert "status" not in requests[1].url.params

    assert [signal.metadata["build_number"] for signal in signals] == [42, 43]
    signal = signals[0]
    assert signal.id == "bitbucket-pipeline-run:example:tool:{pipeline-uuid}"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "bitbucket_pipeline_runs_import"
    assert signal.title == "example/tool pipeline FAILED"
    assert signal.content == "status FAILED, branch main, commit abcdef123456, trigger PUSH, duration 123s"
    assert signal.url.endswith("/pipelines/results/42")
    assert signal.author == "Ada"
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "failure_data"
    assert signal.metadata["workspace"] == "example"
    assert signal.metadata["repository"] == "tool"
    assert signal.metadata["status"] == "FAILED"
    assert signal.metadata["branch"] == "main"
    assert signal.metadata["commit_hash"] == "abcdef1234567890"
    assert signal.metadata["trigger"] == "PUSH"
    assert signal.metadata["duration"] == 123
    assert signal.metadata["creator"]["display_name"] == "Ada"
    assert signal.metadata["raw"]["uuid"] == "{pipeline-uuid}"
    assert "bitbucket" in signal.tags
    assert "pipeline" in signal.tags
    assert "failed" in signal.tags


@pytest.mark.asyncio
async def test_bitbucket_pipeline_runs_supports_basic_auth_targets_and_total_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [PIPELINE, {**PIPELINE, "uuid": "{pipeline-uuid-2}"}]})

    adapter = BitbucketPipelineRunsImportAdapter(
        config={
            "username": "ada",
            "app_password": "app-pass",
            "targets": [
                {"workspace": "example", "repo": "tool"},
                {"workspace": "example", "repository": "api"},
            ],
            "page_len": 50,
            "branch": "main",
            "status": "FAILED",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    expected = "Basic " + base64.b64encode(b"ada:app-pass").decode()
    assert requests[0].headers["Authorization"] == expected
    assert len(requests) == 1
    assert requests[0].url.path == "/2.0/repositories/example/tool/pipelines/"
    assert requests[0].url.params["pagelen"] == "1"
    assert requests[0].url.params["target.ref_name"] == "main"
    assert requests[0].url.params["status"] == "FAILED"
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_bitbucket_pipeline_runs_supports_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_BEARER_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [PIPELINE]})

    adapter = BitbucketPipelineRunsImportAdapter(
        config={"workspace": "example", "repository": "tool"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["pipeline_uuid"] == "{pipeline-uuid}"


@pytest.mark.asyncio
async def test_bitbucket_pipeline_runs_empty_without_config_auth_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_BEARER_TOKEN", raising=False)

    assert await BitbucketPipelineRunsImportAdapter(config={"workspace": "example", "repository": "tool"}).fetch() == []
    assert await BitbucketPipelineRunsImportAdapter(token="token", config={"workspace": "example"}).fetch() == []
    assert (
        await BitbucketPipelineRunsImportAdapter(
            token="token",
            config={"workspace": "example", "repository": "tool"},
        ).fetch(limit=0)
        == []
    )

    failing = BitbucketPipelineRunsImportAdapter(
        token="token",
        config={"workspace": "example", "repository": "tool"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = BitbucketPipelineRunsImportAdapter(
        token="token",
        config={"workspace": "example", "repository": "tool"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
