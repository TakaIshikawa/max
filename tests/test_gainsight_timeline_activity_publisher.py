from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.gainsight_timeline_activities import GainsightTimelineActivityPublishError, GainsightTimelineActivityPublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_builds_company_activity_payload_with_max_context() -> None:
    publisher = GainsightTimelineActivityPublisher(company_id="company-1", activity_type="Lifecycle")

    result = publisher.publish(_unit(), dry_run=True)

    assert result.endpoint == "https://api.gainsight.com/v1/timeline/activities"
    assert result.payload["company_id"] == "company-1"
    assert result.payload["relationship_id"] is None
    assert result.payload["activity_type"] == "Lifecycle"
    assert "Problem: Billing teams need approved idea context." in result.payload["body"]
    assert result.payload["metadata"]["publisher"] == "max.gainsight_timeline_activities"


def test_builds_relationship_activity_payload_and_rejects_missing_target() -> None:
    publisher = GainsightTimelineActivityPublisher(relationship_id="rel-1")

    assert publisher.build_activity_payload(_unit()).relationship_id == "rel-1"

    with pytest.raises(GainsightTimelineActivityPublishError, match="company_id or relationship_id"):
        GainsightTimelineActivityPublisher().publish(_unit(), dry_run=True)


def test_from_env_reads_gainsight_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAINSIGHT_API_TOKEN", "gain-token")
    monkeypatch.setenv("GAINSIGHT_API_URL", "https://gainsight.example.test")
    monkeypatch.setenv("GAINSIGHT_COMPANY_ID", "company-env")

    publisher = GainsightTimelineActivityPublisher.from_env(timeout=2.5, max_retries=3)

    assert publisher.token == "gain-token"
    assert publisher.api_url == "https://gainsight.example.test"
    assert publisher.company_id == "company-env"
    assert publisher.timeout == 2.5
    assert publisher.max_retries == 3


def test_live_publish_posts_activity_and_returns_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"activity": {"id": "act-1"}})

    publisher = GainsightTimelineActivityPublisher(
        token="gain-token",
        company_id="company-1",
        api_url="https://gainsight.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False)

    assert result.activity_id == "act-1"
    assert requests[0].headers["Authorization"] == "Bearer gain-token"
    assert json.loads(requests[0].read())["companyId"] == "company-1"


def test_gainsight_retry_failure_exposes_status_code() -> None:
    publisher = GainsightTimelineActivityPublisher(
        token="gain-token",
        company_id="company-1",
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable gain-token"))),
    )

    with pytest.raises(GainsightTimelineActivityPublishError) as exc:
        publisher.publish(_unit(), dry_run=False)

    assert exc.value.status_code == 503
    assert "gain-token" not in str(exc.value)
