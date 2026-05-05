"""Tests for Opsgenie alert publishing."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from max.publisher import OpsgenieAlertPublisher as ExportedOpsgenieAlertPublisher
from max.publisher.opsgenie_alerts import (
    OpsgenieAlertPublishError,
    OpsgenieAlertPublisher,
)


def _design_brief_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": "dbf-opsgenie001",
            "idea_id": "bu-opsgenie001",
            "status": "approved",
            "domain": "operations",
            "category": "alerting",
            "url": "https://max.example.test/design-briefs/dbf-opsgenie001",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Opsgenie Alert Publisher",
            "summary": "Route generated launch handoffs into alert response workflows.",
            "target_users": "SRE teams",
        },
        "problem": {"statement": "Generated launch risks do not page accountable teams."},
        "solution": {"approach": "Create Opsgenie alerts from approved design briefs."},
        "execution": {
            "mvp_scope": ["Alert payload builder", "Live publisher"],
            "validation_plan": "Publish one approved design brief into an Opsgenie sandbox.",
        },
        "evidence": {
            "rationale": "Launch risks need responder ownership before release.",
            "insight_ids": ["ins-opsgenie001"],
            "signal_ids": ["sig-opsgenie001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": ["handoff_risk"],
        },
        "evaluation": {
            "overall_score": 86.0,
            "recommendation": "yes",
        },
    }


def _design_brief_packet() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-opsgenie-brief",
            "title": "Opsgenie Launch Handoff",
            "domain": "operations",
            "theme": "alerting",
            "lead_idea_id": "bu-lead",
            "source_idea_ids": ["bu-lead", "bu-supporting", "bu-lead"],
            "readiness_score": 88.5,
            "design_status": "ready",
            "merged_product_concept": "Publish validated design briefs into Opsgenie.",
            "validation_plan": "Create one sandbox alert.",
        },
        "source_ideas": [
            {
                "id": "bu-lead",
                "role": "lead",
                "problem": "SRE handoffs lose launch context.",
                "solution": "Map persisted briefs into Opsgenie alerts.",
            }
        ],
    }


def test_dry_run_returns_deterministic_alert_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = OpsgenieAlertPublisher(
        api_key="opsgenie_key",
        priority="P2",
        tags=["Launch Risk", "platform"],
        responders=[{"type": "team", "name": "Platform Ops"}],
        details={"runbook_url": "https://runbooks.example.test/max"},
        client=client,
    )

    first = publisher.publish(_design_brief_tact_spec(), dry_run=True)
    second = publisher.publish(_design_brief_tact_spec(), dry_run=True)

    assert first.payload == second.payload
    assert first.dry_run is True
    assert first.status_code is None
    assert first.request_id is None
    assert first.alert_id is None
    assert first.alias == "max:design-brief:dbf-opsgenie001"
    assert first.payload["message"] == "[Max] Opsgenie Alert Publisher"
    assert first.payload["priority"] == "P2"
    assert first.payload["tags"] == [
        "max",
        "tact-spec",
        "publisher:opsgenie",
        "source_type:design-brief",
        "source_system:max",
        "domain:operations",
        "category:alerting",
        "status:approved",
        "recommendation:yes",
        "quality:handoff-risk",
        "launch-risk",
        "platform",
    ]
    assert first.payload["responders"] == [{"type": "team", "name": "Platform Ops"}]
    assert first.payload["entity"] == "max/design-brief/dbf-opsgenie001"
    assert first.payload["source"] == "max/design-brief/dbf-opsgenie001"
    assert first.payload["details"]["source_url"] == (
        "https://max.example.test/design-briefs/dbf-opsgenie001"
    )
    assert first.payload["details"]["runbook_url"] == "https://runbooks.example.test/max"
    assert first.payload["details"]["max_metadata"]["publisher"] == "max.opsgenie_alerts"
    assert "Publish one approved design brief" in first.payload["description"]
    assert first.payload["metadata"]["source_type"] == "design_brief"
    assert first.payload["metadata"]["source_id"] == "dbf-opsgenie001"


def test_build_design_brief_payload_maps_persisted_brief_fields() -> None:
    publisher = OpsgenieAlertPublisher(priority="p4", responders=["On Call"])

    payload = publisher.build_design_brief_payload(
        _design_brief_packet(),
        markdown="# Opsgenie Launch Handoff",
    ).to_dict()

    assert payload["message"] == "[Max] Opsgenie Launch Handoff"
    assert payload["alias"] == "max:design-brief:dbf-opsgenie-brief"
    assert payload["priority"] == "P4"
    assert payload["responders"] == [{"name": "On Call", "type": "team"}]
    assert payload["tags"] == [
        "max",
        "design-brief",
        "publisher:opsgenie",
        "domain:operations",
        "theme:alerting",
        "status:ready",
    ]
    assert payload["details"]["source_idea_ids"] == ["bu-lead", "bu-supporting"]
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["design_brief_id"] == "dbf-opsgenie-brief"
    assert "SRE handoffs lose launch context." in payload["description"]
    assert "Map persisted briefs into Opsgenie alerts." in payload["description"]
    assert "# Opsgenie Launch Handoff" in payload["description"]


def test_live_publish_posts_alert_with_geniekey_and_configurable_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            202,
            json={
                "result": "Request will be processed",
                "requestId": "req-123",
                "alertId": "alert-456",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = OpsgenieAlertPublisher(
        api_key="opsgenie_key",
        api_url="https://api.eu.opsgenie.com/v2/alerts",
        message="Custom launch alert",
        description="Custom description",
        alias="custom-alias",
        priority="P1",
        tags=["custom"],
        responders=[{"type": "user", "username": "sre@example.test"}],
        entity="max://brief/dbf-opsgenie001",
        source="max://ops",
        details={"owner": "SRE"},
        client=client,
    )

    result = publisher.publish(_design_brief_tact_spec(), dry_run=False)

    assert result.status_code == 202
    assert result.request_id == "req-123"
    assert result.alert_id == "alert-456"
    assert result.alias == "custom-alias"
    assert requests[0].url == "https://api.eu.opsgenie.com/v2/alerts"
    assert requests[0].headers["Authorization"] == "GenieKey opsgenie_key"
    assert requests[0].headers["User-Agent"] == "max-opsgenie-alerts-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted == {
        "message": "Custom launch alert",
        "alias": "custom-alias",
        "description": "Custom description",
        "priority": "P1",
        "tags": [
            "max",
            "tact-spec",
            "publisher:opsgenie",
            "source_type:design-brief",
            "source_system:max",
            "domain:operations",
            "category:alerting",
            "status:approved",
            "recommendation:yes",
            "quality:handoff-risk",
            "custom",
        ],
        "details": {
            "project_title": "Opsgenie Alert Publisher",
            "project_summary": "Route generated launch handoffs into alert response workflows.",
            "problem": "Generated launch risks do not page accountable teams.",
            "approach": "Create Opsgenie alerts from approved design briefs.",
            "validation_plan": "Publish one approved design brief into an Opsgenie sandbox.",
            "mvp_scope": '["Alert payload builder", "Live publisher"]',
            "recommendation": "yes",
            "overall_score": "86.0",
            "quality_score": "8.0",
            "rejection_tags": '["handoff_risk"]',
            "rationale": "Launch risks need responder ownership before release.",
            "insight_ids": '["ins-opsgenie001"]',
            "signal_ids": '["sig-opsgenie001"]',
            "source_url": "https://max.example.test/design-briefs/dbf-opsgenie001",
            "max_metadata": (
                '{"design_brief_id": "dbf-opsgenie001", "idea_id": "bu-opsgenie001", '
                '"kind": "tact.project_spec", "priority": "P1", '
                '"publisher": "max.opsgenie_alerts", '
                '"schema_version": "tact-spec-preview/v1", "source_id": "dbf-opsgenie001", '
                '"source_system": "max", "source_type": "design_brief"}'
            ),
            "owner": "SRE",
        },
        "responders": [{"type": "user", "username": "sre@example.test"}],
        "entity": "max://brief/dbf-opsgenie001",
        "source": "max://ops",
    }
    assert result.payload["metadata"]["opsgenie_request_id"] == "req-123"
    assert result.payload["metadata"]["opsgenie_alert_id"] == "alert-456"
    assert result.payload["metadata"]["opsgenie_alert_alias"] == "custom-alias"


def test_from_env_reads_opsgenie_configuration_and_normalizes_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPSGENIE_API_KEY", "env-api-key")
    monkeypatch.setenv("OPSGENIE_API_URL", "api.eu.opsgenie.com/v2/alerts")
    monkeypatch.setenv("OPSGENIE_ALERT_MESSAGE", "Env message")
    monkeypatch.setenv("OPSGENIE_ALERT_DESCRIPTION", "Env description")
    monkeypatch.setenv("OPSGENIE_ALERT_PRIORITY", "p5")
    monkeypatch.setenv("OPSGENIE_ALERT_TAGS", "env-one, env-two")
    monkeypatch.setenv("OPSGENIE_ALERT_RESPONDERS", "Env Team, Backup Team")
    monkeypatch.setenv("OPSGENIE_ALERT_ALIAS", "env-alias")
    monkeypatch.setenv("OPSGENIE_ALERT_ENTITY", "env-entity")
    monkeypatch.setenv("OPSGENIE_ALERT_SOURCE", "env-source")

    publisher = OpsgenieAlertPublisher.from_env()

    assert publisher.api_key == "env-api-key"
    assert publisher.api_url == "https://api.eu.opsgenie.com"
    assert publisher.alerts_endpoint == "https://api.eu.opsgenie.com/v2/alerts"
    assert publisher.message == "Env message"
    assert publisher.description == "Env description"
    assert publisher.priority == "P5"
    assert publisher.tags == ["env-one", "env-two"]
    assert publisher.responders == [
        {"name": "Env Team", "type": "team"},
        {"name": "Backup Team", "type": "team"},
    ]
    assert publisher.alias == "env-alias"
    assert publisher.entity == "env-entity"
    assert publisher.source == "env-source"


def test_live_publish_requires_api_key() -> None:
    publisher = OpsgenieAlertPublisher()

    with pytest.raises(OpsgenieAlertPublishError, match="OPSGENIE_API_KEY"):
        publisher.publish(_design_brief_tact_spec(), dry_run=False)


def test_provider_failures_and_validation_raise_actionable_errors() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                403,
                text=(
                    "bad api_key=opsgenie_secret "
                    "https://api.opsgenie.com/v2/alerts?api_key=url_secret"
                ),
            )
        )
    )
    publisher = OpsgenieAlertPublisher(
        api_key="opsgenie_secret",
        api_url="https://api.opsgenie.com?genieKey=site_secret",
        client=client,
    )

    with pytest.raises(OpsgenieAlertPublishError, match="HTTP 403") as exc:
        publisher.publish(_design_brief_tact_spec(), dry_run=False)

    assert exc.value.status_code == 403
    assert "opsgenie_secret" not in str(exc.value)
    assert "url_secret" not in str(exc.value)
    assert "site_secret" not in str(exc.value)
    assert "api_key=%3Credacted%3E" in str(exc.value)

    with pytest.raises(OpsgenieAlertPublishError, match="schema_version"):
        OpsgenieAlertPublisher().build_alert_payload({"project": {"title": "Missing schema"}})

    with pytest.raises(OpsgenieAlertPublishError, match="project.title"):
        OpsgenieAlertPublisher().build_alert_payload({"schema_version": "tact-spec-preview/v1"})

    with pytest.raises(OpsgenieAlertPublishError, match="priority"):
        OpsgenieAlertPublisher(priority="critical")

    with pytest.raises(OpsgenieAlertPublishError, match="details"):
        invalid_details: Any = ["not", "a", "dict"]
        OpsgenieAlertPublisher(details=invalid_details)

    with pytest.raises(OpsgenieAlertPublishError, match="design_brief.title"):
        OpsgenieAlertPublisher().build_design_brief_payload({"design_brief": {}})


def test_exported_from_publisher_package() -> None:
    assert ExportedOpsgenieAlertPublisher is OpsgenieAlertPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
