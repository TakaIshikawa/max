from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_pricing_strategy import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_pricing_strategy_detail,
    get_design_brief_pricing_strategy,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_pricing_strategy import _seed_pricing_brief


@pytest.fixture
def mcp_pricing_strategy_db(tmp_path):
    db_path = str(tmp_path / "mcp_pricing_strategy.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_pricing_strategy_brief_id(mcp_pricing_strategy_db) -> str:
    store = Store(db_path=mcp_pricing_strategy_db, wal_mode=True)
    try:
        return _seed_pricing_brief(store)
    finally:
        store.close()


def test_get_design_brief_pricing_strategy_json(seeded_pricing_strategy_brief_id) -> None:
    result = get_design_brief_pricing_strategy(seeded_pricing_strategy_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_pricing_strategy_brief_id
    assert result["design_brief"]["buyer"] == "VP of Engineering"
    assert [package["name"] for package in result["packages"]] == [
        "Starter",
        "Team",
        "Business",
    ]
    assert result["price_bands"]
    assert result["value_metric"]["metric"] == "completed workflow runs"
    assert result["evidence_references"]


def test_get_design_brief_pricing_strategy_markdown(seeded_pricing_strategy_brief_id) -> None:
    result = get_design_brief_pricing_strategy(
        seeded_pricing_strategy_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_pricing_strategy_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Pricing Strategy: Agent Pricing Guard Brief")
    assert "Schema: `max.design_brief.pricing_strategy.v1`" in result["markdown"]
    assert "## Recommended Packaging" in result["markdown"]
    assert "## Initial Price Bands" in result["markdown"]


def test_get_design_brief_pricing_strategy_not_found(mcp_pricing_strategy_db) -> None:
    result = get_design_brief_pricing_strategy("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_pricing_strategy_invalid_format(
    seeded_pricing_strategy_brief_id,
) -> None:
    result = get_design_brief_pricing_strategy(
        seeded_pricing_strategy_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported pricing strategy format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_pricing_strategy_resource(seeded_pricing_strategy_brief_id) -> None:
    result = json.loads(design_brief_pricing_strategy_detail(seeded_pricing_strategy_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_pricing_strategy_brief_id
    assert result["packages"]
    assert result["price_bands"]


def test_create_mcp_server_registers_pricing_strategy_tool(monkeypatch) -> None:
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

    assert "get_design_brief_pricing_strategy" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-pricing-strategies://{brief_id}"]
        == "design_brief_pricing_strategy_detail"
    )
