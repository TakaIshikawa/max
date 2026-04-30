"""Tests for HubSpot deal publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import HubSpotDealPublisher as ExportedHubSpotDealPublisher
from max.publisher.hubspot_deals import HubSpotDealPublishError, HubSpotDealPublisher


def _design_brief() -> dict:
    return {
        "id": "dbf-hubspot001",
        "title": "HubSpot Deal Brief",
        "domain": "devtools",
        "theme": "crm-handoff",
        "lead_idea_id": "bu-lead",
        "source_idea_ids": ["bu-lead", "bu-supporting", "bu-lead"],
        "readiness_score": 87.5,
        "design_status": "ready",
        "merged_product_concept": "Publish validated briefs into CRM.",
        "why_this_now": "Go-to-market teams need discovery pipeline visibility.",
        "mvp_scope": ["Map deal properties", "Create deal"],
        "validation_plan": "Dry-run payloads before live CRM publishing.",
        "created_at": "2026-04-22T00:00:00+00:00",
        "updated_at": "2026-04-23T00:00:00+00:00",
    }


def test_build_design_brief_payload_maps_hubspot_properties() -> None:
    publisher = HubSpotDealPublisher(
        pipeline_id="pipeline-123",
        deal_stage_id="stage-456",
        portal_id="portal-789",
        deal_owner_id="owner-111",
        amount=12000,
        close_date="2026-05-31",
    )

    payload = publisher.build_design_brief_payload(
        _design_brief(),
        markdown="# HubSpot Deal Brief\n\nBrief markdown",
    ).to_dict()

    assert payload["properties"]["dealname"] == "[Max] HubSpot Deal Brief"
    assert payload["properties"]["pipeline"] == "pipeline-123"
    assert payload["properties"]["dealstage"] == "stage-456"
    assert payload["properties"]["hubspot_owner_id"] == "owner-111"
    assert payload["properties"]["amount"] == "12000"
    assert payload["properties"]["closedate"] == "2026-05-31"
    assert "dbf-hubspot001" in payload["properties"]["description"]
    assert "Brief markdown" in payload["properties"]["description"]
    assert payload["metadata"]["publisher"] == "max.hubspot_deals"
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["source_idea_ids"] == ["bu-lead", "bu-supporting"]


def test_dry_run_returns_payload_without_token_or_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = HubSpotDealPublisher(pipeline_id="pipeline-123", deal_stage_id="stage-456", client=client)

    result = publisher.publish_design_brief(
        _design_brief(),
        markdown="# HubSpot Deal Brief",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.status_code is None
    assert result.deal_id is None
    assert result.deal_url is None
    assert result.attempts == []
    assert result.payload["properties"]["pipeline"] == "pipeline-123"


def test_live_publish_posts_deal_and_returns_attempts_and_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": "deal-123",
                "properties": {"dealname": "[Max] HubSpot Deal Brief"},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = HubSpotDealPublisher(
        access_token="hubspot-secret",
        api_url="https://api.hubspot.test",
        pipeline_id="pipeline-123",
        deal_stage_id="stage-456",
        portal_id="portal-789",
        client=client,
    )

    result = publisher.publish_design_brief(
        _design_brief(),
        markdown="# HubSpot Deal Brief",
        dry_run=False,
    )

    assert result.status_code == 201
    assert result.deal_id == "deal-123"
    assert result.deal_url == "https://app.hubspot.com/contacts/portal-789/deal/deal-123"
    assert result.attempts == [
        {
            "method": "POST",
            "url": "https://api.hubspot.test/crm/v3/objects/deals",
            "status_code": 201,
        }
    ]
    assert requests[0].headers["Authorization"] == "Bearer hubspot-secret"
    posted = json.loads(requests[0].read())
    assert posted["properties"]["dealname"] == "[Max] HubSpot Deal Brief"
    assert posted["properties"]["pipeline"] == "pipeline-123"
    assert posted["properties"]["dealstage"] == "stage-456"
    assert result.payload["metadata"]["hubspot_deal_id"] == "deal-123"


def test_live_publish_requires_access_token() -> None:
    publisher = HubSpotDealPublisher()

    with pytest.raises(HubSpotDealPublishError, match="HUBSPOT_ACCESS_TOKEN"):
        publisher.publish_design_brief(_design_brief(), markdown="# Brief", dry_run=False)


def test_live_publish_retries_transient_status_and_redacts_error() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"message": "slow down"})
        return httpx.Response(401, json={"message": "Bad token hubspot-secret"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = HubSpotDealPublisher(
        access_token="hubspot-secret",
        api_url="https://user:password@api.hubspot.test?token=hubspot-secret",
        max_retries=1,
        client=client,
    )

    with pytest.raises(HubSpotDealPublishError) as exc:
        publisher.publish_design_brief(_design_brief(), markdown="# Brief", dry_run=False)

    message = str(exc.value)
    assert "hubspot-secret" not in message
    assert "password" not in json.dumps(exc.value.attempts)
    assert "Bad token [redacted]" in message
    assert exc.value.status_code == 401
    assert exc.value.attempts == [
        {
            "method": "POST",
            "url": "https://***@api.hubspot.test/crm/v3/objects/deals",
            "status_code": 429,
        },
        {
            "method": "POST",
            "url": "https://***@api.hubspot.test/crm/v3/objects/deals",
            "status_code": 401,
        },
    ]


def test_from_env_reads_hubspot_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("HUBSPOT_DEAL_PIPELINE_ID", "env-pipeline")
    monkeypatch.setenv("HUBSPOT_DEAL_STAGE_ID", "env-stage")
    monkeypatch.setenv("HUBSPOT_PORTAL_ID", "env-portal")

    publisher = HubSpotDealPublisher.from_env()

    assert publisher.access_token == "env-token"
    assert publisher.pipeline_id == "env-pipeline"
    assert publisher.deal_stage_id == "env-stage"
    assert publisher.portal_id == "env-portal"


def test_publisher_is_exported_from_package() -> None:
    assert ExportedHubSpotDealPublisher is HubSpotDealPublisher
