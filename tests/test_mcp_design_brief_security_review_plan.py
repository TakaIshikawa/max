from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_security_review_plan import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_security_review_plan_detail,
    get_design_brief_security_review_plan,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_security_review_plan import _seed_security_brief


@pytest.fixture
def mcp_security_review_plan_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_security_review_plan.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_security_review_plan_brief_id(mcp_security_review_plan_db) -> str:
    store = Store(db_path=mcp_security_review_plan_db, wal_mode=True)
    try:
        return _seed_security_brief(store)
    finally:
        store.close()


def test_get_design_brief_security_review_plan_json(
    seeded_security_review_plan_brief_id,
) -> None:
    result = get_design_brief_security_review_plan(seeded_security_review_plan_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.security_review_plan"
    assert result["design_brief"]["id"] == seeded_security_review_plan_brief_id
    assert result["summary"]["risk_count"] >= 4
    assert {area["id"] for area in result["review_areas"]} == {
        "threat_model_scope",
        "sensitive_data",
        "integration_risks",
        "abuse_cases",
        "evidence_gaps",
    }
    assert any(item["name"] == "OAuth tokens" for item in result["sensitive_data"])
    assert any(item["name"] == "GitHub" for item in result["integration_risks"])
    assert any("least privilege" in item["mitigation"] for item in result["abuse_cases"])
    assert {ref["id"] for ref in result["evidence_references"]} == {
        "ins-security-review",
        "sig-security-review",
    }
    integration_area = next(
        area for area in result["review_areas"] if area["id"] == "integration_risks"
    )
    assert integration_area["section"] == "integration_risks"
    assert integration_area["risk_ids"]
    assert integration_area["check_ids"]
    assert integration_area["evidence_reference_ids"] == [
        "ins-security-review",
        "sig-security-review",
    ]


def test_get_design_brief_security_review_plan_markdown(
    seeded_security_review_plan_brief_id,
) -> None:
    result = get_design_brief_security_review_plan(
        seeded_security_review_plan_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_security_review_plan_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Security Review Plan: Security Review Plan Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Review Scope" in result["markdown"]
    assert "### Integration Risks" in result["markdown"]
    assert "## Evidence Gaps" in result["markdown"]


def test_get_design_brief_security_review_plan_not_found(
    mcp_security_review_plan_db,
) -> None:
    result = get_design_brief_security_review_plan("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_security_review_plan_invalid_format(
    seeded_security_review_plan_brief_id,
) -> None:
    result = get_design_brief_security_review_plan(
        seeded_security_review_plan_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported security review plan format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_security_review_plan_resource(
    seeded_security_review_plan_brief_id,
) -> None:
    result = json.loads(
        design_brief_security_review_plan_detail(seeded_security_review_plan_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_security_review_plan_brief_id
    assert result["review_areas"]
    assert result["evidence_references"]


def test_create_mcp_server_registers_security_review_plan_tool(monkeypatch) -> None:
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

    assert "get_design_brief_security_review_plan" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-security-review-plan://{brief_id}"]
        == "design_brief_security_review_plan_detail"
    )
