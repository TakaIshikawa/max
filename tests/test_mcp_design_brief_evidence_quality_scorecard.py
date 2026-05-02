"""MCP tests for design brief evidence quality scorecard exports."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from max.analysis.design_brief_evidence_quality_scorecard import KIND, SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_evidence_quality_scorecard_detail,
    get_design_brief_evidence_quality_scorecard,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_evidence_quality_scorecard_db(tmp_path):
    db_path = str(tmp_path / "mcp_evidence_quality_scorecard.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_evidence_quality_scorecard_brief_id(mcp_evidence_quality_scorecard_db) -> str:
    return _seed_design_brief(mcp_evidence_quality_scorecard_db)


def test_get_design_brief_evidence_quality_scorecard_json(
    seeded_evidence_quality_scorecard_brief_id,
) -> None:
    result = get_design_brief_evidence_quality_scorecard(
        seeded_evidence_quality_scorecard_brief_id
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert result["source"]["entity_type"] == "design_brief"
    assert result["source"]["id"] == seeded_evidence_quality_scorecard_brief_id
    assert result["design_brief"]["id"] == seeded_evidence_quality_scorecard_brief_id
    assert result["summary"]["overall_score"] > 0
    assert {dimension["id"] for dimension in result["dimension_scores"]} == {
        "evidence_volume",
        "source_diversity",
        "recency",
        "role_balance",
        "contradiction_risk",
        "traceability",
    }
    assert result["evidence_refs"]["source_idea_ids"] == ["bu-mcp-evidence-quality"]
    assert result["evidence_refs"]["signal_ids"] == [
        "sig-mcp-market",
        "sig-mcp-problem",
        "sig-mcp-risk",
        "sig-mcp-validation",
        "sig-mcp-workflow",
    ]


def test_get_design_brief_evidence_quality_scorecard_markdown(
    seeded_evidence_quality_scorecard_brief_id,
) -> None:
    result = get_design_brief_evidence_quality_scorecard(
        seeded_evidence_quality_scorecard_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_evidence_quality_scorecard_brief_id
    assert result["format"] == "markdown"
    assert "# Evidence Quality Scorecard: MCP Evidence Quality Brief" in result["markdown"]
    assert "Schema: `max.design_brief.evidence_quality_scorecard.v1`" in result["markdown"]
    assert "## Dimension Scores" in result["markdown"]
    assert "## Recommended Next Evidence Actions" in result["markdown"]
    assert "sig-mcp-problem" in result["markdown"]


def test_get_design_brief_evidence_quality_scorecard_not_found(
    mcp_evidence_quality_scorecard_db,
) -> None:
    result = get_design_brief_evidence_quality_scorecard("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_evidence_quality_scorecard_invalid_format(
    seeded_evidence_quality_scorecard_brief_id,
) -> None:
    result = get_design_brief_evidence_quality_scorecard(
        seeded_evidence_quality_scorecard_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported evidence quality scorecard format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"


def test_get_design_brief_evidence_quality_scorecard_generation_failure(
    seeded_evidence_quality_scorecard_brief_id,
    monkeypatch,
) -> None:
    def fail_build(*args, **kwargs):
        raise RuntimeError("scorecard boom")

    monkeypatch.setattr(
        "max.server.mcp_tools.build_design_brief_evidence_quality_scorecard",
        fail_build,
    )

    result = get_design_brief_evidence_quality_scorecard(
        seeded_evidence_quality_scorecard_brief_id
    )

    assert result["error"] == "Failed to generate design brief evidence quality scorecard"
    assert result["code"] == 502
    assert result["details"]["service"] == "design_brief_evidence_quality_scorecard"
    assert result["details"]["reason"] == "scorecard boom"


def test_design_brief_evidence_quality_scorecard_resource(
    seeded_evidence_quality_scorecard_brief_id,
) -> None:
    result = json.loads(
        design_brief_evidence_quality_scorecard_detail(
            seeded_evidence_quality_scorecard_brief_id
        )
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_evidence_quality_scorecard_brief_id
    assert result["summary"]["overall_score"] > 0


def test_create_mcp_server_registers_evidence_quality_scorecard_tool(monkeypatch) -> None:
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

    assert "get_design_brief_evidence_quality_scorecard" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources[
            "design-brief-evidence-quality-scorecards://{brief_id}"
        ]
        == "design_brief_evidence_quality_scorecard_detail"
    )


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        published_at = datetime(2026, 4, 20, tzinfo=timezone.utc)
        for signal in [
            _signal("sig-mcp-problem", "hackernews", "problem", published_at),
            _signal("sig-mcp-market", "stackoverflow_survey", "market", published_at),
            _signal("sig-mcp-workflow", "github_issues", "workflow", published_at),
            _signal("sig-mcp-risk", "nvd_cve", "risk", published_at),
            _signal("sig-mcp-validation", "product_hunt", "validation", published_at),
        ]:
            store.insert_signal(signal)

        store.insert_insight(
            Insight(
                id="ins-mcp-evidence-quality",
                category=InsightCategory.GAP,
                title="Evidence quality handoff gap",
                summary="MCP consumers need evidence quality before acting on design briefs.",
                evidence=["sig-mcp-problem", "sig-mcp-market", "sig-mcp-workflow"],
                confidence=0.88,
                domains=["developer-tools"],
            )
        )

        unit = BuildableUnit(
            id="bu-mcp-evidence-quality",
            title="Evidence Quality MCP",
            one_liner="Expose evidence quality scorecards over MCP.",
            category="application",
            problem="Agents cannot inspect design brief evidence quality over MCP.",
            solution="Serve deterministic scorecards through an MCP tool and resource.",
            value_proposition="Make evidence readiness visible before agent action.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="agent build assignment review",
            why_now="Evidence confidence matters before autonomous implementation.",
            validation_plan="Compare MCP output against the scorecard renderer.",
            evidence_signals=[
                "sig-mcp-problem",
                "sig-mcp-market",
                "sig-mcp-workflow",
                "sig-mcp-risk",
                "sig-mcp-validation",
            ],
            inspiring_insights=["ins-mcp-evidence-quality"],
            domain_risks=["Unsupported formats should fail clearly."],
            evidence_rationale="Signals cover problem, market, workflow, risk, and validation.",
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(unit)

        return store.insert_design_brief(
            ProjectBrief(
                title="MCP Evidence Quality Brief",
                domain="developer-tools",
                theme="evidence-quality-mcp",
                lead=Candidate(unit=unit),
                readiness_score=88.0,
                why_this_now="MCP consumers need scorecards before build execution.",
                merged_product_concept="An MCP artifact for design brief evidence quality.",
                synthesis_rationale="The existing scorecard should be available to agent clients.",
                mvp_scope=["JSON scorecard tool", "Scorecard MCP resource"],
                first_milestones=["Expose scorecard tool", "Validate markdown rendering"],
                validation_plan="Run focused MCP tests against a persisted design brief.",
                risks=["Unsupported formats should fail clearly."],
                source_idea_ids=[unit.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def _signal(
    signal_id: str,
    adapter: str,
    role: str,
    published_at: datetime,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"{role.title()} evidence",
        content=f"Recent credible {role} evidence for MCP scorecard handoff.",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.85,
        published_at=published_at,
        fetched_at=published_at,
        metadata={"signal_role": role},
    )
