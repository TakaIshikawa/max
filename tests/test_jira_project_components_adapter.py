"""Tests for Jira project components import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.jira_project_components_adapter import JiraProjectComponentsAdapter


def _component(number: int, *, name: str | None = None) -> dict:
    return {
        "id": str(1000 + number),
        "name": name or f"API {number}",
        "description": f"Component {number} description",
        "self": f"https://jira.example/rest/api/3/component/{1000 + number}",
        "lead": {"displayName": "Ada Lovelace", "accountId": "abc"},
        "assigneeType": "PROJECT_LEAD",
        "archived": False,
        "released": True,
    }


@pytest.mark.asyncio
async def test_jira_project_components_fetches_multiple_projects_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        project = request.url.path.split("/")[-2]
        return httpx.Response(200, json={"startAt": 0, "total": 1, "isLast": True, "values": [_component(1, name=f"{project} API")]})

    adapter = JiraProjectComponentsAdapter(
        base_url="https://jira.example",
        email="ada@example.com",
        api_token="jira_token",
        config={"project_keys": ["MAX", "OPS"], "max_results": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert [request.url.path for request in requests] == ["/rest/api/3/project/MAX/component", "/rest/api/3/project/OPS/component"]
    assert requests[0].url.params["startAt"] == "0"
    assert requests[0].url.params["maxResults"] == "1"
    assert [signal.metadata["project_key"] for signal in signals] == ["MAX", "OPS"]
    assert signals[0].id == "jira-project-component:MAX:1001"
    assert signals[0].source_adapter == "jira_project_components_import"
    assert signals[0].title == "MAX API"
    assert "lead Ada Lovelace" in signals[0].content
    assert signals[0].metadata["jira_component_id"] == "1001"
    assert signals[0].metadata["description"] == "Component 1 description"
    assert signals[0].metadata["lead_name"] == "Ada Lovelace"
    assert signals[0].metadata["assignee_type"] == "PROJECT_LEAD"
    assert signals[0].metadata["archived"] is False
    assert signals[0].metadata["released"] is True


@pytest.mark.asyncio
async def test_jira_project_components_empty_and_missing_optional_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/MAX/component"):
            return httpx.Response(200, json=[{"id": "2001", "name": "No lead"}])
        return httpx.Response(200, json=[])

    adapter = JiraProjectComponentsAdapter(
        base_url="https://jira.example",
        bearer_token="bearer",
        config={"project_keys": ["MAX", "EMPTY"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].metadata["lead_name"] is None
    assert signals[0].metadata["description"] is None
    assert signals[0].metadata["project_key"] == "MAX"


@pytest.mark.asyncio
async def test_jira_project_components_paginates_and_handles_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("startAt") == "0":
            return httpx.Response(200, json={"startAt": 0, "total": 2, "isLast": False, "values": [_component(1)]})
        return httpx.Response(200, json={"startAt": 1, "total": 2, "isLast": True, "values": [_component(2)]})

    adapter = JiraProjectComponentsAdapter(
        base_url="https://jira.example",
        bearer_token="bearer",
        config={"project_key": "MAX", "max_results": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requests[0].headers["Authorization"] == "Bearer bearer"
    assert [request.url.params["startAt"] for request in requests] == ["0", "1"]
    assert [signal.metadata["jira_component_id"] for signal in signals] == ["1001", "1002"]

    failing = JiraProjectComponentsAdapter(
        base_url="https://jira.example",
        bearer_token="bearer",
        config={"project_keys": ["MAX"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=5) == []

    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_BEARER_TOKEN", raising=False)
    assert await JiraProjectComponentsAdapter(bearer_token="bearer", config={"project_key": "MAX"}).fetch() == []
