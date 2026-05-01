"""Tests for Datadog monitor publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher import DatadogMonitorPublisher as ExportedDatadogMonitorPublisher
from max.publisher.datadog_monitors import (
    DatadogMonitorPublishError,
    DatadogMonitorPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-datadog001",
            "status": "approved",
            "domain": "devtools",
            "category": "observability",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Datadog Monitor Publisher",
            "summary": "Publish implementation-ready specs into Datadog monitors",
            "target_users": "platform teams",
        },
        "problem": {"statement": "Generated specs do not become runtime checks."},
        "solution": {"approach": "Create Datadog monitors through the REST API."},
        "execution": {
            "mvp_scope": ["Monitor payload builder", "Live publisher"],
            "validation_plan": "Publish one approved spec into a Datadog sandbox.",
        },
        "evidence": {
            "rationale": "Teams need operational feedback after handoff.",
            "insight_ids": ["ins-datadog001"],
            "signal_ids": ["sig-datadog001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": ["runtime_risk"],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
        },
    }


def test_dry_run_returns_deterministic_monitor_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = DatadogMonitorPublisher(
        tags=["team platform"],
        notify=["pagerduty-platform", "@slack-observability"],
        client=client,
    )

    first = publisher.publish(_tact_spec(), dry_run=True)
    second = publisher.publish(_tact_spec(), dry_run=True)

    assert first.payload == second.payload
    assert first.dry_run is True
    assert first.status_code is None
    assert first.monitor_id is None
    assert first.monitor_url is None
    assert first.payload["name"] == "[Max] Runtime check: Datadog Monitor Publisher"
    assert first.payload["type"] == "query alert"
    assert (
        first.payload["query"]
        == "avg(last_5m):sum:max.tactspec.runtime_check{service:devtools,source:bu-datadog001} < 1"
    )
    assert first.payload["priority"] == 3
    assert "category:observability" in first.payload["tags"]
    assert "team-platform" in first.payload["tags"]
    assert "@pagerduty-platform" in first.payload["notify"]
    assert "@slack-observability" in first.payload["message"]
    assert first.payload["metadata"]["publisher"] == "max.datadog_monitors"
    assert first.payload["metadata"]["source_id"] == "bu-datadog001"


def test_live_publish_posts_monitor_with_datadog_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": 4242})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = DatadogMonitorPublisher(
        api_key="dd_api_key",
        app_key="dd_app_key",
        site="datadoghq.eu",
        api_url="https://api.datadoghq.eu/",
        tags=["ops"],
        notify=["@team-platform"],
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.monitor_id == "4242"
    assert result.monitor_url == "https://app.datadoghq.eu/monitors/4242"
    assert requests[0].url == "https://api.datadoghq.eu/api/v1/monitor"
    assert requests[0].headers["DD-API-KEY"] == "dd_api_key"
    assert requests[0].headers["DD-APPLICATION-KEY"] == "dd_app_key"
    assert requests[0].headers["User-Agent"] == "max-datadog-monitors-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted["name"] == "[Max] Runtime check: Datadog Monitor Publisher"
    assert posted["type"] == "query alert"
    assert posted["priority"] == 3
    assert posted["options"] == {"include_tags": True, "notify_audit": False}
    assert "metadata" not in posted
    assert result.payload["metadata"]["datadog_monitor_id"] == "4242"


def test_provider_failures_raise_redacted_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text=(
                "bad api_key=dd_api_secret app_key=dd_app_secret "
                "https://api.datadoghq.com/api/v1/monitor?api_key=url_secret&safe=yes"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = DatadogMonitorPublisher(
        api_key="dd_api_secret",
        app_key="dd_app_secret",
        api_url="https://api.datadoghq.com?application_key=site_secret",
        client=client,
    )

    with pytest.raises(DatadogMonitorPublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert exc.value.status_code == 403
    assert "dd_api_secret" not in message
    assert "dd_app_secret" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "api_key=%3Credacted%3E" in message


def test_from_env_reads_datadog_configuration_and_normalizes_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATADOG_API_KEY", "env_api_key")
    monkeypatch.setenv("DATADOG_APP_KEY", "env_app_key")
    monkeypatch.setenv("DATADOG_SITE", "https://api.us3.datadoghq.com/")
    monkeypatch.setenv("DATADOG_TAGS", "ops, team platform")
    monkeypatch.setenv("DATADOG_NOTIFY", "pagerduty-platform, @slack-observability")

    publisher = DatadogMonitorPublisher.from_env()

    assert publisher.api_key == "env_api_key"
    assert publisher.app_key == "env_app_key"
    assert publisher.site == "us3.datadoghq.com"
    assert publisher.api_url == "https://api.us3.datadoghq.com"
    assert publisher.tags == ["ops", "team-platform"]
    assert publisher.notify == ["@pagerduty-platform", "@slack-observability"]

    monkeypatch.setenv("DATADOG_API_URL", "api.datadoghq.eu/api/v1/monitor")
    publisher = DatadogMonitorPublisher.from_env(site="datadoghq.eu")

    assert publisher.site == "datadoghq.eu"
    assert publisher.api_url == "https://api.datadoghq.eu"
    assert publisher.monitor_endpoint == "https://api.datadoghq.eu/api/v1/monitor"


def test_live_publish_requires_keys() -> None:
    publisher = DatadogMonitorPublisher()

    with pytest.raises(DatadogMonitorPublishError, match="DATADOG_API_KEY"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_build_monitor_payload_validates_tact_spec_input() -> None:
    publisher = DatadogMonitorPublisher()

    with pytest.raises(DatadogMonitorPublishError, match="schema_version"):
        publisher.build_monitor_payload({"project": {"title": "Missing schema"}})

    with pytest.raises(DatadogMonitorPublishError, match="project.title"):
        publisher.build_monitor_payload({"schema_version": "tact-spec-preview/v1"})


def test_exported_from_publisher_package() -> None:
    assert ExportedDatadogMonitorPublisher is DatadogMonitorPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
