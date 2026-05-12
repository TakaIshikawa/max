from __future__ import annotations

import httpx
import json
import pytest

from max.publisher.gainsight_timeline_activities import GainsightTimelineActivityPublishError, GainsightTimelineActivityPublisher


def _unit() -> dict:
    return {
        "source": {"idea_id": "bu-gs001", "status": "approved", "category": "customer-success"},
        "project": {"title": "Gainsight Timeline Activity Publisher", "summary": "Create customer success activity context."},
        "problem": {"statement": "CSMs need approved Max idea context in their account timeline."},
        "solution": {"approach": "Create a structured timeline activity from the buildable unit."},
        "execution": {"validation_plan": "Confirm CSMs can find the Max context during account review."},
        "evaluation": {"overall_score": 91.5},
    }


def test_builds_company_activity_payload() -> None:
    publisher = GainsightTimelineActivityPublisher(company_id="company-123", activity_type="Product Feedback")

    payload = publisher.build_activity_payload(_unit()).to_dict()

    assert payload == {
        "target_type": "company",
        "target_id": "company-123",
        "activity_type": "Product Feedback",
        "subject": "Max idea: Gainsight Timeline Activity Publisher",
        "body": {
            "title": "Gainsight Timeline Activity Publisher",
            "category": "customer-success",
            "problem": "CSMs need approved Max idea context in their account timeline.",
            "solution": "Create a structured timeline activity from the buildable unit.",
            "validation_plan": "Confirm CSMs can find the Max context during account review.",
            "score": "91.5",
            "metadata": {
                "publisher": "max.gainsight_timeline_activities",
                "idea_id": "bu-gs001",
                "status": "approved",
                "category": "customer-success",
                "score": "91.5",
                "target_type": "company",
                "target_id": "company-123",
            },
        },
        "metadata": {
            "publisher": "max.gainsight_timeline_activities",
            "idea_id": "bu-gs001",
            "status": "approved",
            "category": "customer-success",
            "score": "91.5",
            "target_type": "company",
            "target_id": "company-123",
        },
    }


def test_builds_relationship_request_payload_with_subject_override() -> None:
    publisher = GainsightTimelineActivityPublisher(relationship_id="rel-456", subject="Review Max idea")

    payload = publisher.build_activity_payload(_unit()).to_request_json()

    assert payload["relationshipId"] == "rel-456"
    assert "companyId" not in payload
    assert payload["subject"] == "Review Max idea"
    assert payload["type"] == "Update"
    assert payload["body"]["metadata"]["target_type"] == "relationship"


def test_from_env_reads_gainsight_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAINSIGHT_API_TOKEN", "gs_env")
    monkeypatch.setenv("GAINSIGHT_API_URL", "https://gainsight.example.test")
    monkeypatch.setenv("GAINSIGHT_COMPANY_ID", "company-env")
    monkeypatch.setenv("GAINSIGHT_ACTIVITY_TYPE", "Milestone")

    publisher = GainsightTimelineActivityPublisher.from_env()

    assert publisher.token == "gs_env"
    assert publisher.api_url == "https://gainsight.example.test"
    assert publisher.company_id == "company-env"
    assert publisher.activity_type == "Milestone"


def test_dry_run_returns_endpoint_and_payload_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = GainsightTimelineActivityPublisher(
        company_id="company-123",
        api_url="https://gainsight.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://gainsight.example.test/v1/timeline/activities"
    assert result.target_type == "company"
    assert result.payload["body"]["metadata"]["idea_id"] == "bu-gs001"


def test_live_publish_posts_activity_and_parses_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"data": {"id": "activity-789"}})

    publisher = GainsightTimelineActivityPublisher(
        token="gs_secret",
        relationship_id="rel-456",
        api_url="https://gainsight.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False, subject="Account timeline update")

    assert result.status_code == 201
    assert result.activity_id == "activity-789"
    assert result.response == {"data": {"id": "activity-789"}}
    assert requests[0].url == "https://gainsight.example.test/v1/timeline/activities"
    assert requests[0].headers["Authorization"] == "Bearer gs_secret"
    posted = json.loads(requests[0].read().decode())
    assert posted["relationshipId"] == "rel-456"
    assert posted["subject"] == "Account timeline update"
    assert posted["body"]["title"] == "Gainsight Timeline Activity Publisher"


def test_missing_target_is_actionable() -> None:
    publisher = GainsightTimelineActivityPublisher(token="gs_secret")

    with pytest.raises(GainsightTimelineActivityPublishError, match="company_id or relationship_id"):
        publisher.publish(_unit(), dry_run=True)


def test_rejects_ambiguous_targets() -> None:
    publisher = GainsightTimelineActivityPublisher(company_id="company-123", relationship_id="rel-456")

    with pytest.raises(GainsightTimelineActivityPublishError, match="exactly one target"):
        publisher.publish(_unit(), dry_run=True)


def test_live_publish_requires_token() -> None:
    publisher = GainsightTimelineActivityPublisher(company_id="company-123")

    with pytest.raises(GainsightTimelineActivityPublishError, match="GAINSIGHT_API_TOKEN"):
        publisher.publish(_unit(), dry_run=False)


def test_retryable_failure_retries_and_redacts_token() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="temporarily unavailable gs_secret")

    publisher = GainsightTimelineActivityPublisher(
        token="gs_secret",
        company_id="company-123",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(GainsightTimelineActivityPublishError, match="HTTP 503") as exc:
        publisher.publish(_unit(), dry_run=False)

    assert calls == 3
    assert exc.value.status_code == 503
    assert "gs_secret" not in str(exc.value)
