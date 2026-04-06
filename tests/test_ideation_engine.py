"""Unit tests for the ideation engine (insights → buildable units)."""

from __future__ import annotations

from unittest.mock import call, patch

import pytest

from max.ideation.engine import (
    BuildableUnitOutput,
    IdeationOutput,
    _format_existing_ideas,
    _parse_output,
    ideate,
    ideate_cross_domain,
    ideate_refinement,
)
from max.types.buildable_unit import BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_insight(
    id: str = "ins-001",
    category: InsightCategory = InsightCategory.GAP,
    title: str = "Test insight",
    domains: list[str] | None = None,
    evidence: list[str] | None = None,
    **kwargs,
) -> Insight:
    defaults = dict(
        id=id,
        category=category,
        title=title,
        summary="Test summary",
        evidence=evidence or ["sig-001"],
        confidence=0.8,
        domains=domains or ["testing"],
        implications=["Build something"],
        time_horizon="near_term",
    )
    defaults.update(kwargs)
    return Insight(**defaults)


def _make_unit(
    id: str = "unit-001",
    title: str = "Test Unit",
    **kwargs,
) -> BuildableUnit:
    defaults = dict(
        id=id,
        title=title,
        one_liner="A test unit",
        category="cli_tool",
        problem="Something is broken",
        solution="Fix it",
        target_users="both",
        value_proposition="Makes things better",
    )
    defaults.update(kwargs)
    return BuildableUnit(**defaults)


def _ideation_output(ideas: list[BuildableUnitOutput] | None = None) -> IdeationOutput:
    if ideas is not None:
        return IdeationOutput(ideas=ideas)
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
                inspiring_insights=["ins-001"],
                tech_approach="TypeScript CLI",
                suggested_stack={"language": "typescript"},
                composability_notes="CI/CD integration",
            ),
            BuildableUnitOutput(
                title="Agent Orchestrator",
                one_liner="Multi-agent coordination layer",
                category="library",
                problem="Agents can't collaborate easily",
                solution="Shared message bus for agents",
                target_users="agents",
                value_proposition="10x agent interop",
                inspiring_insights=["ins-002"],
                tech_approach="Python async",
                suggested_stack={"language": "python"},
                composability_notes="Plugin architecture",
            ),
        ]
    )


# ---------------------------------------------------------------------------
# ideate() tests
# ---------------------------------------------------------------------------

class TestIdeateEmpty:
    def test_returns_empty_list(self):
        assert ideate([]) == []


class TestIdeateBasicFlow:
    @patch("max.ideation.engine.structured_call")
    def test_returns_correct_number_of_units(self, mock_call):
        mock_call.return_value = _ideation_output()
        insights = [
            _make_insight(id="ins-001"),
            _make_insight(id="ins-002"),
        ]

        result = ideate(insights)

        assert len(result) == 2
        assert all(isinstance(u, BuildableUnit) for u in result)

    @patch("max.ideation.engine.structured_call")
    def test_ideation_mode_is_direct(self, mock_call):
        mock_call.return_value = _ideation_output()
        result = ideate([_make_insight()])

        assert all(u.ideation_mode == IdeationMode.DIRECT for u in result)

    @patch("max.ideation.engine.structured_call")
    def test_valid_target_users_accepted(self, mock_call):
        for target in ("humans", "agents", "both"):
            mock_call.return_value = _ideation_output(
                ideas=[
                    BuildableUnitOutput(
                        title="T",
                        one_liner="o",
                        category="cli_tool",
                        problem="p",
                        solution="s",
                        target_users=target,
                        value_proposition="v",
                    ),
                ]
            )
            result = ideate([_make_insight()])
            assert result[0].target_users == target

    @patch("max.ideation.engine.structured_call")
    def test_invalid_target_users_defaults_to_both(self, mock_call):
        mock_call.return_value = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="T",
                    one_liner="o",
                    category="cli_tool",
                    problem="p",
                    solution="s",
                    target_users="aliens",
                    value_proposition="v",
                ),
            ]
        )
        result = ideate([_make_insight()])
        assert result[0].target_users == "both"

    @patch("max.ideation.engine.structured_call")
    def test_empty_category_defaults_to_application(self, mock_call):
        mock_call.return_value = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="T",
                    one_liner="o",
                    category="",
                    problem="p",
                    solution="s",
                    value_proposition="v",
                ),
            ]
        )
        result = ideate([_make_insight()])
        assert result[0].category == "application"

    @patch("max.ideation.engine.structured_call")
    def test_evidence_signals_traced_through_insight_map(self, mock_call):
        mock_call.return_value = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="T",
                    one_liner="o",
                    category="cli_tool",
                    problem="p",
                    solution="s",
                    value_proposition="v",
                    inspiring_insights=["ins-A", "ins-B"],
                ),
            ]
        )
        insights = [
            _make_insight(id="ins-A", evidence=["sig-1", "sig-2"]),
            _make_insight(id="ins-B", evidence=["sig-2", "sig-3"]),
        ]

        result = ideate(insights)

        # evidence_signals should be the deduplicated union of both insights' evidence
        assert set(result[0].evidence_signals) == {"sig-1", "sig-2", "sig-3"}


# ---------------------------------------------------------------------------
# ideate_refinement() tests
# ---------------------------------------------------------------------------

class TestIdeateRefinement:
    def test_returns_empty_when_no_existing_units(self):
        assert ideate_refinement([], [_make_insight()]) == []

    def test_returns_empty_when_no_new_insights(self):
        assert ideate_refinement([_make_unit()], []) == []

    def test_returns_empty_when_both_empty(self):
        assert ideate_refinement([], []) == []

    @patch("max.ideation.engine.structured_call")
    def test_returns_units_with_refinement_mode(self, mock_call):
        mock_call.return_value = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="Refined",
                    one_liner="Better version",
                    category="cli_tool",
                    problem="p",
                    solution="s",
                    value_proposition="v",
                    inspiring_insights=["ins-001"],
                ),
            ]
        )

        result = ideate_refinement([_make_unit()], [_make_insight()])

        assert len(result) == 1
        assert result[0].ideation_mode == IdeationMode.REFINEMENT


# ---------------------------------------------------------------------------
# ideate_cross_domain() tests
# ---------------------------------------------------------------------------

class TestIdeateCrossDomain:
    def test_returns_empty_for_empty_insights(self):
        assert ideate_cross_domain([]) == []

    def test_returns_empty_when_fewer_than_2_domains(self):
        # All insights in the same domain
        insights = [
            _make_insight(id="ins-1", domains=["ai"]),
            _make_insight(id="ins-2", domains=["ai"]),
        ]
        assert ideate_cross_domain(insights) == []

    def test_returns_empty_for_single_domain_insight(self):
        insights = [_make_insight(id="ins-1", domains=["testing"])]
        assert ideate_cross_domain(insights) == []

    @patch("max.ideation.engine.structured_call")
    def test_groups_by_domain_and_creates_pairs(self, mock_call):
        mock_call.return_value = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="Cross idea",
                    one_liner="Combining domains",
                    category="integration",
                    problem="p",
                    solution="s",
                    value_proposition="v",
                    inspiring_insights=["ins-1"],
                ),
            ]
        )
        insights = [
            _make_insight(id="ins-1", domains=["ai"]),
            _make_insight(id="ins-2", domains=["security"]),
        ]

        result = ideate_cross_domain(insights)

        assert len(result) == 1
        assert mock_call.call_count == 1  # 1 domain pair → 1 LLM call

    @patch("max.ideation.engine.structured_call")
    def test_limits_to_3_domain_pairs(self, mock_call):
        mock_call.return_value = _ideation_output(ideas=[])

        # 4 domains → C(4,2) = 6 pairs, but limited to 3
        insights = [
            _make_insight(id="ins-1", domains=["ai"]),
            _make_insight(id="ins-2", domains=["security"]),
            _make_insight(id="ins-3", domains=["devtools"]),
            _make_insight(id="ins-4", domains=["infrastructure"]),
        ]

        ideate_cross_domain(insights)

        assert mock_call.call_count == 3

    @patch("max.ideation.engine.structured_call")
    def test_sets_cross_domain_mode(self, mock_call):
        mock_call.return_value = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="Cross idea",
                    one_liner="x",
                    category="integration",
                    problem="p",
                    solution="s",
                    value_proposition="v",
                ),
            ]
        )
        insights = [
            _make_insight(id="ins-1", domains=["ai"]),
            _make_insight(id="ins-2", domains=["security"]),
        ]

        result = ideate_cross_domain(insights)

        assert all(u.ideation_mode == IdeationMode.CROSS_DOMAIN for u in result)


# ---------------------------------------------------------------------------
# _parse_output() tests
# ---------------------------------------------------------------------------

class TestParseOutputEvidenceTracing:
    def test_evidence_signals_union_from_inspiring_insights(self):
        output = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="T",
                    one_liner="o",
                    category="cli_tool",
                    problem="p",
                    solution="s",
                    value_proposition="v",
                    inspiring_insights=["ins-A", "ins-B"],
                ),
            ]
        )
        insights = [
            _make_insight(id="ins-A", evidence=["sig-1", "sig-2"]),
            _make_insight(id="ins-B", evidence=["sig-3"]),
        ]

        units = _parse_output(output, insights, IdeationMode.DIRECT)

        assert set(units[0].evidence_signals) == {"sig-1", "sig-2", "sig-3"}

    def test_unknown_inspiring_insight_ids_ignored(self):
        output = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="T",
                    one_liner="o",
                    category="cli_tool",
                    problem="p",
                    solution="s",
                    value_proposition="v",
                    inspiring_insights=["ins-A", "ins-UNKNOWN"],
                ),
            ]
        )
        insights = [_make_insight(id="ins-A", evidence=["sig-1"])]

        units = _parse_output(output, insights, IdeationMode.DIRECT)

        assert set(units[0].evidence_signals) == {"sig-1"}

    def test_deduplicates_evidence_signals(self):
        output = _ideation_output(
            ideas=[
                BuildableUnitOutput(
                    title="T",
                    one_liner="o",
                    category="cli_tool",
                    problem="p",
                    solution="s",
                    value_proposition="v",
                    inspiring_insights=["ins-A", "ins-B"],
                ),
            ]
        )
        # Both insights share sig-1
        insights = [
            _make_insight(id="ins-A", evidence=["sig-1", "sig-2"]),
            _make_insight(id="ins-B", evidence=["sig-1", "sig-3"]),
        ]

        units = _parse_output(output, insights, IdeationMode.DIRECT)

        assert len(units[0].evidence_signals) == 3
        assert set(units[0].evidence_signals) == {"sig-1", "sig-2", "sig-3"}


# ---------------------------------------------------------------------------
# _format_existing_ideas() tests
# ---------------------------------------------------------------------------

class TestFormatExistingIdeas:
    def test_returns_none_for_empty_list(self):
        assert _format_existing_ideas([]) is None

    def test_returns_formatted_string(self):
        units = [
            _make_unit(title="Alpha", one_liner="First idea"),
            _make_unit(title="Beta", one_liner="Second idea"),
        ]

        result = _format_existing_ideas(units)

        assert result == "- Alpha: First idea\n- Beta: Second idea"

    def test_single_unit(self):
        units = [_make_unit(title="Solo", one_liner="Only one")]
        result = _format_existing_ideas(units)
        assert result == "- Solo: Only one"
