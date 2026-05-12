from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.statuspage_component_status import (
    StatuspageComponentStatusPublishError,
    StatuspageComponentStatusPublisher,
)


def test_dry_run_builds_component_status_payload() -> None:
    publisher = StatuspageComponentStatusPublisher(
        page_id="page123",
        component_id="component123",
        status="degraded_performance",
        name="API",
        description="Public API",
        only_show_if_degraded=True,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("dry run should not make network calls")))),
    )

    result = publisher.publish(dry_run=True)

    assert result.status_code is None
    assert result.dry_run is True
    assert result.endpoint == "https://api.statuspage.io/v1/pages/page123/components/component123"
    assert result.payload == {
        "page_id": "page123",
        "component_id": "component123",
        "status": "degraded_performance",
        "name": "API",
        "description": "Public API",
        "only_show_if_degraded": True,
    }


def test_validates_allowed_component_statuses() -> None:
    with pytest.raises(StatuspageComponentStatusPublishError, match="must be one of"):
        StatuspageComponentStatusPublisher(status="broken")

    publisher = StatuspageComponentStatusPublisher(page_id="page123", component_id="component123")
    with pytest.raises(StatuspageComponentStatusPublishError, match="component status is required"):
        publisher.publish(dry_run=True)


def test_live_publish_patches_component_and_returns_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"component": {"id": "component123", "status": "major_outage"}})

    publisher = StatuspageComponentStatusPublisher(
        page_id="page123",
        component_id="component123",
        status="major_outage",
        api_key="sp-secret",
        api_url="https://statuspage.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(dry_run=False)

    assert result.status_code == 200
    assert result.component_id == "component123"
    assert result.response == {"component": {"id": "component123", "status": "major_outage"}}
    assert requests[0].method == "PATCH"
    assert requests[0].url == "https://statuspage.example.test/v1/pages/page123/components/component123"
    assert requests[0].headers["Authorization"] == "OAuth sp-secret"
    assert json.loads(requests[0].read()) == {"component": {"status": "major_outage"}}


def test_from_env_reads_statuspage_component_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATUSPAGE_API_KEY", "env-key")
    monkeypatch.setenv("STATUSPAGE_PAGE_ID", "page-env")
    monkeypatch.setenv("STATUSPAGE_COMPONENT_ID", "component-env")
    monkeypatch.setenv("STATUSPAGE_COMPONENT_STATUS", "operational")
    monkeypatch.setenv("STATUSPAGE_COMPONENT_NAME", "Env API")
    monkeypatch.setenv("STATUSPAGE_COMPONENT_DESCRIPTION", "Env description")
    monkeypatch.setenv("STATUSPAGE_ONLY_SHOW_IF_DEGRADED", "true")

    publisher = StatuspageComponentStatusPublisher.from_env()

    assert publisher.api_key == "env-key"
    assert publisher.page_id == "page-env"
    assert publisher.component_id == "component-env"
    assert publisher.status == "operational"
    assert publisher.name == "Env API"
    assert publisher.description == "Env description"
    assert publisher.only_show_if_degraded is True


def test_live_publish_requires_api_key() -> None:
    publisher = StatuspageComponentStatusPublisher(
        page_id="page123",
        component_id="component123",
        status="operational",
    )

    with pytest.raises(StatuspageComponentStatusPublishError, match="STATUSPAGE_API_KEY"):
        publisher.publish(dry_run=False)


def test_error_redacts_secret_and_includes_status() -> None:
    publisher = StatuspageComponentStatusPublisher(
        page_id="page123",
        component_id="component123",
        status="operational",
        api_key="sp-secret",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(401, text="bad sp-secret"))
        ),
    )

    with pytest.raises(StatuspageComponentStatusPublishError, match="HTTP 401") as exc:
        publisher.publish(dry_run=False)

    assert exc.value.status_code == 401
    assert "sp-secret" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)
