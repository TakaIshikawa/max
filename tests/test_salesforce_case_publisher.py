"""Tests for Salesforce Case publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import SalesforceCasePublisher as ExportedSalesforceCasePublisher
from max.publisher.salesforce_cases import (
    SalesforceCasePublishError,
    SalesforceCasePublisher,
)


def _design_brief_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": "dbf-salesforce001",
            "idea_id": "bu-salesforce001",
            "status": "approved",
            "domain": "commercial",
            "category": "customer-operations",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Customer Operations Case Handoff",
            "summary": "Turn validated design briefs into commercial follow-up cases.",
            "target_users": "customer operations teams",
        },
        "problem": {
            "statement": "Validated design briefs do not reach the customer operations queue."
        },
        "solution": {"approach": "Create Salesforce Cases for approved design briefs."},
        "execution": {
            "mvp_scope": ["Case payload builder", "Salesforce sandbox publisher"],
            "validation_plan": "Publish one approved design brief into a Salesforce sandbox.",
        },
        "evidence": {
            "rationale": "Commercial teams need structured follow-up tasks.",
            "insight_ids": ["ins-salesforce001"],
            "signal_ids": ["sig-salesforce001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
        },
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
        },
    }


def test_dry_run_returns_deterministic_case_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SalesforceCasePublisher(
        origin="Web",
        priority="High",
        status="New",
        account_id="001xx000003DGbYAAW",
        contact_id="003xx000004TmiQAAS",
        client=client,
    )

    first = publisher.publish(_design_brief_tact_spec(), dry_run=True)
    second = publisher.publish(_design_brief_tact_spec(), dry_run=True)

    assert first.payload == second.payload
    assert first.dry_run is True
    assert first.status_code is None
    assert first.case_id is None
    assert first.case_url is None
    assert first.payload["Subject"] == "[Max] Customer ops handoff: Customer Operations Case Handoff"
    assert first.payload["Origin"] == "Web"
    assert first.payload["Priority"] == "High"
    assert first.payload["Status"] == "New"
    assert first.payload["AccountId"] == "001xx000003DGbYAAW"
    assert first.payload["ContactId"] == "003xx000004TmiQAAS"
    assert "Commercial Handoff" in first.payload["Description"]
    assert "Salesforce Cases for approved design briefs" in first.payload["Description"]
    assert first.payload["metadata"]["publisher"] == "max.salesforce_cases"
    assert first.payload["metadata"]["source_type"] == "design_brief"
    assert first.payload["metadata"]["source_id"] == "dbf-salesforce001"
    assert first.payload["metadata"]["design_brief_id"] == "dbf-salesforce001"


def test_live_publish_posts_case_with_bearer_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "500xx0000012345AAA", "success": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SalesforceCasePublisher(
        instance_url="https://acme.my.salesforce.com/",
        access_token="sf_access_token",
        api_version="v61.0",
        origin="Email",
        priority="Medium",
        status="New",
        account_id="001xx000003DGbYAAW",
        client=client,
    )

    result = publisher.publish(_design_brief_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.case_id == "500xx0000012345AAA"
    assert result.case_url == "https://acme.my.salesforce.com/500xx0000012345AAA"
    assert (
        requests[0].url
        == "https://acme.my.salesforce.com/services/data/v61.0/sobjects/Case"
    )
    assert requests[0].headers["Authorization"] == "Bearer sf_access_token"
    assert requests[0].headers["User-Agent"] == "max-salesforce-cases-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted["Subject"] == "[Max] Customer ops handoff: Customer Operations Case Handoff"
    assert posted["Origin"] == "Email"
    assert posted["Priority"] == "Medium"
    assert posted["Status"] == "New"
    assert posted["AccountId"] == "001xx000003DGbYAAW"
    assert "metadata" not in posted
    assert result.payload["metadata"]["salesforce_case_id"] == "500xx0000012345AAA"


def test_live_publish_allows_success_without_case_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SalesforceCasePublisher(
        instance_url="acme.my.salesforce.com",
        access_token="sf_access_token",
        client=client,
    )

    result = publisher.publish(_design_brief_tact_spec(), dry_run=False)

    assert result.status_code == 204
    assert result.case_id is None
    assert result.case_url is None


def test_provider_failures_raise_redacted_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text=(
                "bad access_token=sf_secret Authorization=Bearer sf_secret "
                "https://acme.my.salesforce.com/services/data/v60.0/sobjects/Case?"
                "access_token=url_secret&safe=yes"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = SalesforceCasePublisher(
        instance_url="https://acme.my.salesforce.com?access_token=site_secret",
        access_token="sf_secret",
        client=client,
    )

    with pytest.raises(SalesforceCasePublishError) as exc:
        publisher.publish(_design_brief_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert exc.value.status_code == 401
    assert "sf_secret" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "access_token=%3Credacted%3E" in message


def test_from_env_reads_salesforce_configuration_and_normalizes_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALESFORCE_INSTANCE_URL", "acme.my.salesforce.com/services/data/v60.0")
    monkeypatch.setenv("SALESFORCE_ACCESS_TOKEN", "env_access_token")
    monkeypatch.setenv("SALESFORCE_API_VERSION", "61.0")
    monkeypatch.setenv("SALESFORCE_CASE_ORIGIN", "Phone")
    monkeypatch.setenv("SALESFORCE_CASE_PRIORITY", "High")
    monkeypatch.setenv("SALESFORCE_CASE_STATUS", "Working")
    monkeypatch.setenv("SALESFORCE_ACCOUNT_ID", "001xx000003DGbYAAW")
    monkeypatch.setenv("SALESFORCE_CONTACT_ID", "003xx000004TmiQAAS")

    publisher = SalesforceCasePublisher.from_env()

    assert publisher.instance_url == "https://acme.my.salesforce.com"
    assert publisher.access_token == "env_access_token"
    assert publisher.api_version == "v61.0"
    assert publisher.origin == "Phone"
    assert publisher.priority == "High"
    assert publisher.status == "Working"
    assert publisher.account_id == "001xx000003DGbYAAW"
    assert publisher.contact_id == "003xx000004TmiQAAS"
    assert (
        publisher.case_endpoint
        == "https://acme.my.salesforce.com/services/data/v61.0/sobjects/Case"
    )


def test_live_publish_requires_credentials() -> None:
    publisher = SalesforceCasePublisher()

    with pytest.raises(SalesforceCasePublishError, match="SALESFORCE_INSTANCE_URL"):
        publisher.publish(_design_brief_tact_spec(), dry_run=False)


def test_build_case_payload_validates_tact_spec_input() -> None:
    publisher = SalesforceCasePublisher()

    with pytest.raises(SalesforceCasePublishError, match="schema_version"):
        publisher.build_case_payload({"project": {"title": "Missing schema"}})

    with pytest.raises(SalesforceCasePublishError, match="project.title"):
        publisher.build_case_payload({"schema_version": "tact-spec-preview/v1"})


def test_exported_from_publisher_package() -> None:
    assert ExportedSalesforceCasePublisher is SalesforceCasePublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
