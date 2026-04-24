"""Tests for Azure DevOps work item publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.azure_devops_work_items import (
    AzureDevOpsWorkItemPublishError,
    AzureDevOpsWorkItemPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-azdo001",
            "status": "approved",
            "domain": "devtools",
        },
        "project": {
            "title": "Azure DevOps Publish Idea",
            "summary": "Publish an idea as an Azure DevOps work item",
        },
        "problem": {"statement": "Enterprise teams need Azure DevOps handoff."},
        "solution": {"approach": "Create work items through JSON Patch."},
        "execution": {
            "mvp_scope": ["Azure DevOps publisher", "REST endpoint"],
            "validation_plan": "Call the endpoint in dry-run and live modes.",
        },
        "evidence": {"rationale": "Customer signals mention Azure Boards."},
        "quality": {"quality_score": 0.82},
        "evaluation": {"overall_score": 80.0, "recommendation": "yes"},
    }


def test_build_work_item_payload_returns_json_patch_operations() -> None:
    publisher = AzureDevOpsWorkItemPublisher(
        "max-org",
        "Delivery Project",
        work_item_type="Product Backlog Item",
        area_path="Delivery Project\\Platform",
        iteration_path="Delivery Project\\Sprint 1",
        tags=["handoff", "max"],
    )

    payload = publisher.build_work_item_payload(_tact_spec()).to_dict()

    assert payload["organization"] == "max-org"
    assert payload["project"] == "Delivery Project"
    assert payload["work_item_type"] == "Product Backlog Item"
    assert payload["operations"][0] == {
        "op": "add",
        "path": "/fields/System.Title",
        "value": "[Max] Azure DevOps Publish Idea",
    }
    assert payload["operations"][2:] == [
        {
            "op": "add",
            "path": "/fields/System.AreaPath",
            "value": "Delivery Project\\Platform",
        },
        {
            "op": "add",
            "path": "/fields/System.IterationPath",
            "value": "Delivery Project\\Sprint 1",
        },
        {
            "op": "add",
            "path": "/fields/System.Tags",
            "value": "max; devtools; recommendation-yes; quality-scored; handoff",
        },
    ]
    assert payload["operations"][1]["path"] == "/fields/System.Description"
    assert "Call the endpoint in dry-run and live modes." in payload["operations"][1]["value"]
    assert payload["metadata"]["idea_id"] == "bu-azdo001"


def test_dry_run_returns_payload_without_credentials_or_http() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run should not make HTTP requests")

    publisher = AzureDevOpsWorkItemPublisher(
        "max-org",
        "Max",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.work_item_id is None
    assert result.payload["operations"][0]["value"] == "[Max] Azure DevOps Publish Idea"


def test_live_publish_posts_json_patch_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": 42})

    publisher = AzureDevOpsWorkItemPublisher(
        "max-org",
        "Max Project",
        personal_access_token="azdo_pat",
        work_item_type="Task",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.work_item_id == "42"
    assert result.work_item_url == "https://dev.azure.com/max-org/Max%20Project/_workitems/edit/42"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == (
        "https://dev.azure.com/max-org/Max%20Project/_apis/wit/workitems/"
        "$Task?api-version=7.1"
    )
    assert request.headers["Content-Type"] == "application/json-patch+json"
    expected_auth = "Basic " + base64.b64encode(b":azdo_pat").decode("ascii")
    assert request.headers["Authorization"] == expected_auth
    body = json.loads(request.content)
    assert body == result.payload["operations"]


def test_live_publish_requires_pat() -> None:
    publisher = AzureDevOpsWorkItemPublisher("max-org", "Max")

    with pytest.raises(AzureDevOpsWorkItemPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert "AZURE_DEVOPS_PAT" in str(exc.value)


def test_live_publish_raises_structured_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized"})

    publisher = AzureDevOpsWorkItemPublisher(
        "max-org",
        "Max",
        personal_access_token="azdo_pat",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AzureDevOpsWorkItemPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401
    assert "Azure DevOps work item publish failed with HTTP 401" in str(exc.value)


def test_from_env_uses_azure_devops_fallbacks(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_DEVOPS_ORGANIZATION", "env-org")
    monkeypatch.setenv("AZURE_DEVOPS_PROJECT", "Env Project")
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "env-pat")
    monkeypatch.setenv("AZURE_DEVOPS_WORK_ITEM_TYPE", "Bug")
    monkeypatch.setenv("AZURE_DEVOPS_AREA_PATH", "Env Project\\Area")
    monkeypatch.setenv("AZURE_DEVOPS_ITERATION_PATH", "Env Project\\Iteration")
    monkeypatch.setenv("AZURE_DEVOPS_TAGS", "one; two")

    publisher = AzureDevOpsWorkItemPublisher.from_env()

    assert publisher.organization == "env-org"
    assert publisher.project == "Env Project"
    assert publisher.personal_access_token == "env-pat"
    assert publisher.work_item_type == "Bug"
    assert publisher.area_path == "Env Project\\Area"
    assert publisher.iteration_path == "Env Project\\Iteration"
    assert publisher.tags == ["one", "two"]
