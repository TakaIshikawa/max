"""Tests for ideation memory — existing ideas injected into prompts."""

from __future__ import annotations

from unittest.mock import patch

from max.ideation.engine import _format_existing_ideas
from max.ideation.prompts import build_cross_domain_prompt, build_ideation_prompt
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def _make_unit(id: str, title: str, one_liner: str) -> BuildableUnit:
    return BuildableUnit(
        id=id,
        title=title,
        one_liner=one_liner,
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="some problem",
        solution="some solution",
        value_proposition="some value",
    )


# ── _format_existing_ideas ────────────────────────────────────────


def test_format_empty_list():
    assert _format_existing_ideas([]) is None


def test_format_single_idea():
    units = [_make_unit("bu-001", "MCP Registry", "Discovery hub for MCP servers")]
    result = _format_existing_ideas(units)
    assert result == "- MCP Registry: Discovery hub for MCP servers"


def test_format_multiple_ideas():
    units = [
        _make_unit("bu-001", "MCP Registry", "Discovery hub"),
        _make_unit("bu-002", "AI Guard", "Runtime security"),
    ]
    result = _format_existing_ideas(units)
    assert "- MCP Registry: Discovery hub" in result
    assert "- AI Guard: Runtime security" in result
    assert result.count("\n") == 1  # Two lines, one newline


# ── Prompt injection ──────────────────────────────────────────────


def test_ideation_prompt_without_existing():
    prompt = build_ideation_prompt('{"insights": []}')
    assert "EXISTING IDEAS" not in prompt


def test_ideation_prompt_with_existing():
    existing = "- MCP Registry: Discovery hub\n- AI Guard: Security proxy"
    prompt = build_ideation_prompt('{"insights": []}', existing_ideas_text=existing)
    assert "EXISTING IDEAS" in prompt
    assert "do NOT regenerate" in prompt
    assert "MCP Registry" in prompt
    assert "AI Guard" in prompt


def test_cross_domain_prompt_without_existing():
    prompt = build_cross_domain_prompt('{"a": []}', '{"b": []}')
    assert "EXISTING IDEAS" not in prompt


def test_cross_domain_prompt_with_existing():
    existing = "- MCP Registry: Discovery hub"
    prompt = build_cross_domain_prompt('{"a": []}', '{"b": []}', existing_ideas_text=existing)
    assert "EXISTING IDEAS" in prompt
    assert "MCP Registry" in prompt


# ── Engine integration ────────────────────────────────────────────


def test_ideate_passes_existing_ideas_to_prompt():
    """ideate() passes existing_ideas through to prompt builder."""
    from max.ideation.engine import ideate
    from max.types.insight import Insight, InsightCategory

    insights = [
        Insight(
            id="ins-001",
            category=InsightCategory.GAP,
            title="Test gap",
            summary="A test gap",
            evidence=["sig-001"],
            confidence=0.8,
            domains=["testing"],
        )
    ]
    existing = [_make_unit("bu-001", "MCP Registry", "Discovery hub")]

    mock_result = type("IdeationOutput", (), {"ideas": []})()

    with patch("max.ideation.engine.structured_call", return_value=mock_result) as mock_call:
        ideate(insights, existing_ideas=existing)

    call_kwargs = mock_call.call_args
    prompt = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt", call_kwargs[0][1])
    assert "EXISTING IDEAS" in prompt
    assert "MCP Registry" in prompt


def test_ideate_without_existing_ideas_no_block():
    """ideate() without existing_ideas doesn't inject EXISTING IDEAS block."""
    from max.ideation.engine import ideate
    from max.types.insight import Insight, InsightCategory

    insights = [
        Insight(
            id="ins-001",
            category=InsightCategory.GAP,
            title="Test gap",
            summary="A test gap",
            evidence=["sig-001"],
            confidence=0.8,
            domains=["testing"],
        )
    ]

    mock_result = type("IdeationOutput", (), {"ideas": []})()

    with patch("max.ideation.engine.structured_call", return_value=mock_result) as mock_call:
        ideate(insights)

    call_kwargs = mock_call.call_args
    prompt = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt", call_kwargs[0][1])
    assert "EXISTING IDEAS" not in prompt
