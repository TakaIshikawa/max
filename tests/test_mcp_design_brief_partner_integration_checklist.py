from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_partner_integration_checklist import (
    KIND,
    SCHEMA_VERSION,
)
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_partner_integration_checklist_detail,
    get_design_brief_partner_integration_checklist,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_partner_integration_checklist import _store_with_brief


@pytest.fixture
def seeded_partner_integration_checklist_brief_id(tmp_path) -> str:
    db_path = str(tmp_path / "partner_integration.db")
    store, brief_id = _store_with_brief(tmp_path)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield brief_id
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def mcp_partner_integration_checklist_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_partner_integration_checklist.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def test_get_design_brief_partner_integration_checklist_json(
    seeded_partner_integration_checklist_brief_id,
) -> None:
    result = get_design_brief_partner_integration_checklist(
        seeded_partner_integration_checklist_brief_id
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert result["design_brief"]["id"] == seeded_partner_integration_checklist_brief_id
    assert result["design_brief"]["title"] == "Partner Integration Brief"
    assert result["summary"]["target_user"] == "customer success operator"
    assert result["summary"]["buyer"] == "customer success director"
    assert [target["id"] for target in result["integration_targets"]] == [
        "core_product",
        "salesforce_crm",
        "slack",
        "postgres",
        "oauth_sso",
        "webhook_api",
    ]
    assert result["data_contracts"]
    assert result["auth_and_security_checks"]
    assert result["operational_readiness"]
    assert result["partner_owner_matrix"]
    assert result["sequencing"]
    assert result["readiness_warnings"] == []


def test_get_design_brief_partner_integration_checklist_markdown(
    seeded_partner_integration_checklist_brief_id,
) -> None:
    result = get_design_brief_partner_integration_checklist(
        seeded_partner_integration_checklist_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_partner_integration_checklist_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith(
        "# Partner Integration Checklist: Partner Integration Brief"
    )
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Integration Targets" in result["markdown"]
    assert "## Data Contracts" in result["markdown"]
    assert "## Auth and Security Checks" in result["markdown"]
    assert "## Operational Readiness" in result["markdown"]


def test_get_design_brief_partner_integration_checklist_not_found(
    mcp_partner_integration_checklist_db,
) -> None:
    result = get_design_brief_partner_integration_checklist("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_partner_integration_checklist_invalid_format(
    seeded_partner_integration_checklist_brief_id,
) -> None:
    result = get_design_brief_partner_integration_checklist(
        seeded_partner_integration_checklist_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported partner integration checklist format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_partner_integration_checklist_resource(
    seeded_partner_integration_checklist_brief_id,
) -> None:
    result = json.loads(
        design_brief_partner_integration_checklist_detail(
            seeded_partner_integration_checklist_brief_id
        )
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_partner_integration_checklist_brief_id
    assert result["integration_targets"]
    assert result["partner_owner_matrix"]


def test_create_mcp_server_registers_partner_integration_checklist_tool(
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

    assert "get_design_brief_partner_integration_checklist" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources[
            "design-brief-partner-integration-checklist://{brief_id}"
        ]
        == "design_brief_partner_integration_checklist_detail"
    )
