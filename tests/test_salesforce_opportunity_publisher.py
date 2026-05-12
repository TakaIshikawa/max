"""Tests for Salesforce Opportunity publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.salesforce_opportunities import (
    SalesforceOpportunityPublishError,
    SalesforceOpportunityPublisher,
)


def _idea_payload() -> dict:
    return {
        "source": {"idea_id": "bu-sfopp001", "type": "idea"},
        "project": {"title": "Opportunity Publisher", "summary": "Create opportunities from qualified ideas."},
        "problem": {"statement": "Sales teams need qualified handoffs."},
        "solution": {"approach": "Create a Salesforce Opportunity."},
        "evidence": {"rationale": "Pipeline review requested it.", "signal_ids": ["sig-1"]},
        "evaluation": {"overall_score": 86.0, "recommendation": "pursue"},
    }


def _design_brief_payload() -> dict:
    return {
        "design_brief": {
            "id": "dbf-sfopp001",
            "title": "Opportunity Design Brief",
            "summary": "Convert ready briefs into opportunities.",
            "readiness_score": 92.0,
            "recommendation": "ready",
            "source_idea_ids": ["bu-sfopp001"],
            "validation_plan": "Review with sales operations.",
        },
        "evidence_refs": {"insight_ids": ["ins-1"], "signal_ids": ["sig-1"]},
    }


def test_dry_run_maps_idea_to_salesforce_opportunity_fields_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = SalesforceOpportunityPublisher(
        instance_url="https://acme.my.salesforce.com",
        default_stage="Qualification",
        close_date="2026-06-30",
        amount=12500,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.dry_run is True
    assert result.method == "POST"
    assert result.endpoint == "https://acme.my.salesforce.com/services/data/v60.0/sobjects/Opportunity"
    assert result.payload["Name"] == "Opportunity Publisher"
    assert result.payload["StageName"] == "Qualification"
    assert result.payload["CloseDate"] == "2026-06-30"
    assert result.payload["Amount"] == 12500
    assert "Idea ID: bu-sfopp001" in result.payload["Description"]
    assert "Recommendation: pursue" in result.payload["Description"]


def test_dry_run_maps_design_brief_with_readiness_and_evidence_metadata() -> None:
    publisher = SalesforceOpportunityPublisher(
        instance_url="https://acme.my.salesforce.com",
        close_date="2026-06-30",
        external_id_field="Max_Source_Id__c",
    )

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert result.method == "PATCH"
    assert result.endpoint.endswith("/Opportunity/Max_Source_Id__c/dbf-sfopp001")
    assert result.payload["Name"] == "Opportunity Design Brief"
    assert "Brief ID: dbf-sfopp001" in result.payload["Description"]
    assert "Readiness score: 92.0" in result.payload["Description"]
    assert "Insight ids: ins-1" in result.payload["Description"]
    assert "Signal ids: sig-1" in result.payload["Description"]


def test_live_publish_posts_create_request_and_returns_opportunity_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "006xx0000012345AAA", "success": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SalesforceOpportunityPublisher(
        instance_url="acme.my.salesforce.com",
        access_token="sf-token",
        api_version="61.0",
        close_date="2026-06-30",
        client=client,
    )

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 201
    assert result.opportunity_id == "006xx0000012345AAA"
    assert result.opportunity_url == "https://acme.my.salesforce.com/006xx0000012345AAA"
    assert requests[0].method == "POST"
    assert requests[0].headers["Authorization"] == "Bearer sf-token"
    assert json.loads(requests[0].read())["Name"] == "Opportunity Publisher"


def test_live_publish_uses_external_id_upsert() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SalesforceOpportunityPublisher(
        instance_url="https://acme.my.salesforce.com",
        access_token="sf-token",
        close_date="2026-06-30",
        external_id_field="Max_Source_Id__c",
        external_id_value="external-123",
        client=client,
    )

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 204
    assert result.method == "PATCH"
    assert requests[0].method == "PATCH"
    assert str(requests[0].url).endswith("/Opportunity/Max_Source_Id__c/external-123")


def test_live_publish_requires_credentials() -> None:
    publisher = SalesforceOpportunityPublisher(close_date="2026-06-30")

    with pytest.raises(SalesforceOpportunityPublishError, match="SALESFORCE_INSTANCE_URL"):
        publisher.publish(_idea_payload(), dry_run=False)


def test_provider_error_redacts_access_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad access_token=sf-token Authorization=Bearer sf-token")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SalesforceOpportunityPublisher(
        instance_url="https://acme.my.salesforce.com",
        access_token="sf-token",
        close_date="2026-06-30",
        client=client,
    )

    with pytest.raises(SalesforceOpportunityPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 401
    assert "sf-token" not in str(exc.value)
