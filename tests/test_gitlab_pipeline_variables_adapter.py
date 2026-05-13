"""Tests for GitLab pipeline variables import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_pipeline_variables_adapter import GitLabPipelineVariablesAdapter
from max.types.signal import SignalSourceType


def _variable(key: str, *, variable_type: str = "env_var", protected: bool = False, masked: bool = False) -> dict:
    return {
        "key": key,
        "value": "redacted",
        "variable_type": variable_type,
        "protected": protected,
        "masked": masked,
        "raw": False,
    }


@pytest.mark.asyncio
async def test_gitlab_pipeline_variables_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_variable("DEPLOY_ENV")], headers={"X-Next-Page": "2"})
        return httpx.Response(200, json=[_variable("KUBECONFIG", variable_type="file", protected=True, masked=True)])

    adapter = GitLabPipelineVariablesAdapter(
        private_token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={"project_ids": ["group/app"], "pipeline_ids": [99], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/group%2Fapp/pipelines/99/variables"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["key"] for signal in signals] == ["DEPLOY_ENV", "KUBECONFIG"]
    signal = signals[0]
    assert signal.id == "gitlab-pipeline-variable:group/app:99:DEPLOY_ENV"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "gitlab_pipeline_variables_import"
    assert signal.title == "GitLab pipeline variable DEPLOY_ENV"
    assert signal.metadata["project_id"] == "group/app"
    assert signal.metadata["pipeline_id"] == "99"
    assert signal.metadata["variable_type"] == "env_var"
    assert signal.metadata["raw"]["value"] == "redacted"
    assert "pipeline-variable" in signal.tags
    assert "pipeline:99" in signal.tags
    assert signals[1].metadata["variable_type"] == "file"
    assert "masked" in signals[1].tags
    assert "protected" in signals[1].tags


@pytest.mark.asyncio
async def test_gitlab_pipeline_variables_supports_config_aliases_and_path_encoding() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_variable(f"VAR_{len(requests)}")])

    adapter = GitLabPipelineVariablesAdapter(
        token="gitlab-token",
        config={
            "gitlab_url": "https://gitlab.example",
            "projects": [{"id": "group/already%2Fencoded"}, {"path": "42"}],
            "pipelines": [{"id": "10/child"}],
            "per_page": 10,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/group%2Falready%2Fencoded/pipelines/10%2Fchild/variables"
    assert requests[1].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/42/pipelines/10%2Fchild/variables"
    assert requests[0].url.params["per_page"] == "5"
    assert [signal.metadata["project_id"] for signal in signals] == ["group/already%2Fencoded", "42"]
    assert {signal.metadata["pipeline_id"] for signal in signals} == {"10/child"}


@pytest.mark.asyncio
async def test_gitlab_pipeline_variables_respects_per_pipeline_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_variable("FIRST"), _variable("SECOND")])

    adapter = GitLabPipelineVariablesAdapter(
        private_token="gitlab-token",
        config={
            "project_id": "group/app",
            "pipeline_ids": ["10", "11"],
            "page_size": 10,
            "per_pipeline_limit": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.params["per_page"] == "1"
    assert [signal.metadata["pipeline_id"] for signal in signals] == ["10", "11"]
    assert [signal.metadata["key"] for signal in signals] == ["FIRST", "FIRST"]


@pytest.mark.asyncio
async def test_gitlab_pipeline_variables_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabPipelineVariablesAdapter(config={"project_id": "1", "pipeline_id": "2"}).fetch() == []
    assert await GitLabPipelineVariablesAdapter(token="token", config={"pipeline_id": "2"}).fetch() == []
    assert await GitLabPipelineVariablesAdapter(token="token", config={"project_id": "1"}).fetch() == []
    assert await GitLabPipelineVariablesAdapter(token="token", config={"project_id": "1", "pipeline_id": "2"}).fetch(limit=0) == []
