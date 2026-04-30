"""Tests for Airtable record publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import AirtableRecordPublisher as ExportedAirtableRecordPublisher
from max.publisher.airtable_records import AirtableRecordPublishError, AirtableRecordPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-airtable001",
            "status": "approved",
            "domain": "design-tools",
            "category": "application",
        },
        "project": {
            "title": "Airtable Design Brief Handoff",
            "summary": "Publish design brief ideas into research operations tables.",
            "target_users": "design leads",
        },
        "problem": {"statement": "Design teams track briefs outside engineering systems."},
        "solution": {"approach": "Create Airtable records from Max payloads."},
        "execution": {"validation_plan": "Dry-run records before creating them."},
        "evidence": {"source_idea_ids": ["bu-lead", "bu-supporting", "bu-lead"]},
        "quality": {
            "quality_score": 8.5,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
        },
        "evaluation": {"recommendation": "yes", "overall_score": 84.0},
    }


def _design_brief_packet() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-airtable001",
            "title": "Airtable Research Brief",
            "domain": "design-tools",
            "theme": "research-ops",
            "lead_idea_id": "bu-lead",
            "source_idea_ids": ["bu-lead", "bu-supporting", "bu-lead"],
            "readiness_score": 91.5,
            "design_status": "ready",
            "merged_product_concept": "Publish validated design briefs into Airtable.",
            "validation_plan": "Create one sandbox Airtable record.",
        },
        "source_ideas": [
            {
                "id": "bu-lead",
                "role": "lead",
                "problem": "Research databases lose design brief context.",
                "solution": "Map persisted briefs into Airtable fields.",
            }
        ],
    }


def test_build_idea_payload_maps_tact_spec_to_airtable_fields() -> None:
    publisher = AirtableRecordPublisher("app123", "Design Briefs")

    payload = publisher.build_idea_payload(_tact_spec()).to_dict()

    assert payload["fields"] == {
        "Record Type": "Idea",
        "Title": "Airtable Design Brief Handoff",
        "Source ID": "bu-airtable001",
        "Source Type": "idea",
        "Status": "approved",
        "Domain": "design-tools",
        "Category": "application",
        "Summary": "Publish design brief ideas into research operations tables.",
        "Problem": "Design teams track briefs outside engineering systems.",
        "Solution": "Create Airtable records from Max payloads.",
        "Target Users": "design leads",
        "Validation Plan": "Dry-run records before creating them.",
        "Recommendation": "yes",
        "Overall Score": 84.0,
        "Quality Score": 8.5,
        "Novelty Score": 7,
        "Usefulness Score": 9,
        "Source Idea IDs": "bu-lead, bu-supporting",
    }
    assert payload["metadata"]["publisher"] == "max.airtable_records"
    assert payload["metadata"]["idea_id"] == "bu-airtable001"


def test_build_design_brief_payload_maps_persisted_brief_fields() -> None:
    publisher = AirtableRecordPublisher("app123", "Design Briefs")

    payload = publisher.build_design_brief_payload(
        _design_brief_packet(),
        markdown="# Airtable Research Brief",
    ).to_dict()

    assert payload["fields"]["Record Type"] == "Design Brief"
    assert payload["fields"]["Title"] == "Airtable Research Brief"
    assert payload["fields"]["Source ID"] == "dbf-airtable001"
    assert payload["fields"]["Status"] == "ready"
    assert payload["fields"]["Theme"] == "research-ops"
    assert payload["fields"]["Problem"] == "Research databases lose design brief context."
    assert payload["fields"]["Solution"] == "Map persisted briefs into Airtable fields."
    assert payload["fields"]["Source Idea IDs"] == "bu-lead, bu-supporting"
    assert payload["fields"]["Readiness Score"] == 91.5
    assert payload["fields"]["Markdown"] == "# Airtable Research Brief"
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["design_brief_id"] == "dbf-airtable001"


def test_dry_run_returns_payload_without_api_key_or_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AirtableRecordPublisher("app123", "Design Briefs", client=client)

    result = publisher.publish_design_brief(
        _design_brief_packet(),
        markdown="# Airtable Research Brief",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.status_code is None
    assert result.record_id is None
    assert result.record_url is None
    assert result.attempts == []
    assert result.payload["fields"]["Source ID"] == "dbf-airtable001"


def test_live_publish_posts_authenticated_airtable_record() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "rec123",
                "createdTime": "2026-04-30T00:00:00.000Z",
                "fields": {"Title": "Airtable Research Brief"},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AirtableRecordPublisher(
        "app123",
        "Design Briefs",
        api_key="airtable-secret",
        api_url="https://api.airtable.test",
        client=client,
    )

    result = publisher.publish_design_brief(
        _design_brief_packet(),
        markdown="# Airtable Research Brief",
        dry_run=False,
    )

    assert result.status_code == 200
    assert result.record_id == "rec123"
    assert result.record_url == "https://airtable.com/app123/Design%20Briefs/rec123"
    assert result.attempts == [
        {
            "method": "POST",
            "url": "https://api.airtable.test/v0/app123/Design%20Briefs",
            "status_code": 200,
        }
    ]
    assert len(requests) == 1
    assert requests[0].url.raw_path == b"/v0/app123/Design%20Briefs"
    assert requests[0].headers["Authorization"] == "Bearer airtable-secret"
    assert requests[0].headers["Content-Type"] == "application/json"
    posted = json.loads(requests[0].read())
    assert posted == {"fields": result.payload["fields"]}
    assert result.payload["metadata"]["airtable_record_id"] == "rec123"


def test_live_publish_requires_api_key() -> None:
    publisher = AirtableRecordPublisher("app123", "Design Briefs")

    with pytest.raises(AirtableRecordPublishError, match="AIRTABLE_API_KEY"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_non_success_response_raises_with_status_and_redacts_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"error": {"message": "Bad api_key airtable-secret"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AirtableRecordPublisher(
        "app123",
        "Design Briefs",
        api_key="airtable-secret",
        client=client,
    )

    with pytest.raises(AirtableRecordPublishError, match="HTTP 422") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 422
    assert "airtable-secret" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)


def test_from_env_requires_base_and_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRTABLE_BASE_ID", raising=False)
    monkeypatch.delenv("AIRTABLE_TABLE", raising=False)
    monkeypatch.delenv("AIRTABLE_TABLE_ID", raising=False)

    with pytest.raises(AirtableRecordPublishError, match="base_id is required"):
        AirtableRecordPublisher.from_env(table="Design Briefs")

    with pytest.raises(AirtableRecordPublishError, match="table is required"):
        AirtableRecordPublisher.from_env(base_id="app123")


def test_from_env_reads_airtable_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRTABLE_BASE_ID", "app-env")
    monkeypatch.setenv("AIRTABLE_TABLE", "Briefs")
    monkeypatch.setenv("AIRTABLE_API_KEY", "key-env")

    publisher = AirtableRecordPublisher.from_env()

    assert publisher.base_id == "app-env"
    assert publisher.table == "Briefs"
    assert publisher.api_key == "key-env"


def test_publisher_is_exported_from_package() -> None:
    assert ExportedAirtableRecordPublisher is AirtableRecordPublisher
