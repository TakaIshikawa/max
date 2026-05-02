from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_unit_economics import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_unit_economics_detail,
    get_design_brief_unit_economics,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_unit_economics import _store_with_unit_economics_brief


@pytest.fixture
def mcp_unit_economics_db(tmp_path):
    store, brief_id = _store_with_unit_economics_brief(tmp_path)
    db_path = str(tmp_path / "design_brief_unit_economics_False.db")
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path, brief_id
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_unit_economics_brief_id(mcp_unit_economics_db) -> str:
    _db_path, brief_id = mcp_unit_economics_db
    return brief_id


def test_get_design_brief_unit_economics_json(seeded_unit_economics_brief_id) -> None:
    result = get_design_brief_unit_economics(seeded_unit_economics_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.unit_economics"
    assert result["source"]["entity_type"] == "design_brief"
    assert result["source"]["id"] == seeded_unit_economics_brief_id
    assert result["design_brief"]["id"] == seeded_unit_economics_brief_id
    assert result["design_brief"]["buyer"] == "VP of Customer Operations"
    assert result["summary"]["expected_payback_months"] > 0
    assert result["revenue_model"]["target_monthly_price_band_usd"]["low"] > 0
    assert result["payback_bands"]["gross_margin_band"]
    assert result["validation_questions"]


def test_get_design_brief_unit_economics_markdown(
    seeded_unit_economics_brief_id,
) -> None:
    result = get_design_brief_unit_economics(
        seeded_unit_economics_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_unit_economics_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Unit Economics: Unit Economics Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert f"Design brief: `{seeded_unit_economics_brief_id}`" in result["markdown"]
    assert "## Revenue Model" in result["markdown"]
    assert "## Payback Bands" in result["markdown"]
    assert "bu-unit-econ-lead" in result["markdown"]


def test_get_design_brief_unit_economics_not_found(mcp_unit_economics_db) -> None:
    result = get_design_brief_unit_economics("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_unit_economics_invalid_format(
    seeded_unit_economics_brief_id,
) -> None:
    result = get_design_brief_unit_economics(
        seeded_unit_economics_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported unit economics format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_unit_economics_resource(seeded_unit_economics_brief_id) -> None:
    result = json.loads(design_brief_unit_economics_detail(seeded_unit_economics_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_unit_economics_brief_id
    assert result["summary"]["expected_payback_months"] > 0
    assert result["gross_margin_risk_notes"]


def test_create_mcp_server_registers_unit_economics_tool(monkeypatch) -> None:
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

    assert "get_design_brief_unit_economics" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-unit-economics://{brief_id}"]
        == "design_brief_unit_economics_detail"
    )
