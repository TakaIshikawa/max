"""Unit tests for src/max/ideation/prompts.py prompt builders."""

from __future__ import annotations

import pytest

from max.ideation.prompts import (
    _DEFAULT_SYSTEM,
    build_cross_domain_prompt,
    build_ideation_prompt,
    build_refinement_prompt,
    get_system_prompt,
)
from max.profiles.schema import DomainContext


@pytest.fixture
def mock_domain_minimal() -> DomainContext:
    """Domain context with no extra_instructions."""
    return DomainContext(
        name="test-domain",
        description="test domain for unit testing",
        categories=["tool", "library"],
        target_user_types=["developers", "testers"],
    )


@pytest.fixture
def mock_domain_with_extra() -> DomainContext:
    """Domain context with extra_instructions."""
    return DomainContext(
        name="healthcare",
        description="healthcare and medical systems",
        categories=["diagnostic_tool", "patient_portal", "integration"],
        target_user_types=["clinicians", "patients", "both"],
        extra_instructions="Focus on HIPAA-compliant solutions with audit trails.",
    )


@pytest.fixture
def sample_insights_json() -> str:
    """Sample insights JSON for testing."""
    return """{
  "insights": [
    {"id": "ins-1", "category": "gap", "description": "missing X"},
    {"id": "ins-2", "category": "trend", "description": "shift toward Y"}
  ]
}"""


@pytest.fixture
def sample_existing_ideas_text() -> str:
    """Sample existing ideas text."""
    return "- Idea A: Build a CLI for Z\n- Idea B: MCP server for W"


@pytest.fixture
def sample_gaps_text() -> str:
    """Sample gaps text."""
    return "GAP ANALYSIS:\n- No tools exist for scenario X\n- Limited agent support for Y"


@pytest.fixture
def sample_learned_context() -> str:
    """Sample learned context text."""
    return "LEARNED CONTEXT:\n- Users prefer CLI over GUI\n- Agent adoption is accelerating"


@pytest.fixture
def sample_existing_units_json() -> str:
    """Sample existing buildable units JSON."""
    return """{
  "units": [
    {"id": "unit-1", "category": "cli_tool", "problem": "manual task X"}
  ]
}"""


@pytest.fixture
def sample_new_insights_json() -> str:
    """Sample new insights JSON for refinement."""
    return """{
  "insights": [
    {"id": "ins-3", "category": "pain_point", "description": "task X now more critical"}
  ]
}"""


@pytest.fixture
def sample_domain_a_insights_json() -> str:
    """Sample insights from domain A."""
    return """{
  "insights": [
    {"id": "a-1", "domain": "A", "description": "pattern P in domain A"}
  ]
}"""


@pytest.fixture
def sample_domain_b_insights_json() -> str:
    """Sample insights from domain B."""
    return """{
  "insights": [
    {"id": "b-1", "domain": "B", "description": "solution S in domain B"}
  ]
}"""


class TestGetSystemPrompt:
    """Tests for get_system_prompt()."""

    def test_no_domain_returns_default(self):
        """Should return _DEFAULT_SYSTEM when no domain provided."""
        result = get_system_prompt(domain=None)
        assert result == _DEFAULT_SYSTEM
        assert "product ideation engine" in result
        assert "developer tools and AI agent ecosystem" in result
        assert "mcp_server" in result
        assert "cli_tool" in result
        assert "Target users: humans | agents | both" in result

    def test_with_domain_categories_and_targets(self, mock_domain_minimal):
        """Should include domain categories and target_user_types."""
        result = get_system_prompt(domain=mock_domain_minimal)
        assert "test domain for unit testing" in result
        assert "- tool" in result
        assert "- library" in result
        assert "developers | testers" in result
        # Should not have default categories
        assert "mcp_server" not in result
        assert "humans | agents | both" not in result

    def test_with_domain_with_extra_instructions(self, mock_domain_with_extra):
        """Should include domain description and extra_instructions."""
        result = get_system_prompt(domain=mock_domain_with_extra)
        assert "healthcare and medical systems" in result
        assert "- diagnostic_tool" in result
        assert "- patient_portal" in result
        assert "- integration" in result
        assert "clinicians | patients | both" in result
        assert "Focus on HIPAA-compliant solutions with audit trails." in result


class TestBuildIdeationPrompt:
    """Tests for build_ideation_prompt()."""

    def test_minimal_params(self, sample_insights_json):
        """Should build prompt with insights only, no optional blocks."""
        result = build_ideation_prompt(sample_insights_json)
        assert "INSIGHTS:" in result
        assert sample_insights_json in result
        assert "EXISTING IDEAS" not in result
        assert "GAP ANALYSIS" not in result
        assert "LEARNED CONTEXT" not in result
        assert "the developer/AI ecosystem" in result
        assert "humans, agents, or both" in result
        assert "Generate 3-5 distinct ideas" in result

    def test_with_existing_ideas(self, sample_insights_json, sample_existing_ideas_text):
        """Should include existing ideas block when provided."""
        result = build_ideation_prompt(
            sample_insights_json, existing_ideas_text=sample_existing_ideas_text
        )
        assert "EXISTING IDEAS (do NOT regenerate these" in result
        assert sample_existing_ideas_text in result
        assert "generate DIFFERENT ideas" in result

    def test_with_gaps_text(self, sample_insights_json, sample_gaps_text):
        """Should include gaps block when provided."""
        result = build_ideation_prompt(sample_insights_json, gaps_text=sample_gaps_text)
        assert sample_gaps_text in result
        assert "GAP ANALYSIS" in result

    def test_with_learned_context(self, sample_insights_json, sample_learned_context):
        """Should include learned context block when provided."""
        result = build_ideation_prompt(
            sample_insights_json, learned_context=sample_learned_context
        )
        assert sample_learned_context in result
        assert "LEARNED CONTEXT" in result

    def test_with_domain(self, sample_insights_json, mock_domain_with_extra):
        """Should use domain-specific labels when domain provided."""
        result = build_ideation_prompt(sample_insights_json, domain=mock_domain_with_extra)
        assert f"the {mock_domain_with_extra.name} domain" in result
        assert "clinicians | patients | both" in result
        assert "the developer/AI ecosystem" not in result
        assert "humans, agents, or both" not in result

    def test_with_all_optional_params(
        self,
        sample_insights_json,
        sample_existing_ideas_text,
        sample_gaps_text,
        sample_learned_context,
        mock_domain_minimal,
    ):
        """Should include all optional blocks when all params provided."""
        result = build_ideation_prompt(
            sample_insights_json,
            existing_ideas_text=sample_existing_ideas_text,
            gaps_text=sample_gaps_text,
            learned_context=sample_learned_context,
            domain=mock_domain_minimal,
        )
        assert "LEARNED CONTEXT" in result
        assert sample_learned_context in result
        assert "EXISTING IDEAS" in result
        assert sample_existing_ideas_text in result
        assert sample_gaps_text in result
        assert "INSIGHTS:" in result
        assert sample_insights_json in result
        assert f"the {mock_domain_minimal.name} domain" in result
        assert "developers | testers" in result


class TestBuildRefinementPrompt:
    """Tests for build_refinement_prompt()."""

    def test_refinement_prompt_structure(
        self, sample_existing_units_json, sample_new_insights_json
    ):
        """Should build refinement prompt with existing units and new insights."""
        result = build_refinement_prompt(
            sample_existing_units_json, sample_new_insights_json
        )
        assert "EXISTING IDEAS:" in result
        assert sample_existing_units_json in result
        assert "NEW INSIGHTS:" in result
        assert sample_new_insights_json in result
        assert "IMPROVE it" in result
        assert "PIVOT it" in result
        assert "KEEP it unchanged" in result
        assert "Return 2-4 refined ideas" in result
        assert "Reference the original idea's ID" in result


class TestBuildCrossDomainPrompt:
    """Tests for build_cross_domain_prompt()."""

    def test_minimal_params(
        self, sample_domain_a_insights_json, sample_domain_b_insights_json
    ):
        """Should build cross-domain prompt with both domain insights, no optional blocks."""
        result = build_cross_domain_prompt(
            sample_domain_a_insights_json, sample_domain_b_insights_json
        )
        assert "DOMAIN A INSIGHTS:" in result
        assert sample_domain_a_insights_json in result
        assert "DOMAIN B INSIGHTS:" in result
        assert sample_domain_b_insights_json in result
        assert "combining insights from TWO DIFFERENT domains" in result
        assert "EXISTING IDEAS" not in result
        assert "LEARNED CONTEXT" not in result
        assert "Generate 2-4 cross-domain ideas" in result

    def test_with_existing_ideas(
        self,
        sample_domain_a_insights_json,
        sample_domain_b_insights_json,
        sample_existing_ideas_text,
    ):
        """Should include existing ideas block when provided."""
        result = build_cross_domain_prompt(
            sample_domain_a_insights_json,
            sample_domain_b_insights_json,
            existing_ideas_text=sample_existing_ideas_text,
        )
        assert "EXISTING IDEAS (do NOT regenerate these" in result
        assert sample_existing_ideas_text in result

    def test_with_gaps_text(
        self, sample_domain_a_insights_json, sample_domain_b_insights_json, sample_gaps_text
    ):
        """Should include gaps block when provided."""
        result = build_cross_domain_prompt(
            sample_domain_a_insights_json,
            sample_domain_b_insights_json,
            gaps_text=sample_gaps_text,
        )
        assert sample_gaps_text in result

    def test_with_learned_context(
        self,
        sample_domain_a_insights_json,
        sample_domain_b_insights_json,
        sample_learned_context,
    ):
        """Should include learned context block when provided."""
        result = build_cross_domain_prompt(
            sample_domain_a_insights_json,
            sample_domain_b_insights_json,
            learned_context=sample_learned_context,
        )
        assert sample_learned_context in result

    def test_with_all_optional_params(
        self,
        sample_domain_a_insights_json,
        sample_domain_b_insights_json,
        sample_existing_ideas_text,
        sample_gaps_text,
        sample_learned_context,
        mock_domain_minimal,
    ):
        """Should include all optional blocks when all params provided."""
        result = build_cross_domain_prompt(
            sample_domain_a_insights_json,
            sample_domain_b_insights_json,
            existing_ideas_text=sample_existing_ideas_text,
            gaps_text=sample_gaps_text,
            learned_context=sample_learned_context,
            domain=mock_domain_minimal,
        )
        assert "LEARNED CONTEXT" in result
        assert sample_learned_context in result
        assert "EXISTING IDEAS" in result
        assert sample_existing_ideas_text in result
        assert sample_gaps_text in result
        assert "DOMAIN A INSIGHTS:" in result
        assert "DOMAIN B INSIGHTS:" in result
        assert "cross-domain connection" in result
        assert "1+1=3 effect" in result
