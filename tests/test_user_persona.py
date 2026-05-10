"""Tests for user persona document export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from max.exports.user_persona import (
    SCHEMA_VERSION,
    KIND,
    build_user_personas,
    render_user_personas_json,
    render_user_personas_markdown,
    _extract_goals,
    _extract_pain_points,
    _extract_tech_preferences,
    _extract_behavior_patterns,
    _generate_persona_name,
    _group_by_user_archetype,
    _infer_archetype,
)
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    *,
    unit_id: str = "bu-001",
    title: str = "Test Unit",
    problem: str = "Testing is hard",
    solution: str = "Automate everything",
    value_proposition: str = "Save time on testing",
    specific_user: str = "",
    target_users: str = "both",
    domain: str = "devtools",
    buyer: str = "",
    current_workaround: str = "",
    why_now: str = "",
    quality_score: float = 0.5,
    evidence_signals: list[str] | None = None,
    suggested_stack: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.problem = problem
    unit.solution = solution
    unit.value_proposition = value_proposition
    unit.specific_user = specific_user
    unit.target_users = target_users
    unit.domain = domain
    unit.buyer = buyer
    unit.current_workaround = current_workaround
    unit.why_now = why_now
    unit.quality_score = quality_score
    unit.evidence_signals = evidence_signals or []
    unit.suggested_stack = suggested_stack or {}
    return unit


def _make_signal(
    *,
    signal_id: str = "sig-001",
    title: str = "Test Signal",
    content: str = "Some content",
    source_type: SignalSourceType = SignalSourceType.FORUM,
    tags: list[str] | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        title=title,
        content=content,
        source_type=source_type,
        source_adapter="test_adapter",
        url="https://example.com",
        tags=tags or [],
    )


def _mock_store(
    units: list | None = None,
    signals: list | None = None,
) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    store.get_signals.return_value = signals or []
    return store


# ── Unit helper tests ────────────────────────────────────────────────


def test_generate_persona_name() -> None:
    assert _generate_persona_name("backend developer") == "Backend Developer"
    assert _generate_persona_name("ai_agent_developer") == "Ai Agent Developer"


def test_infer_archetype_specific_user() -> None:
    unit = _make_unit(specific_user="Data Scientist")
    assert _infer_archetype(unit) == "data scientist"


def test_infer_archetype_agent_target() -> None:
    unit = _make_unit(target_users="agents", specific_user="")
    assert _infer_archetype(unit) == "ai agent developer"


def test_infer_archetype_domain_fallback() -> None:
    unit = _make_unit(specific_user="", target_users="both", domain="security")
    assert _infer_archetype(unit) == "security developer"


def test_infer_archetype_default() -> None:
    unit = _make_unit(specific_user="", target_users="both", domain="")
    assert _infer_archetype(unit) == "developer"


def test_group_by_user_archetype() -> None:
    units = [
        _make_unit(specific_user="DevOps Engineer"),
        _make_unit(specific_user="DevOps Engineer"),
        _make_unit(specific_user="Data Scientist"),
    ]
    groups = _group_by_user_archetype(units)
    assert "devops engineer" in groups
    assert len(groups["devops engineer"]) == 2
    assert "data scientist" in groups
    assert len(groups["data scientist"]) == 1


def test_extract_goals() -> None:
    units = [
        _make_unit(value_proposition="Ship faster"),
        _make_unit(value_proposition="Reduce bugs"),
        _make_unit(value_proposition="Ship faster"),  # duplicate
    ]
    goals = _extract_goals(units)
    assert "Ship faster" in goals
    assert "Reduce bugs" in goals
    assert len(goals) == 2  # deduped


def test_extract_pain_points_from_units() -> None:
    units = [
        _make_unit(problem="Deployment is slow", current_workaround="Manual scripts"),
    ]
    pain_points = _extract_pain_points(units, [])
    assert "Deployment is slow" in pain_points
    assert "Current workaround: Manual scripts" in pain_points


def test_extract_pain_points_from_signals() -> None:
    signals = [
        _make_signal(
            title="Docker builds are frustratingly slow",
            content="It's really frustrating to wait 10 minutes",
        ),
    ]
    pain_points = _extract_pain_points([], signals)
    assert "Docker builds are frustratingly slow" in pain_points


def test_extract_tech_preferences_from_signals() -> None:
    signals = [
        _make_signal(
            title="Using Python with LangChain",
            content="I built a python langchain RAG pipeline",
            tags=["python", "langchain", "rag"],
        ),
    ]
    prefs = _extract_tech_preferences(signals, [])
    assert "python" in prefs["technologies"]
    assert "langchain" in prefs["technologies"]
    assert "python" in prefs["tags"]


def test_extract_tech_preferences_from_stacks() -> None:
    units = [
        _make_unit(suggested_stack={"language": "Rust", "runtime": "Tokio"}),
    ]
    prefs = _extract_tech_preferences([], units)
    assert "rust" in prefs["technologies"]


def test_extract_behavior_patterns() -> None:
    signals = [
        _make_signal(source_type=SignalSourceType.FORUM),
        _make_signal(source_type=SignalSourceType.FORUM),
        _make_signal(source_type=SignalSourceType.ARTICLE),
    ]
    patterns = _extract_behavior_patterns(signals)
    assert any("forum" in p for p in patterns)
    assert any("article" in p for p in patterns)


def test_extract_behavior_patterns_empty() -> None:
    patterns = _extract_behavior_patterns([])
    assert patterns == ["No specific behavior patterns detected"]


# ── Build persona integration tests ──────────────────────────────────


def test_build_user_personas_schema() -> None:
    store = _mock_store()
    result = build_user_personas(store)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert "generated_at" in result
    assert "personas" in result
    assert result["persona_count"] == 0


def test_build_user_personas_with_units() -> None:
    units = [
        _make_unit(
            unit_id="bu-1",
            specific_user="Backend Developer",
            problem="API testing is tedious",
            value_proposition="Automated API testing",
            evidence_signals=["sig-1"],
        ),
        _make_unit(
            unit_id="bu-2",
            specific_user="Backend Developer",
            problem="Deployment pipelines break often",
            value_proposition="Resilient CI/CD",
            evidence_signals=["sig-2"],
        ),
    ]
    signals = [
        _make_signal(signal_id="sig-1", title="REST API testing tools", content="Using python pytest"),
        _make_signal(signal_id="sig-2", title="CI pipeline failures", content="Jenkins is slow and error-prone"),
    ]
    store = _mock_store(units=units, signals=signals)

    result = build_user_personas(store)
    assert result["persona_count"] == 1
    persona = result["personas"][0]
    assert persona["archetype"] == "backend developer"
    assert persona["name"] == "Backend Developer"
    assert len(persona["goals"]) == 2
    assert len(persona["pain_points"]) >= 2
    assert persona["evidence"]["unit_count"] == 2


def test_build_user_personas_multiple_archetypes() -> None:
    units = [
        _make_unit(unit_id="bu-1", specific_user="Data Scientist"),
        _make_unit(unit_id="bu-2", specific_user="DevOps Engineer"),
        _make_unit(unit_id="bu-3", specific_user="Frontend Developer"),
    ]
    store = _mock_store(units=units)

    result = build_user_personas(store)
    assert result["persona_count"] == 3
    archetypes = {p["archetype"] for p in result["personas"]}
    assert "data scientist" in archetypes
    assert "devops engineer" in archetypes
    assert "frontend developer" in archetypes


def test_build_user_personas_max_personas() -> None:
    units = [
        _make_unit(unit_id=f"bu-{i}", specific_user=f"Role {i}")
        for i in range(10)
    ]
    store = _mock_store(units=units)

    result = build_user_personas(store, max_personas=3)
    assert result["persona_count"] <= 3


def test_build_user_personas_fallback_from_signals() -> None:
    """When no units exist, a default persona is built from signals."""
    signals = [
        _make_signal(
            signal_id="sig-1",
            title="Python async patterns",
            content="Using python asyncio for concurrent tasks",
            tags=["python", "async"],
        ),
    ]
    store = _mock_store(signals=signals)

    result = build_user_personas(store)
    assert result["persona_count"] == 1
    persona = result["personas"][0]
    assert persona["archetype"] == "developer"


def test_build_user_personas_domain_filter() -> None:
    store = _mock_store()
    build_user_personas(store, domain="security")
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="security")


def test_build_persona_demographics() -> None:
    units = [
        _make_unit(
            specific_user="ML Engineer",
            domain="ai",
            buyer="Engineering Manager",
            quality_score=0.8,
        ),
    ]
    store = _mock_store(units=units)
    result = build_user_personas(store)
    demo = result["personas"][0]["demographics"]
    assert demo["role"] == "Ml Engineer"
    assert "ai" in demo["domains"]
    assert "Engineering Manager" in demo["buyer_roles"]
    assert demo["experience_level"] == "senior"


def test_build_persona_experience_level_junior() -> None:
    units = [_make_unit(specific_user="Intern", quality_score=0.2)]
    store = _mock_store(units=units)
    result = build_user_personas(store)
    assert result["personas"][0]["demographics"]["experience_level"] == "junior"


# ── Rendering tests ──────────────────────────────────────────────────


def test_render_markdown_contains_sections() -> None:
    units = [
        _make_unit(
            specific_user="Platform Engineer",
            problem="Infra provisioning is painful",
            value_proposition="One-click infrastructure",
            why_now="Cloud costs are rising",
        ),
    ]
    signals = [
        _make_signal(
            signal_id="sig-1",
            title="Terraform modules",
            content="Using terraform and kubernetes for infrastructure",
            tags=["terraform", "k8s"],
            source_type=SignalSourceType.ARTICLE,
        ),
    ]
    store = _mock_store(units=units, signals=[signals[0]])
    # Wire up evidence_signals so the signal is associated
    units[0].evidence_signals = ["sig-1"]

    report = build_user_personas(store)
    md = render_user_personas_markdown(report)

    assert "# User Personas" in md
    assert "## Persona 1:" in md
    assert "### Demographics" in md
    assert "### Goals" in md
    assert "### Pain Points" in md
    assert "### Motivations" in md
    assert "### Technology Preferences" in md
    assert "### Behavior Patterns" in md
    assert "### Evidence" in md


def test_render_markdown_empty_personas() -> None:
    store = _mock_store()
    report = build_user_personas(store)
    md = render_user_personas_markdown(report)
    assert "# User Personas" in md
    assert "Total personas: 0" in md


def test_render_json_valid() -> None:
    units = [_make_unit(specific_user="QA Engineer")]
    store = _mock_store(units=units)
    report = build_user_personas(store)
    json_str = render_user_personas_json(report)
    parsed = json.loads(json_str)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert len(parsed["personas"]) == 1


def test_render_json_roundtrip() -> None:
    """JSON output contains all persona fields."""
    units = [
        _make_unit(
            specific_user="SRE",
            problem="Incidents take too long to resolve",
            value_proposition="Faster incident response",
            why_now="More microservices",
            current_workaround="PagerDuty + manual runbooks",
        ),
    ]
    store = _mock_store(units=units)
    report = build_user_personas(store)
    parsed = json.loads(render_user_personas_json(report))

    persona = parsed["personas"][0]
    assert "demographics" in persona
    assert "goals" in persona
    assert "pain_points" in persona
    assert "motivations" in persona
    assert "technology_preferences" in persona
    assert "behavior_patterns" in persona
    assert "evidence" in persona


# ── Persona completeness test ────────────────────────────────────────


def test_persona_completeness() -> None:
    """Each persona has all required fields populated."""
    units = [
        _make_unit(
            specific_user="Full Stack Dev",
            problem="State management is complex",
            solution="Unified state layer",
            value_proposition="Simpler state management",
            domain="frontend",
            buyer="Tech Lead",
            why_now="React ecosystem fragmentation",
            current_workaround="Redux + context + local state",
            quality_score=0.6,
            evidence_signals=["sig-1"],
            suggested_stack={"framework": "React", "language": "TypeScript"},
        ),
    ]
    signals = [
        _make_signal(
            signal_id="sig-1",
            title="React state management comparison",
            content="Comparing redux, zustand, and jotai for state management",
            tags=["react", "state-management", "typescript"],
            source_type=SignalSourceType.ARTICLE,
        ),
    ]
    store = _mock_store(units=units, signals=signals)

    report = build_user_personas(store)
    assert report["persona_count"] == 1
    persona = report["personas"][0]

    # Verify all top-level keys
    assert persona["name"]
    assert persona["archetype"] == "full stack dev"

    # Demographics
    assert persona["demographics"]["role"]
    assert persona["demographics"]["experience_level"] in ("junior", "mid-level", "senior")
    assert persona["demographics"]["domains"]
    assert persona["demographics"]["buyer_roles"]

    # Goals
    assert len(persona["goals"]) >= 1

    # Pain points
    assert len(persona["pain_points"]) >= 1

    # Technology preferences
    assert len(persona["technology_preferences"]["technologies"]) >= 1

    # Behavior patterns
    assert len(persona["behavior_patterns"]) >= 1

    # Evidence
    assert persona["evidence"]["unit_count"] == 1
    assert persona["evidence"]["signal_count"] == 1
