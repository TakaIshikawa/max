"""Tests for publishing ideas to Azure DevOps through the REST API."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_azure_devops_api.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
    return path


@pytest.fixture
def client(db_path):
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _seed_idea(db_path: str, *, with_evaluation: bool = True) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-azdo001",
                title="Azure DevOps Publish Idea",
                one_liner="Publish an idea as an Azure DevOps work item",
                category=BuildableCategory.APPLICATION,
                problem="API clients cannot publish Azure DevOps work items",
                solution="Expose the Azure DevOps publisher over REST",
                value_proposition="Agents can publish without shelling out",
                validation_plan="Call the REST endpoint",
                domain="devtools",
                status="approved",
                evidence_rationale="Customer signals mention Azure Boards handoff.",
                evidence_signals=["sig-azdo001"],
                inspiring_insights=["ins-azdo001"],
            )
        )
        if with_evaluation:
            store.insert_evaluation(_evaluation("bu-azdo001"))
    finally:
        store.close()


def _evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=80.0,
        recommendation="yes",
    )


def test_publish_azure_devops_dry_run_returns_exact_json_patch_without_credentials(
    client,
    db_path,
) -> None:
    _seed_idea(db_path)

    response = client.post(
        "/api/v1/ideas/bu-azdo001/publish/azure-devops",
        json={
            "organization": "max-org",
            "project": "Max Project",
            "work_item_type": "Product Backlog Item",
            "area_path": "Max Project\\Platform",
            "iteration_path": "Max Project\\Sprint 1",
            "tags": ["handoff"],
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["organization"] == "max-org"
    assert data["project"] == "Max Project"
    assert data["work_item_type"] == "Product Backlog Item"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["work_item_id"] is None
    assert data["work_item_url"] is None
    assert data["payload"]["operations"][0] == {
        "op": "add",
        "path": "/fields/System.Title",
        "value": "[Max] Azure DevOps Publish Idea",
    }
    assert data["payload"]["operations"][2:] == [
        {"op": "add", "path": "/fields/System.AreaPath", "value": "Max Project\\Platform"},
        {
            "op": "add",
            "path": "/fields/System.IterationPath",
            "value": "Max Project\\Sprint 1",
        },
        {
            "op": "add",
            "path": "/fields/System.Tags",
            "value": "max; devtools; recommendation-yes; quality-scored; handoff",
        },
    ]
    assert "Call the REST endpoint" in data["payload"]["operations"][1]["value"]
    assert data["publication_attempt"]["target_type"] == "azure_devops_work_item"
    assert data["publication_attempt"]["target_url"] == (
        "https://dev.azure.com/max-org/Max%20Project/_apis/wit/workitems/"
        "$Product%20Backlog%20Item?api-version=7.1"
    )
    assert data["publication_attempt"]["status"] == "success"


def test_publish_azure_devops_live_success_records_publication_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": 42})

    def publisher_from_env(**kwargs):
        from max.publisher.azure_devops_work_items import AzureDevOpsWorkItemPublisher

        return AzureDevOpsWorkItemPublisher(
            kwargs["organization"],
            kwargs["project"],
            personal_access_token=kwargs["personal_access_token"],
            work_item_type=kwargs["work_item_type"],
            area_path=kwargs["area_path"],
            iteration_path=kwargs["iteration_path"],
            tags=kwargs["tags"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.AzureDevOpsWorkItemPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/ideas/bu-azdo001/publish/azure-devops",
        json={
            "organization": "max-org",
            "project": "Max Project",
            "personal_access_token": "azdo_pat",
            "work_item_type": "Task",
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 200
    assert data["work_item_id"] == "42"
    assert data["work_item_url"] == "https://dev.azure.com/max-org/Max%20Project/_workitems/edit/42"
    assert data["publication_attempt"]["target_type"] == "azure_devops_work_item"
    assert data["publication_attempt"]["target_url"] == data["work_item_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["publication_attempt"]["response_status"] == 200
    assert len(requests) == 1
    assert json.loads(requests[0].content) == data["payload"]["operations"]

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-azdo001")
        assert len(attempts) == 1
        assert attempts[0]["target_type"] == "azure_devops_work_item"
        assert attempts[0]["target_url"] == data["work_item_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_azure_devops_http_failure_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden"})

    def publisher_from_env(**kwargs):
        from max.publisher.azure_devops_work_items import AzureDevOpsWorkItemPublisher

        return AzureDevOpsWorkItemPublisher(
            kwargs["organization"],
            kwargs["project"],
            personal_access_token=kwargs["personal_access_token"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(
        "max.server.api.AzureDevOpsWorkItemPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/ideas/bu-azdo001/publish/azure-devops",
        json={
            "organization": "max-org",
            "project": "Max",
            "personal_access_token": "azdo_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Azure DevOps work item publish failed with HTTP 403" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "azure_devops_work_item"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-azdo001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "HTTP 403" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_azure_devops_live_requires_pat_and_records_failed_attempt(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-azdo001/publish/azure-devops",
        json={
            "organization": "max-org",
            "project": "Max",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "AZURE_DEVOPS_PAT" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "azure_devops_work_item"
    assert detail["publication_attempt"]["status"] == "failure"

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts("bu-azdo001")
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "AZURE_DEVOPS_PAT" in attempts[0]["error"]
    finally:
        store.close()


def test_publish_azure_devops_missing_organization_fails_before_network(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("AZURE_DEVOPS_ORGANIZATION", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-azdo001/publish/azure-devops",
        json={"project": "Max", "personal_access_token": "azdo_pat", "dry_run": False},
    )

    assert response.status_code == 400
    assert "Azure DevOps organization is required" in response.json()["detail"]


def test_publish_azure_devops_missing_project_fails_before_network(
    client,
    db_path,
    monkeypatch,
) -> None:
    _seed_idea(db_path)
    monkeypatch.delenv("AZURE_DEVOPS_PROJECT", raising=False)

    response = client.post(
        "/api/v1/ideas/bu-azdo001/publish/azure-devops",
        json={
            "organization": "max-org",
            "personal_access_token": "azdo_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 400
    assert "Azure DevOps project is required" in response.json()["detail"]


def test_publish_azure_devops_missing_idea(client, monkeypatch) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing ideas should not initialize the Azure DevOps publisher")

    monkeypatch.setattr(
        "max.server.api.AzureDevOpsWorkItemPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/ideas/missing/publish/azure-devops",
        json={"organization": "max-org", "project": "Max"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: missing"


def test_publish_azure_devops_missing_evaluation(client, db_path) -> None:
    _seed_idea(db_path, with_evaluation=False)

    response = client.post(
        "/api/v1/ideas/bu-azdo001/publish/azure-devops",
        json={"organization": "max-org", "project": "Max"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found: bu-azdo001"
