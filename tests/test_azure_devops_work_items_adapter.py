"""Tests for Azure DevOps work item import adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from max.imports.azure_devops_work_items_adapter import AzureDevOpsWorkItemsAdapter


@pytest.mark.asyncio
async def test_azure_devops_runs_wiql_fetches_batch_and_maps_work_item() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/_apis/wit/wiql"):
            return httpx.Response(200, json={"workItems": [{"id": 101}]})
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": 101,
                        "fields": {
                            "System.Title": "Fix import bug",
                            "System.Description": "Customers cannot import alerts",
                            "System.State": "Active",
                            "System.Reason": "Investigating",
                            "System.WorkItemType": "Bug",
                            "System.AssignedTo": {"displayName": "Ada", "uniqueName": "ada@example.com", "id": "a"},
                            "System.CreatedBy": {"displayName": "Grace", "uniqueName": "grace@example.com", "id": "g"},
                            "System.Tags": "customer;imports",
                            "System.AreaPath": "Max\\Imports",
                            "System.IterationPath": "Max\\Sprint 1",
                            "System.CreatedDate": "2026-05-01T00:00:00Z",
                            "System.ChangedDate": "2026-05-02T00:00:00Z",
                        },
                        "_links": {"html": {"href": "https://dev.azure.com/acme/max/_workitems/edit/101"}},
                        "relations": [{"rel": "System.LinkTypes.Related", "url": "https://example.test"}],
                    }
                ]
            },
        )

    adapter = AzureDevOpsWorkItemsAdapter(
        organization="acme",
        project="max",
        personal_access_token="pat",
        config={"wiql": "SELECT [System.Id] FROM WorkItems", "api_version": "7.0"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=10)

    assert requests[0].url.path == "/acme/max/_apis/wit/wiql"
    assert requests[0].url.params["api-version"] == "7.0"
    assert requests[1].url.path == "/acme/max/_apis/wit/workitemsbatch"
    assert requests[1].url.params["api-version"] == "7.0"
    assert signals[0].title == "Fix import bug"
    assert signals[0].content == "Customers cannot import alerts"
    assert signals[0].url == "https://dev.azure.com/acme/max/_workitems/edit/101"
    assert signals[0].metadata["azure_devops_work_item_id"] == 101
    assert signals[0].metadata["state"] == "Active"
    assert signals[0].metadata["reason"] == "Investigating"
    assert signals[0].metadata["work_item_type"] == "Bug"
    assert signals[0].metadata["assigned_to"]["displayName"] == "Ada"
    assert signals[0].metadata["created_by"]["displayName"] == "Grace"
    assert signals[0].metadata["tags"] == ["customer", "imports"]
    assert signals[0].metadata["area_path"] == "Max\\Imports"
    assert signals[0].metadata["iteration_path"] == "Max\\Sprint 1"
    assert signals[0].metadata["created_date"] == "2026-05-01T00:00:00Z"
    assert signals[0].metadata["changed_date"] == "2026-05-02T00:00:00Z"
    assert signals[0].metadata["relations"] == [{"rel": "System.LinkTypes.Related", "url": "https://example.test"}]


@pytest.mark.asyncio
async def test_azure_devops_batches_more_than_two_hundred_ids() -> None:
    batch_sizes: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/_apis/wit/wiql"):
            return httpx.Response(200, json={"workItems": [{"id": item_id} for item_id in range(1, 206)]})
        body = json.loads(request.read().decode())
        batch_sizes.append(len(body["ids"]))
        return httpx.Response(200, json={"value": []})

    adapter = AzureDevOpsWorkItemsAdapter(organization="acme", project="max", personal_access_token="pat", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=205) == []
    assert batch_sizes == [200, 5]


@pytest.mark.asyncio
async def test_azure_devops_http_failure_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = AzureDevOpsWorkItemsAdapter(organization="acme", project="max", personal_access_token="pat", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch() == []
