from __future__ import annotations

from unittest.mock import patch

import pytest

from max.profiles.schema import ArchitectureConstraintsConfig, DomainContext, PipelineProfile
from max.server import mcp_tools
from max.server.mcp_tools import (
    create_mcp_server,
    get_architecture_enforcement_report,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def _profile(
    *,
    name: str = "architecture",
    domain: str = "architecture",
) -> PipelineProfile:
    return PipelineProfile(
        name=name,
        domain=DomainContext(
            name=domain,
            description="Architecture test profile",
            categories=["cli_tool"],
            target_user_types=["humans"],
        ),
        architecture_constraints=ArchitectureConstraintsConfig(
            allowed_categories=["cli_tool"],
            allowed_target_users=["humans"],
            required_stack_decisions=["language"],
        ),
    )


def _unit(
    unit_id: str,
    *,
    domain: str = "architecture",
    category: str = "cli_tool",
    target_users: str = "humans",
    suggested_stack: dict | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="Architecture idea",
        category=category,
        problem="Problem",
        solution="Solution",
        target_users=target_users,
        value_proposition="Value",
        tech_approach="Ship a local CLI backed by Python.",
        suggested_stack=suggested_stack or {},
        domain=domain,
    )


@pytest.fixture
def mcp_arch_db(tmp_path):
    db_path = str(tmp_path / "mcp_architecture.db")
    with Store(db_path=db_path, wal_mode=True):
        pass

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def test_get_architecture_enforcement_report_returns_api_shaped_report(mcp_arch_db) -> None:
    with Store(db_path=mcp_arch_db, wal_mode=True) as store:
        store.insert_buildable_unit(
            _unit(
                "bu-arch-missing-language",
                suggested_stack={"runtime": "local"},
            )
        )
        store.insert_buildable_unit(
            _unit(
                "bu-other-domain",
                domain="other",
                category="application",
                target_users="agents",
            )
        )

    with patch("max.profiles.loader.load_profile", return_value=_profile()):
        result = get_architecture_enforcement_report(domain="architecture", limit=5)

    assert result["profile_name"] == "architecture"
    assert result["domain"] == "architecture"
    assert result["unit_limit"] == 5
    assert result["units_analyzed"] == 1
    assert result["constraints_configured"] is True
    assert result["assessments"][0]["idea_id"] == "bu-arch-missing-language"
    assert "missing_stack_decision" in {finding["code"] for finding in result["findings"]}
    assert set(result) >= {
        "generated_at",
        "categories_allowed",
        "target_users_allowed",
        "evaluation_weights",
        "recommended_constraint_additions",
        "status",
    }


def test_get_architecture_enforcement_report_returns_structured_mcp_errors(
    mcp_arch_db,
) -> None:
    invalid = get_architecture_enforcement_report(domain="architecture", limit=0)

    assert invalid["error"] == "limit must be between 1 and 10000"
    assert invalid["code"] == 400
    assert invalid["details"]["field"] == "limit"

    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        missing = get_architecture_enforcement_report(domain="missing")

    assert missing["error"] == "Profile not found: missing"
    assert missing["code"] == 404
    assert missing["details"]["resource_type"] == "profile"
    assert missing["details"]["resource_id"] == "missing"


def test_create_mcp_server_registers_architecture_enforcement_tool(monkeypatch) -> None:
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

    monkeypatch.setattr(mcp_tools, "FastMCP", FakeMCP)

    create_mcp_server()

    assert "get_architecture_enforcement_report" in FakeMCP.latest.tools
