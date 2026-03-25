"""Integration test — full pipeline with mocked LLM and mocked HTTP."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.pipeline.runner import PipelineResult, run_pipeline
from max.synthesis.engine import SynthesisOutput, InsightOutput
from max.ideation.engine import IdeationOutput, BuildableUnitOutput
from max.evaluation.engine import EvaluationOutput, DimensionScoreOutput
from max.spec.generator import SpecOutput, GoalOutput, TechStackOutput, PatternOutput, DecisionOutput, RequirementOutput


def _mock_synthesis_output() -> SynthesisOutput:
    return SynthesisOutput(
        insights=[
            InsightOutput(
                category="gap",
                title="Testing gap in MCP ecosystem",
                summary="No standard testing framework for MCP servers despite 16K+ servers.",
                evidence=["sig-mock001"],
                confidence=0.85,
                domains=["mcp", "testing"],
                implications=["Testing framework needed"],
                time_horizon="near_term",
            ),
        ]
    )


def _mock_ideation_output() -> IdeationOutput:
    return IdeationOutput(
        ideas=[
            BuildableUnitOutput(
                title="MCP Test Runner",
                one_liner="Automated testing for MCP servers",
                category="cli_tool",
                problem="No standard way to test MCP servers",
                solution="CLI that validates MCP protocol compliance",
                target_users="both",
                value_proposition="Reduce MCP server bugs by 80%",
                inspiring_insights=["ins-mock001"],
                tech_approach="TypeScript CLI with protocol validation",
                suggested_stack={"language": "typescript"},
                composability_notes="Integrates with CI/CD",
            ),
        ]
    )


def _mock_evaluation_output() -> EvaluationOutput:
    def score(v: float) -> DimensionScoreOutput:
        return DimensionScoreOutput(value=v, confidence=0.7, reasoning="Mock reasoning")

    return EvaluationOutput(
        pain_severity=score(8.0),
        addressable_scale=score(7.0),
        build_effort=score(7.5),
        composability=score(8.5),
        competitive_density=score(9.0),
        timing_fit=score(8.0),
        compounding_value=score(7.0),
        strengths=["High demand", "Low competition"],
        weaknesses=["Niche audience"],
        recommendation="yes",
    )


def _mock_spec_output() -> SpecOutput:
    return SpecOutput(
        name="mcp-test-runner",
        vision="Automated MCP server testing",
        goals=[GoalOutput(id="G-1", description="Validate MCP compliance", success_criteria="100% protocol coverage")],
        tech_stack=TechStackOutput(languages=["TypeScript"], frameworks=["Node.js"], infrastructure=["npm"]),
        constraints=["MVP scope only"],
        patterns=[PatternOutput(name="Plugin", description="Pluggable test suites", scope=["tests"])],
        invariants=["Tests must be deterministic"],
        conventions=["kebab-case files"],
        decisions=[DecisionOutput(id="ADR-1", title="Use stdio transport", decision="stdio", rationale="Most common")],
        requirements=[
            RequirementOutput(
                title="Implement protocol validator",
                priority="critical",
                description="Core validation engine",
                acceptance_criteria=["Validates initialize", "Validates tool listing"],
            ),
            RequirementOutput(
                title="Add CLI interface",
                priority="high",
                description="CLI entry point",
                acceptance_criteria=["Supports --verbose flag", "Returns exit code"],
                dependencies=["Implement protocol validator"],
            ),
        ],
    )


# Track which structured_call invocations happen
_call_count = 0


def _mock_structured_call(system, prompt, output_type, **kwargs):
    global _call_count
    _call_count += 1
    type_name = output_type.__name__

    if type_name == "SynthesisOutput":
        return _mock_synthesis_output()
    elif type_name == "IdeationOutput":
        return _mock_ideation_output()
    elif type_name == "EvaluationOutput":
        return _mock_evaluation_output()
    elif type_name == "SpecOutput":
        return _mock_spec_output()
    else:
        raise ValueError(f"Unexpected output_type in mock: {type_name}")


def _mock_hn_item(story_id: int, title: str) -> dict:
    return {
        "id": story_id, "type": "story", "title": title,
        "url": f"https://example.com/{story_id}", "by": "user",
        "time": 1711000000, "score": 200, "descendants": 30,
    }


@pytest.fixture(autouse=True)
def reset_call_count():
    global _call_count
    _call_count = 0


def test_full_pipeline_with_mocks(tmp_path: Path) -> None:
    """Run the full pipeline with mocked LLM and HTTP, verify output structure."""
    db_path = str(tmp_path / "test.db")
    output_dir = tmp_path / ".tact"

    # Mock HTTP for source adapters
    hn_responses = {
        "topstories.json": MagicMock(json=lambda: [1, 2], raise_for_status=lambda: None),
        "item/1.json": MagicMock(json=lambda: _mock_hn_item(1, "AI Agent Framework"), raise_for_status=lambda: None),
        "item/2.json": MagicMock(json=lambda: _mock_hn_item(2, "MCP Security Audit"), raise_for_status=lambda: None),
    }
    npm_response = MagicMock(
        json=lambda: {"objects": [{"package": {"name": "test-mcp", "description": "test", "version": "1.0.0"}, "searchScore": 50000}]},
        raise_for_status=lambda: None,
    )

    async def mock_get(url: str, **kwargs) -> MagicMock:
        for key, resp in hn_responses.items():
            if url.endswith(key):
                return resp
        return npm_response

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("max.sources.hackernews.httpx.AsyncClient", return_value=mock_client),
        patch("max.sources.npm_registry.httpx.AsyncClient", return_value=mock_client),
        patch("max.llm.client.get_client"),
        patch("max.synthesis.engine.structured_call", side_effect=_mock_structured_call),
        patch("max.ideation.engine.structured_call", side_effect=_mock_structured_call),
        patch("max.evaluation.engine.structured_call", side_effect=_mock_structured_call),
        patch("max.spec.generator.structured_call", side_effect=_mock_structured_call),
        patch("max.store.db.DB_PATH", db_path),
        patch("max.pipeline.runner.Store", lambda: __import__("max.store.db", fromlist=["Store"]).Store(db_path=db_path)),
    ):
        result = run_pipeline(output_dir=output_dir, signal_limit=10, min_score=40.0)

    # Verify pipeline result
    assert isinstance(result, PipelineResult)
    assert result.signals_fetched > 0
    assert result.insights_generated == 1
    assert result.ideas_generated == 1
    assert result.ideas_evaluated == 1
    assert result.specs_generated == 1
    assert len(result.top_ideas) == 1
    assert result.top_ideas[0]["title"] == "MCP Test Runner"
    assert result.top_ideas[0]["recommendation"] == "yes"

    # Verify quality metrics
    assert result.avg_insight_confidence > 0
    assert result.avg_idea_score > 0

    # Verify output files
    project_dir = output_dir / "mcp-test-runner"
    assert project_dir.exists()
    assert (project_dir / "product.yaml").exists()
    assert (project_dir / "architecture.yaml").exists()
    req_files = list((project_dir / "requirements").glob("REQ-*.yaml"))
    assert len(req_files) == 2

    # Verify LLM was called for each stage
    global _call_count
    assert _call_count == 4  # synthesis + ideation + evaluation + spec
