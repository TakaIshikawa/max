"""Integration test — full pipeline with mocked LLM and mocked HTTP."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.evaluation.weights import DEFAULT_WEIGHTS
from max.pipeline.runner import PipelineResult, run_pipeline
from max.store.db import Store
from max.synthesis.engine import SynthesisOutput, InsightOutput
from max.ideation.engine import IdeationOutput, BuildableUnitOutput
from max.evaluation.engine import EvaluationOutput, DimensionScoreOutput
from max.spec.generator import SpecOutput, GoalOutput, TechStackOutput, PatternOutput, DecisionOutput, RequirementOutput
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


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


# Track structured_call invocations — count + captured prompts by stage
_call_count = 0
_captured_calls: list[dict] = []


def _mock_structured_call(system, prompt, output_type, **kwargs):
    global _call_count
    _call_count += 1
    type_name = output_type.__name__

    _captured_calls.append({"stage": type_name, "system": system, "prompt": prompt})

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
    global _call_count, _captured_calls
    _call_count = 0
    _captured_calls = []


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

    # Verify new pipeline features
    assert result.weights_adapted is False  # No feedback seeded → static weights

    # Meta-intelligence fields populated (limited data → small values, but present)
    assert isinstance(result.clusters_found, int) and result.clusters_found >= 0
    assert isinstance(result.multi_source_clusters, int)
    assert isinstance(result.gaps_detected, int)


def _make_store(db_path: str) -> Store:
    """Create a Store for the given db_path (used as pipeline mock target)."""
    return Store(db_path=db_path)


def _seed_feedback_data(db_path: str) -> None:
    """Seed the DB with signals, insights, units, evaluations, and mixed feedback."""
    store = Store(db_path=db_path)

    def _dim(v: float) -> DimensionScore:
        return DimensionScore(value=v, confidence=0.7, reasoning="test")

    # Seed a few units with evaluations + feedback
    for i, (outcome, pain, effort) in enumerate([
        ("approved", 9.0, 8.0),
        ("approved", 8.0, 7.0),
        ("rejected", 3.0, 2.0),
        ("rejected", 4.0, 3.0),
    ]):
        uid = f"bu-fb-{i:03d}"
        store.insert_buildable_unit(BuildableUnit(
            id=uid,
            title=f"Feedback Unit {i}",
            one_liner=f"Unit {i} one liner",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem=f"Problem {i}",
            solution=f"Solution {i}",
            value_proposition=f"Value {i}",
        ))
        store.insert_evaluation(UtilityEvaluation(
            buildable_unit_id=uid,
            pain_severity=_dim(pain),
            addressable_scale=_dim(7.0),
            build_effort=_dim(effort),
            composability=_dim(7.0),
            competitive_density=_dim(7.0),
            timing_fit=_dim(7.0),
            compounding_value=_dim(6.0),
            overall_score=70.0,
            strengths=["good"],
            weaknesses=["bad"],
            recommendation="maybe",
            weights_used=DEFAULT_WEIGHTS,
        ))
        store.insert_feedback(uid, outcome, reason=f"test feedback {i}")

    store.close()


def _seed_evidence_data(db_path: str) -> None:
    """Seed DB with signals and insights so evidence chain resolves during evaluation."""
    store = Store(db_path=db_path)

    store.insert_signal(Signal(
        id="sig-mock001",
        source_type=SignalSourceType.FORUM,
        source_adapter="hackernews",
        title="MCP ecosystem lacks testing",
        content="Discussion about MCP server quality — no standard testing exists.",
        url="https://example.com/evidence-signal",
        tags=["mcp", "testing"],
        credibility=0.8,
    ))

    store.insert_insight(Insight(
        id="ins-mock001",
        category=InsightCategory.GAP,
        title="Testing gap in MCP ecosystem",
        summary="No standard testing framework for MCP servers.",
        evidence=["sig-mock001"],
        confidence=0.85,
        domains=["mcp", "testing"],
    ))

    store.close()


def test_pipeline_with_feedback_adapts_weights(tmp_path: Path) -> None:
    """Pipeline uses feedback-adapted weights when DB has mixed feedback."""
    db_path = str(tmp_path / "test_fb.db")

    # Seed feedback data before pipeline runs
    _seed_feedback_data(db_path)

    # Mock HTTP
    hn_responses = {
        "topstories.json": MagicMock(json=lambda: [1], raise_for_status=lambda: None),
        "item/1.json": MagicMock(json=lambda: _mock_hn_item(1, "AI Framework"), raise_for_status=lambda: None),
    }
    npm_response = MagicMock(
        json=lambda: {"objects": []},
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
        patch("max.pipeline.runner.Store", lambda: _make_store(db_path)),
    ):
        result = run_pipeline(output_dir=None, signal_limit=5, min_score=40.0)

    assert result.weights_adapted is True


def test_pipeline_ideation_receives_existing_ideas(tmp_path: Path) -> None:
    """When DB has existing ideas, ideation prompt includes EXISTING IDEAS block."""
    db_path = str(tmp_path / "test_memory.db")

    # Seed existing ideas
    store = Store(db_path=db_path)
    store.insert_buildable_unit(BuildableUnit(
        id="bu-existing-001",
        title="MCP Registry",
        one_liner="Discovery hub for MCP servers",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Hard to find MCP servers",
        solution="Central registry with search",
        value_proposition="Find any MCP server instantly",
    ))
    store.close()

    # Mock HTTP
    hn_responses = {
        "topstories.json": MagicMock(json=lambda: [1], raise_for_status=lambda: None),
        "item/1.json": MagicMock(json=lambda: _mock_hn_item(1, "AI Framework"), raise_for_status=lambda: None),
    }
    npm_response = MagicMock(
        json=lambda: {"objects": []},
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
        patch("max.pipeline.runner.Store", lambda: _make_store(db_path)),
    ):
        run_pipeline(output_dir=None, signal_limit=5, min_score=40.0)

    # Find the ideation call and check its prompt includes existing ideas
    ideation_calls = [c for c in _captured_calls if c["stage"] == "IdeationOutput"]
    assert len(ideation_calls) >= 1
    assert "EXISTING IDEAS" in ideation_calls[0]["prompt"]
    assert "MCP Registry" in ideation_calls[0]["prompt"]


def test_pipeline_evaluation_receives_evidence(tmp_path: Path) -> None:
    """When evidence chain resolves, evaluation prompt includes SUPPORTING EVIDENCE."""
    db_path = str(tmp_path / "test_evidence.db")

    # Seed evidence data (signal + insight that the mock ideation output references)
    _seed_evidence_data(db_path)

    # Mock HTTP
    hn_responses = {
        "topstories.json": MagicMock(json=lambda: [1], raise_for_status=lambda: None),
        "item/1.json": MagicMock(json=lambda: _mock_hn_item(1, "AI Framework"), raise_for_status=lambda: None),
    }
    npm_response = MagicMock(
        json=lambda: {"objects": []},
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
        patch("max.pipeline.runner.Store", lambda: _make_store(db_path)),
    ):
        run_pipeline(output_dir=None, signal_limit=5, min_score=40.0)

    # Find evaluation call and check its prompt includes evidence
    eval_calls = [c for c in _captured_calls if c["stage"] == "EvaluationOutput"]
    assert len(eval_calls) >= 1
    eval_prompt = eval_calls[0]["prompt"]
    assert "SUPPORTING EVIDENCE" in eval_prompt
    assert "sig-mock001" in eval_prompt
    assert "ins-mock001" in eval_prompt


# ── Meta-intelligence e2e test ─────────────────────────────────────


def test_pipeline_meta_intelligence_features(tmp_path: Path) -> None:
    """E2E: signal roles, triangulation, gap detection, and prompt threading.

    Patches _fetch_all_signals to inject diverse signals from multiple adapters,
    then verifies the full meta-intelligence pipeline:
    - Roles annotated correctly and persisted to store
    - Triangulation produces clusters (including multi-source)
    - Gap detection finds validated unmet needs
    - Synthesis prompt includes signal_role data and role-aware instructions
    - Ideation prompt includes gaps context when gaps are detected
    """
    db_path = str(tmp_path / "test_meta.db")
    output_dir = tmp_path / ".tact"

    # Diverse signals from 5 adapters — designed to produce meaningful clusters and gaps.
    # NOTE: Clustering uses hash-based trigram embeddings (not real semantic embeddings).
    # To ensure clustering, overlapping signals share nearly identical text — only minor
    # word differences so their trigram vectors are very similar (cosine > 0.65).
    shared_content = (
        "MCP server testing framework needed. There is no standard way to validate "
        "MCP servers. Developers have to write custom test harnesses for every server. "
        "The MCP ecosystem needs a standardized testing and validation approach."
    )
    mock_signals = [
        # Problem cluster: "MCP testing" from 2 adapters (near-identical content → will cluster)
        Signal(
            id="sig-m01",
            source_type=SignalSourceType.FORUM,
            source_adapter="github_issues",
            title="MCP server testing framework needed urgently",
            content=shared_content,
            url="https://github.com/example/issues/101",
            credibility=0.8,
        ),
        Signal(
            id="sig-m02",
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="MCP server testing framework still missing and broken",
            content="MCP server testing framework still missing. " + shared_content[len("MCP server testing framework needed. "):],
            url="https://news.ycombinator.com/item?id=200",
            credibility=0.7,
        ),
        # Another problem — different topic (AI agent auth)
        Signal(
            id="sig-m03",
            source_type=SignalSourceType.SECURITY,
            source_adapter="security_advisories",
            title="Critical authentication vulnerability in AI agent framework",
            content="Authentication bypass discovered in a popular AI agent framework.",
            url="https://ghsa.example.com/GHSA-0001",
            credibility=0.9,
        ),
        # Solution — unrelated topic (won't match MCP testing problems)
        Signal(
            id="sig-m04",
            source_type=SignalSourceType.REGISTRY,
            source_adapter="npm_registry",
            title="react-form-validator library v3 released",
            content="Popular React form validation library gets major update with new API.",
            url="https://www.npmjs.com/package/react-form-validator",
            credibility=0.6,
        ),
        # Market signal
        Signal(
            id="sig-m05",
            source_type=SignalSourceType.TRENDING,
            source_adapter="product_hunt",
            title="AI developer tools market sees rapid growth",
            content="The AI developer tools market raised $2 billion in funding this quarter.",
            url="https://producthunt.com/posts/ai-market-growth",
            credibility=0.5,
        ),
    ]

    with (
        patch("max.pipeline.runner._fetch_all_signals", return_value=(mock_signals, {"mock": 5})),
        patch("max.llm.client.get_client"),
        patch("max.synthesis.engine.structured_call", side_effect=_mock_structured_call),
        patch("max.ideation.engine.structured_call", side_effect=_mock_structured_call),
        patch("max.evaluation.engine.structured_call", side_effect=_mock_structured_call),
        patch("max.spec.generator.structured_call", side_effect=_mock_structured_call),
        patch("max.store.db.DB_PATH", db_path),
        patch("max.pipeline.runner.Store", lambda: _make_store(db_path)),
    ):
        result = run_pipeline(output_dir=output_dir, signal_limit=10, min_score=40.0)

    # ── 1. Signal role annotation ──────────────────────────────────
    store = Store(db_path=db_path)
    try:
        problems = store.get_signals_by_role("problem")
        solutions = store.get_signals_by_role("solution")
        markets = store.get_signals_by_role("market")
    finally:
        store.close()

    # github_issues → problem (default), hackernews → problem (keywords: "frustrating", "broken", "crash"),
    # security_advisories → problem (default)
    assert len(problems) == 3, f"Expected 3 problems, got {len(problems)}: {[s.title for s in problems]}"
    # npm_registry → solution (default)
    assert len(solutions) == 1
    # product_hunt → market (default)
    assert len(markets) == 1

    assert result.signals_fetched == 5
    assert result.signals_new == 5

    # ── 2. Triangulation ───────────────────────────────────────────
    # 5 signals should produce at least 1 cluster
    assert result.clusters_found >= 1

    # ── 3. Gap detection ───────────────────────────────────────────
    # 3 problem signals (MCP testing + AI auth) vs 1 unrelated solution (react-form)
    # → at least the MCP testing cluster should be a gap
    assert result.gaps_detected >= 1, f"Expected >= 1 gap, got {result.gaps_detected}"

    # ── 4. Synthesis prompt: signal_role included in signal JSON ───
    synth_calls = [c for c in _captured_calls if c["stage"] == "SynthesisOutput"]
    assert len(synth_calls) == 1
    synth_prompt = synth_calls[0]["prompt"]
    # Signal JSON includes signal_role for each signal
    assert "signal_role" in synth_prompt
    # Should contain actual role values from annotated signals
    assert '"problem"' in synth_prompt

    # ── 5. Synthesis system prompt: role-aware instructions ────────
    synth_system = synth_calls[0]["system"]
    assert "problem" in synth_system
    assert "solution" in synth_system

    # ── 6. Ideation prompt: gaps context threaded through ──────────
    ideation_calls = [c for c in _captured_calls if c["stage"] == "IdeationOutput"]
    assert len(ideation_calls) >= 1
    ideation_prompt = ideation_calls[0]["prompt"]
    # When gaps are detected, ideation prompt should contain gaps block
    assert "VALIDATED UNMET NEEDS" in ideation_prompt
    assert "Prioritize ideas" in ideation_prompt

    # ── 7. Standard pipeline assertions still hold ─────────────────
    assert result.insights_generated == 1
    assert result.ideas_generated == 1
    assert result.ideas_evaluated == 1
    assert result.specs_generated == 1
    assert result.avg_insight_confidence > 0
    assert result.avg_idea_score > 0

    # Output files created
    project_dir = output_dir / "mcp-test-runner"
    assert project_dir.exists()
