"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

import max.sources.base
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reset circuit breakers before each test to ensure isolation."""
    max.sources.base._circuit_breakers.clear()
    yield
    max.sources.base._circuit_breakers.clear()


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def store(tmp_db: str) -> Store:
    s = Store(db_path=tmp_db)
    yield s
    s.close()


@pytest.fixture
def sample_signal() -> Signal:
    return Signal(
        id="sig-test001",
        source_type=SignalSourceType.FORUM,
        source_adapter="hackernews",
        title="Show HN: MCP server for database access",
        content="A new MCP server that provides database access to AI agents",
        url="https://news.ycombinator.com/item?id=12345",
        author="testuser",
        tags=["mcp", "ai", "devtools"],
        credibility=0.7,
        metadata={"hn_id": 12345, "score": 350},
    )


@pytest.fixture
def sample_insight() -> Insight:
    return Insight(
        id="ins-test001",
        category=InsightCategory.GAP,
        title="MCP servers lack standardized testing",
        summary="Despite 16K+ MCP servers, no standard testing framework exists.",
        evidence=["sig-test001"],
        confidence=0.8,
        domains=["mcp", "testing"],
        implications=["Testing framework opportunity", "Quality gap in ecosystem"],
        time_horizon="near_term",
    )


@pytest.fixture
def sample_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-test001",
        title="MCP Test Framework",
        one_liner="Standardized testing for MCP servers",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="No standard way to test MCP servers",
        solution="A CLI tool that validates MCP server implementations",
        target_users="both",
        value_proposition="Reduce bugs in MCP servers by 80%",
        specific_user="MCP server maintainer",
        buyer="developer platform lead",
        workflow_context="pre-release CI validation",
        current_workaround="manual protocol testing",
        why_now="MCP server adoption is growing",
        validation_plan="run against five open-source MCP servers",
        first_10_customers="teams publishing MCP servers",
        domain_risks=["protocol churn"],
        evidence_rationale="Insight shows lack of standardized testing.",
        novelty_score=7.0,
        usefulness_score=8.0,
        quality_score=7.5,
        rejection_tags=[],
        inspiring_insights=["ins-test001"],
        evidence_signals=["sig-test001"],
        tech_approach="TypeScript CLI with protocol-level validation",
        suggested_stack={"language": "typescript", "runtime": "node"},
        composability_notes="Integrates with CI/CD pipelines",
    )


@pytest.fixture
def sample_evaluation() -> UtilityEvaluation:
    def make_score(value: float, confidence: float = 0.7, reasoning: str = "test") -> DimensionScore:
        return DimensionScore(value=value, confidence=confidence, reasoning=reasoning)

    return UtilityEvaluation(
        buildable_unit_id="bu-test001",
        pain_severity=make_score(8.0),
        addressable_scale=make_score(7.0),
        build_effort=make_score(7.5),
        composability=make_score(8.5),
        competitive_density=make_score(9.0),
        timing_fit=make_score(8.0),
        compounding_value=make_score(7.0),
        overall_score=78.0,
        strengths=["High demand", "Low competition"],
        weaknesses=["Niche audience"],
        recommendation="yes",
        weights_used={
            "pain_severity": 0.20,
            "addressable_scale": 0.15,
            "build_effort": 0.15,
            "composability": 0.15,
            "competitive_density": 0.10,
            "timing_fit": 0.10,
            "compounding_value": 0.15,
        },
    )

