"""Tests for publishing design briefs to HubSpot deals through the REST API."""

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
    path = str(tmp_path / "test_design_brief_hubspot_api.db")
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
            id="bu-hubspot-brief",
            title="HubSpot Brief Source",
            one_liner="Publish design briefs to HubSpot",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Design briefs are not visible in CRM discovery pipeline.",
            solution="Create a HubSpot deal from the persisted brief.",
            value_proposition="Sales and product can track opportunity discovery.",
            buyer="GTM lead",
            specific_user="Product marketer",
            workflow_context="Discovery pipeline review",
            evidence_rationale="Teams asked for CRM handoff.",
            domain="devtools",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="HubSpot Design Brief",
                domain="devtools",
                theme="crm-handoff",
                lead=Candidate(unit=unit),
                readiness_score=88.0,
                why_this_now="Validated briefs need CRM visibility.",
                merged_product_concept="A HubSpot publisher for Max design briefs.",
                synthesis_rationale="The source idea is ready for GTM discovery.",
                mvp_scope=["Render HubSpot payload", "Create deal"],
                first_milestones=["Ship REST endpoint"],
                validation_plan="Dry run, then publish through a fake transport.",
                risks=["Incorrect HubSpot credentials"],
                source_idea_ids=["bu-hubspot-brief"],
            )
        )
    finally:
        store.close()


def test_publish_design_brief_hubspot_dry_run_returns_payload_without_network(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/hubspot-deal",
        json={
            "pipeline_id": "pipeline-123",
            "deal_stage_id": "stage-456",
            "portal_id": "portal-789",
            "deal_owner_id": "owner-111",
            "amount": "15000",
            "close_date": "2026-05-31",
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["design_brief_id"] == brief_id
    assert data["dry_run"] is True
    assert data["status_code"] is None
    assert data["deal_id"] is None
    assert data["deal_url"] is None
    assert data["attempts"] == []
    assert data["payload"]["properties"]["dealname"] == "[Max] HubSpot Design Brief"
    assert data["payload"]["properties"]["pipeline"] == "pipeline-123"
    assert data["payload"]["properties"]["dealstage"] == "stage-456"
    assert data["payload"]["properties"]["hubspot_owner_id"] == "owner-111"
    assert data["payload"]["properties"]["amount"] == "15000"
    assert data["payload"]["properties"]["closedate"] == "2026-05-31"
    assert "Dry run, then publish through a fake transport." in data["payload"]["properties"]["description"]
    assert data["payload"]["metadata"]["design_brief_id"] == brief_id
    assert data["provider_metadata"]["readiness_score"] == 88.0
    assert data["request_summary"]["access_token"] is None
    assert data["publication_attempt"]["target_type"] == "hubspot_deal"
    assert data["publication_attempt"]["status"] == "success"


def test_publish_design_brief_hubspot_live_success_records_attempt(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "deal-123"})

    def publisher_from_env(**kwargs):
        from max.publisher.hubspot_deals import HubSpotDealPublisher

        return HubSpotDealPublisher(
            access_token=kwargs["access_token"],
            api_url=kwargs["api_url"] or "https://api.hubspot.test",
            pipeline_id=kwargs["pipeline_id"],
            deal_stage_id=kwargs["deal_stage_id"],
            portal_id=kwargs["portal_id"],
            deal_owner_id=kwargs["deal_owner_id"],
            amount=kwargs["amount"],
            close_date=kwargs["close_date"],
            timeout=kwargs["timeout"],
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.HubSpotDealPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/hubspot-deal",
        json={
            "access_token": "hubspot-secret",
            "pipeline_id": "pipeline-123",
            "deal_stage_id": "stage-456",
            "portal_id": "portal-789",
            "amount": 25000,
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["status_code"] == 201
    assert data["deal_id"] == "deal-123"
    assert data["deal_url"] == "https://app.hubspot.com/contacts/portal-789/deal/deal-123"
    assert data["publication_attempt"]["target_url"] == data["deal_url"]
    assert data["publication_attempt"]["status"] == "success"
    assert data["provider_metadata"]["deal_id"] == "deal-123"
    assert data["attempts"] == [
        {
            "method": "POST",
            "url": "https://api.hubspot.test/crm/v3/objects/deals",
            "status_code": 201,
        }
    ]
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer hubspot-secret"
    posted = json.loads(requests[0].read())
    assert posted["properties"]["dealname"] == "[Max] HubSpot Design Brief"
    assert posted["properties"]["pipeline"] == "pipeline-123"
    assert posted["properties"]["dealstage"] == "stage-456"
    assert posted["properties"]["amount"] == "25000"


def test_publish_design_brief_hubspot_missing_brief_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def publisher_from_env(**kwargs):
        raise AssertionError("missing briefs should not initialize the HubSpot publisher")

    monkeypatch.setattr("max.server.api.HubSpotDealPublisher.from_env", publisher_from_env)

    response = client.post(
        "/api/v1/design-briefs/dbf-missing/publish/hubspot-deal",
        json={"pipeline_id": "pipeline-123"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_publish_design_brief_hubspot_live_requires_token_and_records_failure(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/hubspot-deal",
        json={"pipeline_id": "pipeline-123", "dry_run": False},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "HUBSPOT_ACCESS_TOKEN is required" in detail["message"]
    assert detail["publication_attempt"]["target_type"] == "hubspot_deal"
    assert detail["publication_attempt"]["status"] == "failure"


def test_publish_design_brief_hubspot_provider_error_redacts_token(
    client: TestClient,
    db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief_id = _seed_design_brief(db_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad token hubspot-secret"})

    def publisher_from_env(**kwargs):
        from max.publisher.hubspot_deals import HubSpotDealPublisher

        return HubSpotDealPublisher(
            access_token=kwargs["access_token"],
            api_url="https://api.hubspot.test",
            max_retries=kwargs["max_retries"],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr("max.server.api.HubSpotDealPublisher.from_env", publisher_from_env)

    response = client.post(
        f"/api/v1/design-briefs/{brief_id}/publish/hubspot-deal",
        json={"access_token": "hubspot-secret", "dry_run": False},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "hubspot-secret" not in json.dumps(detail)
    assert "Bad token [redacted]" in detail["message"]
    assert detail["publication_attempt"]["status"] == "failure"
    assert detail["publication_attempt"]["response_status"] == 401
