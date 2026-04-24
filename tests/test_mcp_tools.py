"""Tests for MCP tools (calling tool functions directly)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from max.analysis.portfolio_synthesis import build_candidates, synthesize_project_briefs
from max.server.mcp_tools import (
    contribute_idea,
    contribute_signal,
    create_mcp_server,
    dry_run_pipeline,
    get_evaluation_calibration,
    evidence_chain_detail,
    get_design_brief,
    get_design_brief_markdown,
    get_evidence_chain,
    get_idea,
    get_implementation_plan,
    get_spec_readiness,
    get_spec_preview,
    get_stats,
    get_review_thresholds,
    list_design_briefs,
    max_portfolio_overlap,
    max_signal_freshness,
    max_source_reliability,
    portfolio_overlap_detail,
    simulate_source_allocation,
    source_allocation_detail,
    search_ideas,
    set_schedule,
    set_scheduler_ref,
    set_store_factory,
    spec_preview_detail,
)
from max.server.scheduler import Scheduler
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def _mcp_mock_profile(name: str = "devtools", domain_name: str = "developer-tools"):
    from max.profiles.schema import DomainContext, EvaluationConfig, PipelineProfile, SourceConfig

    return PipelineProfile(
        name=name,
        domain=DomainContext(
            name=domain_name,
            description=f"{domain_name} domain",
            categories=["cli_tool"],
            target_user_types=["developers"],
        ),
        sources=[
            SourceConfig(adapter="test", weight=2.0),
            SourceConfig(adapter="unused", enabled=False, weight=0.5),
        ],
        evaluation=EvaluationConfig(weight_profile="default", min_score=70.0),
        signal_limit=99,
        ideation_mode="direct",
        quality_loop_enabled=False,
        draft_count=8,
    )


def _mcp_mock_dry_run_report():
    from max.types.pipeline import DryRunReport, StageSummary

    return DryRunReport(
        stages=[
            StageSummary(
                name="fetch",
                would_process=12,
                estimated_llm_calls=0,
                skipped=False,
                reason="",
            ),
            StageSummary(
                name="ideate",
                would_process=3,
                estimated_llm_calls=3,
                skipped=False,
                reason="",
                estimated_input_tokens=4500,
                estimated_output_tokens=1500,
                estimated_total_tokens=6000,
                estimated_cost_usd=0.01,
            ),
        ],
        estimated_total_llm_calls=3,
        estimated_token_budget=6000,
        estimated_input_tokens=4500,
        estimated_output_tokens=1500,
        estimated_cost_usd=0.01,
        cost_by_stage={"ideate": 0.01},
        enabled_adapters=["test"],
        fetch_allocation={"test": 12},
    )


def _mcp_overlap_unit(
    unit_id: str,
    title: str,
    problem: str,
    *,
    target_users: str = "MCP platform teams",
    specific_user: str = "platform engineer",
    evidence: list[str] | None = None,
    status: str = "evaluated",
    quality_score: float = 7.0,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=problem,
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem=problem,
        solution="Build a workflow automation surface",
        target_users=target_users,
        specific_user=specific_user,
        value_proposition="Reduce manual review work",
        evidence_signals=evidence or [],
        tech_approach="TypeScript service with workflow automation",
        suggested_stack={"language": "typescript", "runtime": "node"},
        quality_score=quality_score,
        usefulness_score=8.0,
        status=status,
    )


def _seed_feedback_analytics(
    db_path: str,
    *,
    domain: str = "devtools",
) -> None:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        def _unit(unit_id: str) -> BuildableUnit:
            return BuildableUnit(
                id=unit_id,
                title=f"Idea {unit_id}",
                one_liner="Analytics idea",
                category=BuildableCategory.CLI_TOOL,
                ideation_mode=IdeationMode.DIRECT,
                problem="Problem",
                solution="Solution",
                value_proposition="Value",
                domain=domain,
            )

        def _score(val: float) -> DimensionScore:
            return DimensionScore(value=val, confidence=0.7, reasoning="test")

        for unit_id, score, outcome in [
            ("bu-mcp-cal-1", 90.0, "approved"),
            ("bu-mcp-cal-2", 82.0, "approved"),
            ("bu-mcp-cal-3", 76.0, "approved"),
            ("bu-mcp-cal-4", 48.0, "rejected"),
            ("bu-mcp-cal-5", 40.0, "rejected"),
            ("bu-mcp-cal-6", 32.0, "rejected"),
        ]:
            store.insert_buildable_unit(_unit(unit_id))
            store.insert_evaluation(
                UtilityEvaluation(
                    buildable_unit_id=unit_id,
                    pain_severity=_score(8.0),
                    addressable_scale=_score(7.0),
                    build_effort=_score(6.0),
                    composability=_score(7.0),
                    competitive_density=_score(8.0),
                    timing_fit=_score(7.0),
                    compounding_value=_score(6.0),
                    overall_score=score,
                    recommendation="yes",
                    strengths=["Testable"],
                    weaknesses=["Narrow scope"],
                    weights_used={"pain_severity": 0.20},
                )
            )
            store.insert_feedback(unit_id, outcome)
    finally:
        store.close()


@pytest.fixture
def mcp_db(tmp_path):
    """Create temp DB and configure mcp_tools to use it."""
    db_path = str(tmp_path / "test_mcp.db")
    # Initialize schema
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    # Reset to default
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_mcp_db(mcp_db):
    """DB pre-populated with test data."""
    store = Store(db_path=mcp_db, wal_mode=True)

    signal = Signal(
        id="sig-mcp001",
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title="MCP Test Signal",
        content="Test content for MCP",
        url="https://example.com/mcp-test",
        tags=["mcp"],
    )
    store.insert_signal(signal)

    unit = BuildableUnit(
        id="bu-mcp001",
        title="MCP Test Idea",
        one_liner="A test idea for MCP testing",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Testing MCP tools",
        solution="Write unit tests",
        value_proposition="Reliable MCP tools",
    )
    store.insert_buildable_unit(unit)

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    evaluation = UtilityEvaluation(
        buildable_unit_id="bu-mcp001",
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(7.5),
        composability=_score(8.5),
        competitive_density=_score(9.0),
        timing_fit=_score(8.0),
        compounding_value=_score(7.0),
        overall_score=78.0,
        strengths=["Testable"],
        weaknesses=["Narrow scope"],
        recommendation="yes",
        weights_used={"pain_severity": 0.20},
    )
    store.insert_evaluation(evaluation)
    store.close()
    return mcp_db


@pytest.fixture
def seeded_evidence_chain_db(mcp_db):
    """DB pre-populated with an idea, insight, transitive signal, and direct signal."""
    store = Store(db_path=mcp_db, wal_mode=True)

    insight_signal = Signal(
        id="sig-chain001",
        source_type=SignalSourceType.FORUM,
        source_adapter="hn",
        title="Insight Signal",
        content="Evidence that supports the insight",
        url="https://example.com/insight-signal",
        tags=["mcp"],
        credibility=0.8,
        metadata={"signal_role": "problem"},
    )
    direct_signal = Signal(
        id="sig-chain002",
        source_type=SignalSourceType.REGISTRY,
        source_adapter="npm",
        title="Direct Signal",
        content="Direct evidence for the idea",
        url="https://example.com/direct-signal",
        tags=["registry"],
        credibility=0.7,
    )
    store.insert_signal(insight_signal)
    store.insert_signal(direct_signal)

    insight = Insight(
        id="ins-chain001",
        category=InsightCategory.GAP,
        title="Testing Gap",
        summary="MCP tools need better testing.",
        evidence=["sig-chain001"],
        confidence=0.9,
        domains=["developer-tools"],
    )
    store.insert_insight(insight)

    unit = BuildableUnit(
        id="bu-chain001",
        title="Evidence Chain Idea",
        one_liner="Expose evidence graph",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Evidence is hard to inspect",
        solution="Return a graph",
        value_proposition="Traceable ideas",
        inspiring_insights=["ins-chain001"],
        evidence_signals=["sig-chain002"],
    )
    store.insert_buildable_unit(unit)
    store.close()
    return mcp_db


@pytest.fixture
def seeded_design_brief_db(mcp_db):
    """DB pre-populated with one persisted design brief."""
    store = Store(db_path=mcp_db, wal_mode=True)

    first = BuildableUnit(
        id="bu-brief001",
        title="MCP Design Brief",
        one_liner="A test design brief for MCP",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Design handoffs lack context",
        solution="Persist synthesized briefs",
        value_proposition="Clear implementation handoff",
        specific_user="product engineer",
        buyer="engineering manager",
        workflow_context="MCP tool browsing",
        why_now="Design brief synthesis is now persisted.",
        validation_plan="Call the MCP tools.",
        domain="developer-tools",
        status="approved",
    )
    second = BuildableUnit(
        id="bu-brief002",
        title="MCP Supporting Idea",
        one_liner="Supporting idea for MCP design brief",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Supporting context is hard to find",
        solution="Attach source relationships",
        value_proposition="Better handoffs",
        specific_user="product engineer",
        buyer="engineering manager",
        workflow_context="MCP tool browsing",
        why_now="Design brief synthesis is now persisted.",
        validation_plan="Call the MCP tools.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(first)
    store.insert_buildable_unit(second)

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    evaluations = {}
    for unit_id, score in [("bu-brief001", 75.0), ("bu-brief002", 70.0)]:
        evaluation = UtilityEvaluation(
            buildable_unit_id=unit_id,
            pain_severity=_score(7.0),
            addressable_scale=_score(7.0),
            build_effort=_score(8.0),
            composability=_score(7.0),
            competitive_density=_score(7.0),
            timing_fit=_score(7.0),
            compounding_value=_score(7.0),
            overall_score=score,
            strengths=["Testable"],
            weaknesses=["Narrow scope"],
            recommendation="yes",
            weights_used={"pain_severity": 0.20},
        )
        store.insert_evaluation(evaluation)
        evaluations[unit_id] = evaluation

    candidates = build_candidates(
        [first, second],
        evaluations=evaluations,
        feedback={"bu-brief001": {"approval_score": 8}, "bu-brief002": {"approval_score": 6}},
    )
    brief_id = store.insert_design_brief(synthesize_project_briefs(candidates, top=1)[0])
    store.close()
    return brief_id


def test_search_ideas_empty(mcp_db):
    result = search_ideas()
    assert result == []


def test_search_ideas_with_data(seeded_mcp_db):
    result = search_ideas()
    assert len(result) == 1
    assert result[0]["id"] == "bu-mcp001"
    assert result[0]["score"] == 78.0


def test_search_ideas_filter_category(seeded_mcp_db):
    result = search_ideas(category="cli_tool")
    assert len(result) == 1

    result = search_ideas(category="library")
    assert len(result) == 0


def test_search_ideas_filter_query(seeded_mcp_db):
    result = search_ideas(query="MCP Test")
    assert len(result) == 1

    result = search_ideas(query="nonexistent")
    assert len(result) == 0


def test_search_ideas_filter_min_score(seeded_mcp_db):
    result = search_ideas(min_score=50.0)
    assert len(result) == 1

    result = search_ideas(min_score=90.0)
    assert len(result) == 0


def test_get_idea_found(seeded_mcp_db):
    result = get_idea(id="bu-mcp001")
    assert result["title"] == "MCP Test Idea"
    assert result["evaluation"]["overall_score"] == 78.0


def test_get_idea_not_found(mcp_db):
    result = get_idea(id="nonexistent")
    assert "error" in result
    assert result["code"] == 404


def test_get_spec_preview_success(seeded_mcp_db):
    result = get_spec_preview(id="bu-mcp001")

    assert result["id"] == "bu-mcp001"
    assert result["title"] == "MCP Test Idea"
    assert result["score"] == 78.0
    assert result["recommendation"] == "yes"
    assert result["preview"]["kind"] == "tact.project_spec"
    assert result["preview"]["source"]["idea_id"] == "bu-mcp001"
    assert result["preview"]["evaluation"]["overall_score"] == 78.0


def test_get_spec_preview_missing_idea(mcp_db):
    result = get_spec_preview(id="missing")

    assert result["error"] == "Idea not found: missing"
    assert result["code"] == 404


def test_get_spec_preview_missing_evaluation(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    unit = BuildableUnit(
        id="bu-noeval001",
        title="Unevaluated Idea",
        one_liner="A test idea without evaluation",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="No evaluation exists",
        solution="Return a clear error",
        value_proposition="Better MCP errors",
    )
    store.insert_buildable_unit(unit)
    store.close()

    result = get_spec_preview(id="bu-noeval001")

    assert result["error"] == "Evaluation not found for idea: bu-noeval001"
    assert result["code"] == 404


def test_get_spec_readiness_success(seeded_mcp_db):
    result = get_spec_readiness(id="bu-mcp001")

    assert result["idea_id"] == "bu-mcp001"
    assert result["status"] == "fail"
    assert result["passed"] is False
    assert "target_user" in result["failed_check_ids"]


def test_get_spec_readiness_missing_idea(mcp_db):
    result = get_spec_readiness(id="missing")

    assert result["error"] == "Idea not found: missing"
    assert result["code"] == 404


def test_get_spec_readiness_missing_evaluation(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    unit = BuildableUnit(
        id="bu-noeval-readiness",
        title="Unevaluated Readiness Idea",
        one_liner="A test idea without evaluation",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="No evaluation exists",
        solution="Return a clear error",
        value_proposition="Better MCP errors",
    )
    store.insert_buildable_unit(unit)
    store.close()

    result = get_spec_readiness(id="bu-noeval-readiness")

    assert result["error"] == "Evaluation not found for idea: bu-noeval-readiness"
    assert result["code"] == 404


def test_get_implementation_plan_success(seeded_mcp_db):
    result = get_implementation_plan(id="bu-mcp001")

    assert result["schema_version"] == "max-implementation-plan/v1"
    assert result["kind"] == "max.implementation_plan"
    assert result["idea_id"] == "bu-mcp001"
    assert result["summary"]["title"] == "MCP Test Idea"
    assert result["summary"]["recommendation"] == "yes"
    assert result["source"]["spec_preview_schema_version"] == "tact-spec-preview/v1"
    assert [milestone["id"] for milestone in result["milestones"]] == ["M1", "M2", "M3", "M4"]
    assert any(task["id"] == "T3" for task in result["task_breakdown"])


def test_get_implementation_plan_missing_idea(mcp_db):
    result = get_implementation_plan(id="missing")

    assert result["error"] == "Idea not found: missing"
    assert result["code"] == 404


def test_get_implementation_plan_missing_evaluation(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    unit = BuildableUnit(
        id="bu-noeval-plan",
        title="Unevaluated Plan Idea",
        one_liner="A test idea without evaluation",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="No evaluation exists",
        solution="Return a clear error",
        value_proposition="Better MCP errors",
    )
    store.insert_buildable_unit(unit)
    store.close()

    result = get_implementation_plan(id="bu-noeval-plan")

    assert result["error"] == "Evaluation not found for idea: bu-noeval-plan"
    assert result["code"] == 404


def test_spec_preview_resource(seeded_mcp_db):
    result = spec_preview_detail("bu-mcp001")

    assert '"id": "bu-mcp001"' in result
    assert '"kind": "tact.project_spec"' in result
    assert '"overall_score": 78.0' in result


def test_get_evidence_chain_graph(seeded_evidence_chain_db):
    result = get_evidence_chain(id="bu-chain001")

    assert result["idea"]["id"] == "bu-chain001"
    assert [ins["id"] for ins in result["insights"]] == ["ins-chain001"]
    assert {sig["id"] for sig in result["signals"]} == {"sig-chain001", "sig-chain002"}
    assert {
        (edge["source"], edge["target"], edge["type"])
        for edge in result["edges"]
    } == {
        ("bu-chain001", "ins-chain001", "inspired_by"),
        ("ins-chain001", "sig-chain001", "supported_by"),
        ("bu-chain001", "sig-chain002", "direct_evidence"),
    }


def test_get_evidence_chain_not_found(mcp_db):
    result = get_evidence_chain(id="missing")
    assert result["error"] == "Idea not found: missing"
    assert result["code"] == 404


def test_evidence_chain_resource(seeded_evidence_chain_db):
    result = evidence_chain_detail("bu-chain001")
    assert '"idea": {' in result
    assert '"type": "direct_evidence"' in result


def test_list_design_briefs(seeded_design_brief_db):
    result = list_design_briefs()
    assert len(result) == 1
    assert result[0]["id"] == seeded_design_brief_db
    assert result[0]["title"] == "MCP Design Brief"


def test_list_design_briefs_filters(seeded_design_brief_db):
    assert len(list_design_briefs(domain="developer-tools")) == 1
    assert list_design_briefs(domain="healthcare") == []
    assert len(list_design_briefs(status="candidate")) == 1
    assert list_design_briefs(status="designing") == []


def test_get_design_brief_found(seeded_design_brief_db):
    result = get_design_brief(seeded_design_brief_db)
    assert result["id"] == seeded_design_brief_db
    assert result["lead_idea_id"] == "bu-brief001"
    assert result["source_idea_ids"] == ["bu-brief001", "bu-brief002"]


def test_get_design_brief_not_found(mcp_db):
    result = get_design_brief("dbf-missing")
    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404


def test_get_design_brief_markdown(seeded_design_brief_db):
    result = get_design_brief_markdown(seeded_design_brief_db)
    assert result["id"] == seeded_design_brief_db
    assert "# MCP Design Brief" in result["markdown"]
    assert "### MVP Scope" in result["markdown"]


def test_get_design_brief_markdown_not_found(mcp_db):
    result = get_design_brief_markdown("dbf-missing")
    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404


def test_max_portfolio_overlap_returns_serializable_clusters_sorted(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    for unit in [
        _mcp_overlap_unit(
            "bu-overlap-a",
            "MCP Release Tester",
            "MCP maintainers need repeatable server release testing",
            evidence=["sig-mcp-shared", "sig-release"],
            quality_score=8.0,
        ),
        _mcp_overlap_unit(
            "bu-overlap-b",
            "MCP Protocol Test Console",
            "MCP maintainers need repeatable protocol release testing",
            evidence=["sig-mcp-shared", "sig-protocol"],
            quality_score=7.0,
        ),
        _mcp_overlap_unit(
            "bu-overlap-c",
            "Payroll Export Reviewer",
            "Payroll analysts need spreadsheet export review automation",
            target_users="finance operations teams",
            specific_user="payroll analyst",
            evidence=["sig-payroll-shared"],
            quality_score=6.0,
        ),
        _mcp_overlap_unit(
            "bu-overlap-d",
            "Payroll Export Checker",
            "Payroll analysts need spreadsheet export checking",
            target_users="finance operations teams",
            specific_user="payroll analyst",
            evidence=["sig-payroll-shared", "sig-payroll-extra"],
            quality_score=5.0,
        ),
    ]:
        store.insert_buildable_unit(unit)
    store.close()

    result = max_portfolio_overlap(min_overlap_score=0.25)

    assert isinstance(result, list)
    assert len(result) == 2
    assert [cluster["overlap_score"] for cluster in result] == sorted(
        [cluster["overlap_score"] for cluster in result],
        reverse=True,
    )
    assert {
        "cluster_id",
        "idea_ids",
        "representative_idea_ids",
        "overlap_score",
        "reasons",
        "suggested_action",
    } <= result[0].keys()
    mcp_cluster = next(
        cluster
        for cluster in result
        if cluster["idea_ids"] == ["bu-overlap-a", "bu-overlap-b"]
    )
    assert mcp_cluster["representative_idea_ids"] == ["bu-overlap-a", "bu-overlap-b"]
    assert {reason["type"] for reason in mcp_cluster["reasons"]} >= {
        "target_users",
        "problem_statement",
        "evidence_signal_ids",
    }
    json.dumps(result)


def test_max_portfolio_overlap_include_archived(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    store.insert_buildable_unit(
        _mcp_overlap_unit(
            "bu-overlap-live",
            "Incident Triage Console",
            "SRE teams need incident triage automation",
            target_users="SRE teams",
            specific_user="site reliability engineer",
            evidence=["sig-incident-shared"],
        )
    )
    store.insert_buildable_unit(
        _mcp_overlap_unit(
            "bu-overlap-archived",
            "Incident Triage Assistant",
            "SRE teams need incident triage review automation",
            target_users="SRE teams",
            specific_user="site reliability engineer",
            evidence=["sig-incident-shared"],
            status="archived",
        )
    )
    store.close()

    assert max_portfolio_overlap(min_overlap_score=0.25) == []
    result = max_portfolio_overlap(min_overlap_score=0.25, include_archived=True)

    assert len(result) == 1
    assert result[0]["idea_ids"] == ["bu-overlap-archived", "bu-overlap-live"]


def test_max_portfolio_overlap_rejects_invalid_arguments(mcp_db):
    result = max_portfolio_overlap(limit=0)
    assert result["error"] == "limit must be at least 1"
    assert result["code"] == 400

    result = max_portfolio_overlap(min_overlap_score=1.1)
    assert result["error"] == "min_overlap_score must be between 0 and 1"
    assert result["code"] == 400


def test_portfolio_overlap_resource_returns_default_report(seeded_mcp_db):
    result = json.loads(portfolio_overlap_detail())

    assert result == []


def test_simulate_source_allocation_uses_profile_and_budget(mcp_db, monkeypatch):
    monkeypatch.setattr(
        "max.profiles.loader.load_profile",
        lambda name: _mcp_mock_profile(),
    )

    result = simulate_source_allocation(profile="devtools", budget=12)

    assert result["profile"] == "devtools"
    assert result["domain"] == "developer-tools"
    assert result["total_budget"] == 12
    assert result["allocation"] == {"test": 12}
    assert [source["adapter"] for source in result["sources"]] == ["test", "unused"]
    assert result["sources"][0]["allocated_limit"] == 12
    assert result["sources"][1]["allocated_limit"] == 0


def test_source_allocation_resource_returns_default_report(mcp_db, monkeypatch):
    monkeypatch.setattr("max.config.MAX_PROFILE", "devtools")
    monkeypatch.setattr(
        "max.profiles.loader.load_profile",
        lambda name: _mcp_mock_profile(),
    )

    result = json.loads(source_allocation_detail())

    assert result["profile"] == "devtools"
    assert result["domain"] == "developer-tools"
    assert result["total_budget"] == 99
    assert result["allocation"] == {"test": 99}


def test_contribute_signal(mcp_db):
    result = contribute_signal(
        title="Test Signal via MCP",
        content="Some content",
        url="https://example.com/mcp-contributed",
    )
    assert result["status"] == "created"
    assert result["id"].startswith("sig-")


def test_contribute_signal_duplicate(mcp_db):
    first = contribute_signal(
        title="Test Signal via MCP",
        content="Some content",
        url="https://example.com/mcp-duplicate",
    )
    second = contribute_signal(
        title="Duplicate Signal via MCP",
        content="Different content",
        url="https://example.com/mcp-duplicate",
    )

    assert first["status"] == "created"
    assert second["status"] == "duplicate"
    assert second["id"] == first["id"]
    assert second["title"] == "Test Signal via MCP"


def test_contribute_idea(mcp_db):
    result = contribute_idea(
        title="Test Idea via MCP",
        problem="Need testing",
        solution="Test via MCP tools",
    )
    assert result["status"] == "draft"
    assert result["id"].startswith("bu-")


def test_get_stats_empty(mcp_db):
    result = get_stats()
    assert result["signals_count"] == 0
    assert result["ideas_count"] == 0
    assert result["avg_score"] is None


def test_get_stats_seeded(seeded_mcp_db):
    result = get_stats()
    assert result["signals_count"] == 1
    assert result["ideas_count"] == 1
    assert result["avg_score"] == 78.0


def test_max_signal_freshness_default_output(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    store.insert_signal(
        Signal(
            id="sig-fresh-mcp-1",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Fresh MCP signal",
            content="Recent signal",
            url="https://example.com/fresh-mcp-1",
            fetched_at=datetime.now(timezone.utc) - timedelta(days=2),
            tags=["mcp"],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-fresh-mcp-2",
            source_type=SignalSourceType.REGISTRY,
            source_adapter="other",
            title="Stale MCP signal",
            content="Older signal",
            url="https://example.com/fresh-mcp-2",
            fetched_at=datetime.now(timezone.utc) - timedelta(days=40),
            tags=["registry"],
        )
    )
    store.close()

    result = max_signal_freshness()

    assert result["max_age_days"] == 30
    assert result["total_signals"] == 2
    assert result["stale_signals"] == 1
    assert result["filters"] == {
        "profile": None,
        "domain": None,
        "source_adapters": None,
        "max_age_days": 30,
    }


def test_max_signal_freshness_filters_source_adapter_string_and_list(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    store.insert_signal(
        Signal(
            id="sig-fresh-filter-1",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Test adapter signal",
            content="Adapter-filtered signal",
            url="https://example.com/fresh-filter-1",
            fetched_at=datetime.now(timezone.utc),
        )
    )
    store.insert_signal(
        Signal(
            id="sig-fresh-filter-2",
            source_type=SignalSourceType.REGISTRY,
            source_adapter="other",
            title="Other adapter signal",
            content="Adapter-filtered signal",
            url="https://example.com/fresh-filter-2",
            fetched_at=datetime.now(timezone.utc),
        )
    )
    store.close()

    comma_result = max_signal_freshness(source_adapter="test, missing")
    list_result = max_signal_freshness(source_adapter=["other"])

    assert comma_result["filters"]["source_adapters"] == ["missing", "test"]
    assert comma_result["source_adapter_filters"] == ["missing", "test"]
    assert comma_result["total_signals"] == 1
    assert comma_result["by_source_adapter"][0]["key"] == "test"
    assert list_result["filters"]["source_adapters"] == ["other"]
    assert list_result["total_signals"] == 1
    assert list_result["by_source_adapter"][0]["key"] == "other"


def test_max_signal_freshness_filters_profile_enabled_adapters(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    store.insert_signal(
        Signal(
            id="sig-fresh-profile-1",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Profile adapter signal",
            content="Included by profile",
            url="https://example.com/fresh-profile-1",
            fetched_at=datetime.now(timezone.utc),
        )
    )
    store.insert_signal(
        Signal(
            id="sig-fresh-profile-2",
            source_type=SignalSourceType.REGISTRY,
            source_adapter="other",
            title="Non-profile adapter signal",
            content="Excluded by profile",
            url="https://example.com/fresh-profile-2",
            fetched_at=datetime.now(timezone.utc),
        )
    )
    store.close()

    with patch("max.profiles.loader.load_profile", return_value=_mcp_mock_profile()):
        result = max_signal_freshness(
            profile="devtools",
            source_adapter=["test", "other"],
        )

    assert result["filters"]["profile"] == "devtools"
    assert result["filters"]["domain"] == "developer-tools"
    assert result["filters"]["source_adapters"] == ["test"]
    assert result["total_signals"] == 1
    assert result["by_source_adapter"][0]["key"] == "test"


def test_max_signal_freshness_rejects_invalid_max_age_days(mcp_db):
    result = max_signal_freshness(max_age_days=0)
    assert result["error"] == "max_age_days must be at least 1"
    assert result["code"] == 400


def test_signal_freshness_resource_registered(monkeypatch):
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

    assert "max_signal_freshness" in FakeMCP.latest.tools
    assert FakeMCP.latest.resources["signals://freshness"] == "signal_freshness_detail"
    assert "max_portfolio_overlap" in FakeMCP.latest.tools
    assert FakeMCP.latest.resources["portfolio://overlap"] == "portfolio_overlap_detail"
    assert "simulate_source_allocation" in FakeMCP.latest.tools
    assert FakeMCP.latest.resources["sources://allocation-simulation"] == "source_allocation_detail"


def test_evaluation_calibration_returns_machine_readable_payload(mcp_db):
    _seed_feedback_analytics(mcp_db)

    payload = get_evaluation_calibration(domain="devtools", min_samples=2, limit=10)

    assert payload["domain"] == "devtools"
    assert payload["min_samples"] == 2
    assert payload["limit"] == 10
    assert payload["total_groups"] == 1
    assert payload["total_samples"] == 6
    group = payload["groups"][0]
    assert group["domain"] == "devtools"
    assert group["recommendation"] == "yes"
    assert group["sample_count"] == 6
    assert group["approved_count"] == 3
    assert group["rejected_count"] == 3
    assert group["score_buckets"]
    assert group["score_buckets"][0]["sample_count"] >= 1


def test_review_thresholds_returns_machine_readable_payload(mcp_db):
    _seed_feedback_analytics(mcp_db)

    payload = get_review_thresholds(domain="devtools", min_samples=4)

    assert payload["domain"] == "devtools"
    assert payload["min_samples"] == 4
    assert payload["default_approve_threshold"] == 68.0
    assert payload["default_reject_threshold"] == 50.0
    assert payload["recommendations"] == [
        {
            "domain": "devtools",
            "approve_threshold": 79.0,
            "reject_threshold": 44.0,
            "sample_count": 6,
            "approved_count": 3,
            "rejected_count": 3,
            "sufficient_samples": True,
            "fallback_used": False,
            "reason": "computed from approved and rejected feedback",
        }
    ]


def test_calibration_and_threshold_tools_registered(monkeypatch):
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

    assert "get_evaluation_calibration" in FakeMCP.latest.tools
    assert "get_review_thresholds" in FakeMCP.latest.tools
    assert "max_signal_freshness" in FakeMCP.latest.tools
    assert "simulate_source_allocation" in FakeMCP.latest.tools
    assert FakeMCP.latest.resources["signals://freshness"] == "signal_freshness_detail"
    assert FakeMCP.latest.resources["portfolio://overlap"] == "portfolio_overlap_detail"
    assert FakeMCP.latest.resources["sources://allocation-simulation"] == "source_allocation_detail"


def test_max_source_reliability_filters_profile_window_and_min_count(mcp_db):
    store = Store(db_path=mcp_db, wal_mode=True)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    old = datetime.now(timezone.utc) - timedelta(days=10)
    store.insert_signal(
        Signal(
            id="sig-reliable-1",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Recent forum signal",
            content="Developers report a repeated problem.",
            url="https://example.com/reliable-1",
            fetched_at=recent,
            tags=["mcp"],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-reliable-2",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Another recent forum signal",
            content="More developers report the same problem.",
            url="https://example.com/reliable-2",
            fetched_at=recent,
            tags=["mcp"],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-old",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Old forum signal",
            content="Old evidence outside the requested window.",
            url="https://example.com/old",
            fetched_at=old,
            tags=["mcp"],
        )
    )
    store.insert_signal(
        Signal(
            id="sig-other",
            source_type=SignalSourceType.REGISTRY,
            source_adapter="other",
            title="Filtered adapter signal",
            content="Evidence from another profile adapter.",
            url="https://example.com/other",
            fetched_at=recent,
            tags=["registry"],
        )
    )
    store.close()

    with patch("max.profiles.loader.load_profile", return_value=_mcp_mock_profile()):
        result = max_source_reliability(
            profile="devtools",
            time_window="2d",
            min_signal_count=2,
        )

    assert result["filters"]["profile"] == "devtools"
    assert result["filters"]["domain"] == "developer-tools"
    assert result["filters"]["source_adapters"] == ["test"]
    assert result["filters"]["time_window"] == "2d"
    assert result["filters"]["min_signal_count"] == 2
    assert result["signal_limit"] == 99
    assert result["total_signals"] == 2
    assert len(result["source_types"]) == 1
    assert result["source_types"][0]["source_type"] == "forum"
    assert result["source_types"][0]["total_signals"] == 2


def test_max_source_reliability_rejects_invalid_time_window(mcp_db):
    result = max_source_reliability(time_window="soon")
    assert "error" in result
    assert result["code"] == 400


def test_set_schedule_pipeline_config():
    scheduler = Scheduler(interval_seconds=3600, enabled=True)
    set_scheduler_ref(scheduler)
    try:
        result = set_schedule(
            profile="devtools",
            include_all=True,
            signal_limit=45,
            min_score=62.5,
            weight_profile="quick_wins",
            ideation_mode="refinement",
            quality_loop_enabled=True,
        )
    finally:
        set_scheduler_ref(None)

    assert result["profile"] == "devtools"
    assert result["include_all"] is True
    assert result["pipeline_config"]["signal_limit"] == 45
    assert result["pipeline_config"]["min_score"] == 62.5
    assert result["pipeline_config"]["weight_profile"] == "quick_wins"
    assert result["pipeline_config"]["ideation_mode"] == "refinement"
    assert result["pipeline_config"]["quality_loop_enabled"] is True


def test_dry_run_pipeline_selects_profile_and_applies_overrides():
    profile = _mcp_mock_profile()
    report = _mcp_mock_dry_run_report()

    with (
        patch("max.profiles.loader.load_profile", return_value=profile) as mock_load,
        patch("max.pipeline.runner.run_pipeline", return_value=report) as mock_run,
    ):
        result = dry_run_pipeline(
            profile="devtools",
            signal_limit=12,
            min_score=62.5,
            weight_profile="quick_wins",
            ideation_mode="refinement",
            quality_loop_enabled=True,
            draft_count=4,
            stages=["fetch", "ideate"],
        )

    mock_load.assert_called_once_with("devtools")
    _, kwargs = mock_run.call_args
    assert kwargs["dry_run"] is True
    assert kwargs["stages"] == ["fetch", "ideate"]
    assert kwargs["profile"].signal_limit == 12
    assert kwargs["profile"].evaluation.min_score == 62.5
    assert kwargs["profile"].evaluation.weight_profile == "quick_wins"
    assert kwargs["profile"].ideation_mode == "refinement"
    assert kwargs["profile"].quality_loop_enabled is True
    assert kwargs["profile"].draft_count == 4
    assert profile.signal_limit == 99
    assert result["profile_name"] == "devtools"
    assert result["domain"] == "developer-tools"


def test_dry_run_pipeline_reports_budget_and_adapter_shape():
    profile = _mcp_mock_profile()
    report = _mcp_mock_dry_run_report()

    with (
        patch("max.profiles.loader.load_profile", return_value=profile),
        patch("max.pipeline.runner.run_pipeline", return_value=report),
    ):
        result = dry_run_pipeline(profile="devtools", signal_limit=12)

    assert result["enabled_adapters"] == ["test"]
    assert result["fetch_allocation"] == {"test": 12}
    assert result["effective_config"] == {
        "signal_limit": 12,
        "min_score": 70.0,
        "weight_profile": "default",
        "ideation_mode": "direct",
        "quality_loop_enabled": False,
        "draft_count": 8,
    }
    assert result["estimated_total_llm_calls"] == 3
    assert result["estimated_token_budget"] == 6000
    assert result["estimated_input_tokens"] == 4500
    assert result["estimated_output_tokens"] == 1500
    assert result["estimated_cost_usd"] == 0.01
    assert result["cost_by_stage"] == {"ideate": 0.01}
    assert result["stages"][0]["name"] == "fetch"
    assert result["stages"][0]["would_process"] == 12
    assert result["stages"][1]["estimated_total_tokens"] == 6000


def test_dry_run_pipeline_returns_error_for_invalid_profile():
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("missing")):
        result = dry_run_pipeline(profile="missing")

    assert result["error"] == "Profile not found: missing"
    assert result["code"] == 404


def test_dry_run_pipeline_returns_error_for_invalid_stages():
    profile = _mcp_mock_profile()

    with (
        patch("max.profiles.loader.load_profile", return_value=profile),
        patch("max.pipeline.runner.run_pipeline", side_effect=ValueError("Unknown stages: nope")),
    ):
        result = dry_run_pipeline(profile="devtools", stages=["nope"])

    assert result["error"] == "Unknown stages: nope"
    assert result["code"] == 400


# ── Structured Error Handling Tests ────────────────────────────────────


def test_get_idea_not_found_returns_structured_error(mcp_db):
    """Test that missing idea returns ResourceNotFoundError with code 404."""
    result = get_idea(id="missing-idea")

    assert result["error"] == "Idea not found: missing-idea"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "buildable_unit"
    assert result["details"]["resource_id"] == "missing-idea"


def test_get_spec_preview_missing_evaluation_returns_structured_error(mcp_db):
    """Test that missing evaluation returns ResourceNotFoundError with suggestion."""
    store = Store(db_path=mcp_db, wal_mode=True)
    unit = BuildableUnit(
        id="bu-noeval",
        title="Unevaluated Idea",
        one_liner="Test idea",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="No evaluation",
        solution="Return error",
        value_proposition="Better errors",
    )
    store.insert_buildable_unit(unit)
    store.close()

    result = get_spec_preview(id="bu-noeval")

    assert result["error"] == "Evaluation not found for idea: bu-noeval"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "evaluation"
    assert result["details"]["resource_id"] == "bu-noeval"
    assert result["details"]["suggestion"] == "Run evaluate_idea first"


def test_simulate_source_allocation_invalid_budget_returns_validation_error(mcp_db):
    """Test that invalid budget returns ValidationError with code 400."""
    result = simulate_source_allocation(budget=0)

    assert result["error"] == "budget must be at least 1"
    assert result["code"] == 400
    assert result["details"]["field"] == "budget"
    assert result["details"]["expected"] == "integer >= 1"
    assert result["details"]["actual"] == "0"


def test_max_portfolio_overlap_invalid_limit_returns_validation_error(mcp_db):
    """Test that invalid limit returns ValidationError."""
    result = max_portfolio_overlap(limit=0)

    assert "error" in result
    assert result["code"] == 400


def test_max_portfolio_overlap_invalid_score_returns_validation_error(mcp_db):
    """Test that invalid overlap score returns ValidationError."""
    result = max_portfolio_overlap(min_overlap_score=1.5)

    assert "error" in result
    assert result["code"] == 400


def test_max_source_reliability_missing_profile_returns_not_found_error(mcp_db):
    """Test that missing profile returns ResourceNotFoundError."""
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("not found")):
        result = max_source_reliability(profile="missing")

    assert result["error"] == "Profile not found: missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "profile"
    assert result["details"]["resource_id"] == "missing"


def test_max_source_reliability_invalid_time_window_returns_validation_error(mcp_db):
    """Test that invalid time window returns ValidationError."""
    result = max_source_reliability(time_window="invalid")

    assert "error" in result
    assert result["code"] == 400
    assert result["details"]["field"] == "time_window"


def test_max_signal_freshness_missing_profile_returns_not_found_error(mcp_db):
    """Test that missing profile returns ResourceNotFoundError."""
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("not found")):
        result = max_signal_freshness(profile="missing")

    assert result["error"] == "Profile not found: missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "profile"


def test_max_signal_freshness_invalid_max_age_returns_validation_error(mcp_db):
    """Test that invalid max_age_days returns ValidationError."""
    result = max_signal_freshness(max_age_days=0)

    assert "error" in result
    assert result["code"] == 400
    assert result["details"]["field"] == "max_age_days"


def test_dry_run_pipeline_missing_profile_returns_not_found_error(mcp_db):
    """Test that missing profile returns ResourceNotFoundError."""
    with patch("max.profiles.loader.load_profile", side_effect=FileNotFoundError("not found")):
        result = dry_run_pipeline(profile="missing")

    assert result["error"] == "Profile not found: missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "profile"
    assert result["details"]["resource_id"] == "missing"


def test_get_design_brief_not_found_returns_structured_error(mcp_db):
    """Test that missing design brief returns ResourceNotFoundError."""
    result = get_design_brief("missing-brief")

    assert result["error"] == "Design brief not found: missing-brief"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "missing-brief"


def test_get_evidence_chain_not_found_returns_structured_error(mcp_db):
    """Test that missing idea returns ResourceNotFoundError."""
    result = get_evidence_chain("missing-idea")

    assert result["error"] == "Idea not found: missing-idea"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "buildable_unit"


def test_error_codes_are_consistent():
    """Test that error codes match their semantic meaning."""
    from max.server.errors import ErrorCode

    assert ErrorCode.INVALID_INPUT == 400
    assert ErrorCode.NOT_FOUND == 404
    assert ErrorCode.STATE_CONFLICT == 409
    assert ErrorCode.RATE_LIMITED == 429
    assert ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE == 502


def test_error_to_dict_includes_all_fields():
    """Test that MCPToolError.to_dict includes all required fields."""
    from max.server.errors import ValidationError

    error = ValidationError(
        "test error",
        field="test_field",
        expected="value > 0",
        actual="-1",
    )
    result = error.to_dict()

    assert result["error"] == "test error"
    assert result["code"] == 400
    assert result["details"]["field"] == "test_field"
    assert result["details"]["expected"] == "value > 0"
    assert result["details"]["actual"] == "-1"
