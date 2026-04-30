from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_buyer_faq import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_buyer_faq_detail,
    get_design_brief_buyer_faq,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_buyer_faq import _seed_supported_brief


@pytest.fixture
def mcp_buyer_faq_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_buyer_faq.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_buyer_faq_brief_id(mcp_buyer_faq_db) -> str:
    store = Store(db_path=mcp_buyer_faq_db, wal_mode=True)
    try:
        return _seed_supported_brief(store)
    finally:
        store.close()


def test_get_design_brief_buyer_faq_json(seeded_buyer_faq_brief_id) -> None:
    result = get_design_brief_buyer_faq(seeded_buyer_faq_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.buyer_faq"
    assert result["design_brief"]["id"] == seeded_buyer_faq_brief_id
    assert result["summary"]["buyer"] == "VP of Sales"
    assert result["questions"]
    assert [area["area"] for area in result["concern_areas"]] == [
        "problem_fit",
        "differentiation",
        "implementation_effort",
        "security_compliance",
        "pricing",
        "adoption_risk",
        "proof_points",
    ]
    assert any("Competitor FAQ Tool" in question["answer"] for question in result["questions"])
    assert result["evidence_refs"]


def test_get_design_brief_buyer_faq_markdown(seeded_buyer_faq_brief_id) -> None:
    result = get_design_brief_buyer_faq(seeded_buyer_faq_brief_id, format="markdown")

    assert result["id"] == seeded_buyer_faq_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Buyer FAQ: Buyer FAQ Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Problem Fit" in result["markdown"]
    assert "## Pricing" in result["markdown"]
    assert "Competitor FAQ Tool" in result["markdown"]


def test_get_design_brief_buyer_faq_not_found(mcp_buyer_faq_db) -> None:
    result = get_design_brief_buyer_faq("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_buyer_faq_invalid_format(seeded_buyer_faq_brief_id) -> None:
    result = get_design_brief_buyer_faq(seeded_buyer_faq_brief_id, format="yaml")

    assert result["error"] == "Unsupported buyer FAQ format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_buyer_faq_resource(seeded_buyer_faq_brief_id) -> None:
    result = json.loads(design_brief_buyer_faq_detail(seeded_buyer_faq_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_buyer_faq_brief_id
    assert result["questions"]
    assert result["concern_areas"]


def test_create_mcp_server_registers_buyer_faq_tool(monkeypatch) -> None:
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

    assert "get_design_brief_buyer_faq" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-briefs://{brief_id}/buyer-faq"]
        == "design_brief_buyer_faq_detail"
    )
