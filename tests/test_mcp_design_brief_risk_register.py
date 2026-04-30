from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_risk_register import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_risk_register_detail,
    get_design_brief_risk_register,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_risk_register import _seed_brief


@pytest.fixture
def mcp_risk_register_db(tmp_path):
    db_path = str(tmp_path / "mcp_risk_register.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_risk_register_brief_id(mcp_risk_register_db) -> str:
    store = Store(db_path=mcp_risk_register_db, wal_mode=True)
    try:
        return _seed_brief(store)
    finally:
        store.close()


def test_get_design_brief_risk_register_structured(
    seeded_risk_register_brief_id,
) -> None:
    result = get_design_brief_risk_register(seeded_risk_register_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_risk_register_brief_id
    assert result["design_brief"]["title"] == "Risk Register Brief"
    assert result["summary"]["risk_count"] == len(result["risks"])
    assert result["risks"]

    adapter_risk = next(
        risk
        for risk in result["risks"]
        if risk["description"] == "Framework adapters may change quickly"
    )
    assert adapter_risk["severity"] == "high"
    assert adapter_risk["mitigation"]
    assert adapter_risk["validation_action"]
    assert adapter_risk["source_idea_ids"] == ["bu-risk-lead", "bu-risk-support"]

    stable_fields = {
        "id",
        "category",
        "title",
        "description",
        "severity",
        "likelihood",
        "priority",
        "source_idea_ids",
        "source_fields",
        "mitigation",
        "validation_action",
    }
    assert stable_fields <= set(adapter_risk)


def test_get_design_brief_risk_register_markdown_boolean(
    seeded_risk_register_brief_id,
) -> None:
    result = get_design_brief_risk_register(
        seeded_risk_register_brief_id,
        markdown=True,
    )

    assert result["id"] == seeded_risk_register_brief_id
    assert result["format"] == "markdown"
    assert "# Risk Register: Risk Register Brief" in result["markdown"]
    assert "Schema: `max.design_brief.risk_register.v1`" in result["markdown"]
    assert "- Severity: high" in result["markdown"]
    assert "- Mitigation:" in result["markdown"]
    assert "- Validation action:" in result["markdown"]


def test_get_design_brief_risk_register_missing_brief_returns_mcp_error(
    mcp_risk_register_db,
) -> None:
    result = get_design_brief_risk_register("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_risk_register_invalid_format_returns_mcp_error(
    seeded_risk_register_brief_id,
) -> None:
    result = get_design_brief_risk_register(
        seeded_risk_register_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported risk register format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_risk_register_resource(seeded_risk_register_brief_id) -> None:
    result = json.loads(design_brief_risk_register_detail(seeded_risk_register_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_risk_register_brief_id
    assert result["risks"]


def test_create_mcp_server_registers_risk_register_tool(monkeypatch) -> None:
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

    assert "get_design_brief_risk_register" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-risk-registers://{brief_id}"]
        == "design_brief_risk_register_detail"
    )
