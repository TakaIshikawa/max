"""Tests for publishing design briefs to Azure DevOps through the REST API."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_azure_devops_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
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


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-azdo-brief",
            title="Azure DevOps Brief Source",
            one_liner="Publish design briefs to Azure DevOps",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs stall before Azure Boards planning.",
            solution="Create an Azure DevOps work item from the persisted brief.",
            value_proposition="Enterprise delivery handoffs land in existing boards.",
            buyer="Product lead",
            specific_user="Engineering manager",
            workflow_context="Execution planning",
            evidence_rationale="Teams requested Azure Boards handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Azure DevOps Design Brief",
                domain="devtools",
                theme="enterprise-handoff",
                lead=Candidate(unit=unit),
                readiness_score=86.0,
                why_this_now="Planning artifacts need direct Azure Boards follow-through.",
                merged_product_concept="An Azure DevOps publisher for design briefs.",
                synthesis_rationale="The source idea is ready for implementation planning.",
                mvp_scope=["Render JSON Patch payload", "Create Azure DevOps work item"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then publish through a fake transport.",
                risks=["Incorrect Azure DevOps credentials"],
                source_idea_ids=["bu-azdo-brief"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_azure_devops_dry_run_returns_payload_without_network(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/azure-devops",
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
    assert data["design_brief_id"] == brief_id
    assert data["organization"] == "max-org"
    assert data["project"] == "Max Project"
    assert data["work_item_type"] == "Product Backlog Item"
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["work_item_id"] is None
    assert data["work_item_url"] is None
    assert data["publication_attempt"] is None
    assert data["payload"]["operations"][0] == {
        "op": "add",
        "path": "/fields/System.Title",
        "value": "[Max] Azure DevOps Design Brief",
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
            "value": "max; devtools; quality-scored; handoff",
        },
    ]
    assert "Dry run, then publish through a fake transport." in data["payload"]["operations"][1]["value"]
    assert data["payload"]["design_brief"]["markdown"].startswith("# Azure DevOps Design Brief")
    assert "Source ideas: `bu-azdo-brief`" in data["payload"]["design_brief"]["markdown"]
    assert data["provider_metadata"]["design_brief_id"] == brief_id
    assert data["provider_metadata"]["source_idea_ids"] == ["bu-azdo-brief"]
    assert data["request_summary"]["personal_access_token"] is None

    store = Store(db_path=db_path, wal_mode=True)
    try:
        assert store.list_publication_attempts(brief_id) == []
    finally:
        store.close()


def test_publish_design_brief_azure_devops_live_success_records_publication_attempt(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": 4242})

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
        f"/api/v1/design-briefs/{brief_id}/publish/azure-devops",
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
    assert data["work_item_id"] == "4242"
    assert data["work_item_url"] == "https://dev.azure.com/max-org/Max%20Project/_workitems/edit/4242"
    assert data["publication_attempt"]["target_type"] == "azure_devops_work_item"
    assert data["publication_attempt"]["target_url"] == data["work_item_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["request_summary"]["personal_access_token"] == "[redacted]"
    assert "azdo_pat" not in json.dumps(data)
    assert len(requests) == 1
    assert json.loads(requests[0].content) == data["payload"]["operations"]

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["target_url"] == data["work_item_url"]
        assert attempts[0]["status"] == "success"
    finally:
        store.close()


def test_publish_design_brief_azure_devops_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the Azure DevOps publisher")

    monkeypatch.setattr(
        "max.server.api.AzureDevOpsWorkItemPublisher.from_env",
        publisher_from_env,
    )

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/azure-devops",
        json={"organization": "max-org", "project": "Max"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_azure_devops_live_requires_pat_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
    monkeypatch.delenv("AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/azure-devops",
        json={"organization": "max-org", "project": "Max", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "AZURE_DEVOPS_PAT" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "azure_devops_work_item"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["request_summary"]["personal_access_token"] is None

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
    finally:
        store.close()


def test_publish_design_brief_azure_devops_provider_failure_redacts_token(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden for azdo_pat"})

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
        f"/api/v1/design-briefs/{brief_id}/publish/azure-devops",
        json={
            "organization": "max-org",
            "project": "Max",
            "personal_access_token": "azdo_pat",
            "dry_run": False,
        },
    )

    assert response.status_code == 502
    raw = response.text
    assert "azdo_pat" not in raw
    detail = response.json()["detail"]
    assert "Azure DevOps work item publish failed with HTTP 403" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "azure_devops_work_item"
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 403

    store = Store(db_path=db_path, wal_mode=True)
    try:
        attempts = store.list_publication_attempts(brief_id)
        assert len(attempts) == 1
        assert attempts[0]["status"] == "failure"
        assert "azdo_pat" not in attempts[0]["error"]
    finally:
        store.close()
