"""Tests for MCP customer discovery script access."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.server.dependencies import get_store
from max.server.mcp_tools import (
    create_mcp_server,
    customer_discovery_script_detail,
    get_customer_discovery_script,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.signal import Signal, SignalSourceType


def _seed_customer_discovery_idea(db_path: str) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-cd-mcp",
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title="Manual onboarding pain",
                content="RevOps teams lose deals during manual onboarding handoffs.",
                url="https://example.com/manual-onboarding",
                credibility=0.8,
            )
        )
        store.insert_buildable_unit(
            BuildableUnit(
                id="bu-cd-mcp",
                title="Onboarding Handoff Tracker",
                one_liner="Track revenue onboarding handoffs",
                category=BuildableCategory.APPLICATION,
                problem="customer onboarding handoffs stall after sales close",
                solution="a shared handoff tracker with owner prompts",
                value_proposition="reduce delayed onboarding and churn risk",
                specific_user="revops manager",
                buyer="VP Customer Success",
                workflow_context="post-sale customer onboarding",
                current_workaround="CRM notes and weekly status meetings",
                evidence_signals=["sig-cd-mcp"],
            )
        )
        store.create_validation_experiment(
            "bu-cd-mcp",
            hypothesis="revops managers will share stalled handoff examples in interviews",
            method="problem interviews",
            target_sample_size=6,
            success_metric="4 of 6 describe a recent stalled handoff",
        )
    finally:
        store.close()


def _client(db_path: str) -> TestClient:
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_mcp_customer_discovery_tool_matches_rest_top_level_fields(tmp_path) -> None:
    db_path = str(tmp_path / "customer-discovery-mcp.db")
    _seed_customer_discovery_idea(db_path)
    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    try:
        mcp_payload = get_customer_discovery_script("bu-cd-mcp")
        rest_payload = _client(db_path).get(
            "/api/v1/ideas/bu-cd-mcp/customer-discovery-script"
        ).json()
    finally:
        set_store_factory(lambda: Store(wal_mode=True))

    assert set(mcp_payload) == set(rest_payload)
    assert mcp_payload["idea_id"] == "bu-cd-mcp"
    assert mcp_payload["sections"]["screening"]["questions"]
    assert mcp_payload["sections"]["interview"]["demo_prompts"]
    assert mcp_payload["sections"]["follow_up"]["artifacts"]
    assert any(
        "revops manager" in profile
        for profile in mcp_payload["target_respondent_profiles"]
    )
    assert any(
        "revops managers will share stalled handoff examples" in question["prompt"]
        for question in mcp_payload["disconfirming_questions"]
    )


def test_mcp_customer_discovery_resource_returns_valid_json(tmp_path) -> None:
    db_path = str(tmp_path / "customer-discovery-resource.db")
    _seed_customer_discovery_idea(db_path)
    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    try:
        payload = json.loads(customer_discovery_script_detail("bu-cd-mcp"))
    finally:
        set_store_factory(lambda: Store(wal_mode=True))

    assert payload["idea_id"] == "bu-cd-mcp"
    assert payload["sections"]["interview"]["questions"]


def test_mcp_customer_discovery_missing_idea_returns_not_found_error(tmp_path) -> None:
    db_path = str(tmp_path / "customer-discovery-missing.db")
    Store(db_path=db_path, wal_mode=True).close()
    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    try:
        payload = get_customer_discovery_script("missing")
    finally:
        set_store_factory(lambda: Store(wal_mode=True))

    assert payload["error"] == "Idea not found: missing"
    assert payload["code"] == 404
    assert payload["details"]["resource_type"] == "buildable_unit"
    assert payload["details"]["resource_id"] == "missing"


def test_create_mcp_server_registers_customer_discovery_tool_and_resource(
    monkeypatch,
) -> None:
    class FakeMCP:
        latest = None

        def __init__(self, name):
            self.name = name
            self.tools = []
            self.resources = {}
            FakeMCP.latest = self

        def tool(self, fn):
            self.tools.append(fn.__name__)
            return fn

        def resource(self, uri):
            def decorator(fn):
                self.resources[uri] = fn.__name__
                return fn

            return decorator

    monkeypatch.setattr("max.server.mcp_tools.FastMCP", FakeMCP)

    create_mcp_server()

    assert "get_customer_discovery_script" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["ideas://{idea_id}/customer-discovery-script"]
        == "customer_discovery_script_detail"
    )
