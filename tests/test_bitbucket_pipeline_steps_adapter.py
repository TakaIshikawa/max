"""Tests for Bitbucket pipeline steps import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.bitbucket_pipeline_steps_adapter import (
    BitbucketPipelineStepsAdapter,
    BitbucketPipelineStepsImportAdapter,
)
from max.types.signal import SignalSourceType


STEP = {
    "uuid": "{step-uuid}",
    "name": "Build image",
    "state": {"name": "COMPLETED", "type": "pipeline_step_state_completed", "result": {"name": "FAILED"}},
    "duration_in_seconds": 55,
    "started_on": "2026-05-01T10:01:00+00:00",
    "completed_on": "2026-05-01T10:01:55+00:00",
    "links": {
        "html": {"href": "https://bitbucket.org/example/tool/pipelines/results/42/steps/{step-uuid}"}
    },
}


@pytest.mark.asyncio
async def test_bitbucket_pipeline_steps_bearer_fetches_filters_follows_next_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "values": [STEP, {**STEP, "uuid": "{ignored}", "state": {"result": {"name": "SUCCESSFUL"}}}],
                    "next": "https://api.bitbucket.test/2.0/repositories/example/tool/pipelines/{pipeline-uuid}/steps/?page=2",
                },
            )
        return httpx.Response(200, json={"values": [{**STEP, "uuid": "{step-uuid-2}", "name": "Deploy"}]})

    adapter = BitbucketPipelineStepsImportAdapter(
        token="bb-token",
        api_url="https://api.bitbucket.test/2.0",
        config={
            "workspace": "example",
            "repo_slug": "tool",
            "pipeline_uuids": ["{pipeline-uuid}"],
            "statuses": ["FAILED"],
            "page_size": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert BitbucketPipelineStepsAdapter is BitbucketPipelineStepsImportAdapter
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer bb-token"
    assert requests[0].headers["User-Agent"] == "max-bitbucket-pipeline-steps-import/1"
    assert requests[0].url.path == "/2.0/repositories/example/tool/pipelines/{pipeline-uuid}/steps/"
    assert requests[0].url.params["pagelen"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["step_uuid"] for signal in signals] == ["{step-uuid}", "{step-uuid-2}"]

    signal = signals[0]
    assert signal.id == "bitbucket-pipeline-step:example:tool:{pipeline-uuid}:{step-uuid}"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "bitbucket_pipeline_steps_import"
    assert signal.title == "example/tool pipeline step Build image FAILED"
    assert signal.content == "step Build image, status FAILED, duration 55s"
    assert signal.url.endswith("/steps/{step-uuid}")
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "failure_data"
    assert signal.metadata["workspace"] == "example"
    assert signal.metadata["repository"] == "tool"
    assert signal.metadata["pipeline_uuid"] == "{pipeline-uuid}"
    assert signal.metadata["status"] == "FAILED"
    assert signal.metadata["duration"] == 55
    assert signal.metadata["raw"]["uuid"] == "{step-uuid}"
    assert "step" in signal.tags
    assert "failed" in signal.tags


@pytest.mark.asyncio
async def test_bitbucket_pipeline_steps_supports_basic_auth_and_total_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [STEP, {**STEP, "uuid": "{step-uuid-2}"}]})

    adapter = BitbucketPipelineStepsImportAdapter(
        config={
            "username": "ada",
            "app_password": "app-pass",
            "workspace": "example",
            "repository": "example/tool",
            "pipeline_uuid": "{pipeline-uuid}",
            "page_len": 50,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    expected = "Basic " + base64.b64encode(b"ada:app-pass").decode()
    assert requests[0].headers["Authorization"] == expected
    assert requests[0].url.params["pagelen"] == "1"
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_bitbucket_pipeline_steps_supports_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [STEP]})

    adapter = BitbucketPipelineStepsImportAdapter(
        config={"workspace": "example", "repo_slug": "tool", "pipeline_uuid": "{pipeline-uuid}"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["step_uuid"] == "{step-uuid}"


@pytest.mark.asyncio
async def test_bitbucket_pipeline_steps_empty_without_config_auth_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_BEARER_TOKEN", raising=False)

    assert await BitbucketPipelineStepsImportAdapter(config={"workspace": "example", "repo_slug": "tool"}).fetch() == []
    assert await BitbucketPipelineStepsImportAdapter(token="token", config={"workspace": "example"}).fetch() == []
    assert (
        await BitbucketPipelineStepsImportAdapter(
            token="token",
            config={"workspace": "example", "repo_slug": "tool", "pipeline_uuid": "{pipeline-uuid}"},
        ).fetch(limit=0)
        == []
    )

    failing = BitbucketPipelineStepsImportAdapter(
        token="token",
        config={"workspace": "example", "repo_slug": "tool", "pipeline_uuid": "{pipeline-uuid}"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = BitbucketPipelineStepsImportAdapter(
        token="token",
        config={"workspace": "example", "repo_slug": "tool", "pipeline_uuid": "{pipeline-uuid}"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
