from __future__ import annotations

import json
import shutil

import pytest

from max.analysis.design_brief_migration_plan import SCHEMA_VERSION
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_migration_plan_detail,
    get_design_brief_migration_plan,
    set_store_factory,
)
from max.store.db import Store
from tests.test_design_brief_migration_plan import _store_with_brief


@pytest.fixture
def mcp_migration_plan_db(tmp_path):
    db_path = str(tmp_path / "mcp_migration_plan.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_migration_plan_brief_id(tmp_path, mcp_migration_plan_db) -> str:
    source_store, source_brief_id = _store_with_brief(tmp_path)
    source_store.close()
    shutil.copyfile(tmp_path / "design_brief_migration_plan.db", mcp_migration_plan_db)
    return source_brief_id


def test_get_design_brief_migration_plan_structured(
    seeded_migration_plan_brief_id,
) -> None:
    result = get_design_brief_migration_plan(seeded_migration_plan_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.migration_plan"
    assert result["design_brief"]["id"] == seeded_migration_plan_brief_id
    assert result["design_brief"]["title"] == "Migration Plan Brief"
    assert result["summary"]["phase_count"] == len(result["migration_phases"])
    assert result["data_workflow_migration_steps"]
    assert result["rollback_criteria"]
    assert result["training_touchpoints"]
    assert result["integration_risks"]


def test_get_design_brief_migration_plan_markdown(
    seeded_migration_plan_brief_id,
) -> None:
    result = get_design_brief_migration_plan(
        seeded_migration_plan_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_migration_plan_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Migration Plan: Migration Plan Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Migration Phases" in result["markdown"]
    assert "## Rollback Criteria" in result["markdown"]
    assert "Source idea references: bu-migration-lead, bu-migration-support" in result["markdown"]


def test_get_design_brief_migration_plan_markdown_boolean(
    seeded_migration_plan_brief_id,
) -> None:
    result = get_design_brief_migration_plan(
        seeded_migration_plan_brief_id,
        markdown=True,
    )

    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Migration Plan: Migration Plan Brief")


def test_get_design_brief_migration_plan_missing_brief_returns_mcp_error(
    mcp_migration_plan_db,
) -> None:
    result = get_design_brief_migration_plan("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_migration_plan_invalid_format_returns_mcp_error(
    seeded_migration_plan_brief_id,
) -> None:
    result = get_design_brief_migration_plan(
        seeded_migration_plan_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported migration plan format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_migration_plan_resource(seeded_migration_plan_brief_id) -> None:
    result = json.loads(design_brief_migration_plan_detail(seeded_migration_plan_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_migration_plan_brief_id
    assert result["migration_phases"]


def test_create_mcp_server_registers_migration_plan_tool(monkeypatch) -> None:
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

    assert "get_design_brief_migration_plan" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-migration-plans://{brief_id}"]
        == "design_brief_migration_plan_detail"
    )
