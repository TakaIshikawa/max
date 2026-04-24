from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_evidence_matrix import CLAIM_AREAS, SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_evidence_matrix_detail,
    get_design_brief_evidence_matrix,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_evidence_matrix_db(tmp_path):
    db_path = str(tmp_path / "mcp_evidence_matrix.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_evidence_matrix_brief_id(mcp_evidence_matrix_db) -> str:
    store = Store(db_path=mcp_evidence_matrix_db, wal_mode=True)
    try:
        for signal in [
            _signal("sig-mcp-matrix-problem", "hackernews", "problem"),
            _signal(
                "sig-mcp-matrix-market",
                "stackoverflow_survey",
                "market",
                SignalSourceType.SURVEY,
            ),
            _signal("sig-mcp-matrix-risk", "nvd_cve", "risk", SignalSourceType.SECURITY),
        ]:
            store.insert_signal(signal)

        store.insert_insight(
            Insight(
                id="ins-mcp-matrix-gap",
                category=InsightCategory.GAP,
                title="Release evidence gap",
                summary="Teams need repeatable evidence before agent workflow releases.",
                evidence=["sig-mcp-matrix-problem", "sig-mcp-matrix-market"],
                confidence=0.84,
                domains=["developer-tools"],
            )
        )

        unit = BuildableUnit(
            id="bu-mcp-matrix",
            title="Agent Evidence Matrix",
            one_liner="Evidence-backed release checks for agent workflows",
            category="application",
            problem="Platform teams cannot prove agent workflow safety before release.",
            solution="Run CI workflow fixtures and publish claim evidence.",
            value_proposition="Reduce unsafe agent releases.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="agent release approval",
            current_workaround="manual prompt testing",
            why_now="Agents are moving into production workflows.",
            validation_plan="Interview platform teams and run a smoke-test pilot.",
            first_10_customers="agent framework maintainers; platform teams",
            domain_risks=["Framework adapters may change quickly."],
            evidence_rationale="Signals show repeated workflow safety gaps.",
            inspiring_insights=["ins-mcp-matrix-gap"],
            evidence_signals=["sig-mcp-matrix-risk"],
            tech_approach="Python service with workflow fixtures",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(unit)

        return store.insert_design_brief(
            ProjectBrief(
                title="Agent Evidence Matrix",
                domain="developer-tools",
                theme="agent-release-safety",
                lead=Candidate(unit=unit),
                readiness_score=87.0,
                why_this_now="Agents are moving into production workflows.",
                merged_product_concept="A CI evidence matrix for agent workflow safety.",
                synthesis_rationale="Problem, market, and risk signals support this brief.",
                mvp_scope=["Fixture runner", "Evidence matrix endpoint"],
                first_milestones=["Run fixtures in CI", "Publish evidence matrix"],
                validation_plan="Interview platform teams and run a smoke-test pilot.",
                risks=["Framework churn could break adapters."],
                source_idea_ids=[unit.id],
            )
        )
    finally:
        store.close()


def _signal(
    signal_id: str,
    adapter: str,
    role: str,
    source_type: SignalSourceType = SignalSourceType.FORUM,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"{role.title()} signal",
        content=f"Persisted {role} evidence",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.8,
        metadata={"signal_role": role},
    )


def test_get_design_brief_evidence_matrix_json(seeded_evidence_matrix_brief_id) -> None:
    result = get_design_brief_evidence_matrix(seeded_evidence_matrix_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_evidence_matrix_brief_id
    assert [row["claim_area"] for row in result["rows"]] == list(CLAIM_AREAS)
    problem = next(row for row in result["rows"] if row["claim_area"] == "problem")
    assert problem["supporting_signal_ids"] == ["sig-mcp-matrix-problem"]
    assert problem["validation_actions"]


def test_get_design_brief_evidence_matrix_markdown(seeded_evidence_matrix_brief_id) -> None:
    result = get_design_brief_evidence_matrix(
        seeded_evidence_matrix_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_evidence_matrix_brief_id
    assert result["format"] == "markdown"
    assert "# Evidence Matrix: Agent Evidence Matrix" in result["markdown"]
    assert "## problem" in result["markdown"]
    assert "### Validation Actions" in result["markdown"]
    assert "- Run problem interviews with the primary user profile." in result["markdown"]


def test_get_design_brief_evidence_matrix_not_found(mcp_evidence_matrix_db) -> None:
    result = get_design_brief_evidence_matrix("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_evidence_matrix_invalid_format(seeded_evidence_matrix_brief_id) -> None:
    result = get_design_brief_evidence_matrix(seeded_evidence_matrix_brief_id, format="yaml")

    assert result["error"] == "Unsupported evidence matrix format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_evidence_matrix_resource(seeded_evidence_matrix_brief_id) -> None:
    result = json.loads(design_brief_evidence_matrix_detail(seeded_evidence_matrix_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_evidence_matrix_brief_id
    assert result["rows"]


def test_create_mcp_server_registers_evidence_matrix_tool(monkeypatch) -> None:
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

    assert "get_design_brief_evidence_matrix" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-evidence-matrices://{brief_id}"]
        == "design_brief_evidence_matrix_detail"
    )
