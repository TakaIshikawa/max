"""Unit tests for src/max/synthesis/prompts.py prompt builders."""

from __future__ import annotations

import pytest

from max.profiles.schema import DomainContext
from max.synthesis.prompts import (
    _DEFAULT_SYSTEM,
    build_incremental_synthesis_prompt,
    build_synthesis_prompt,
    get_system_prompt,
)


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
        categories=["diagnostic_tool", "patient_portal"],
        target_user_types=["clinicians", "patients"],
        extra_instructions="Always prioritize patient safety and HIPAA compliance.",
    )


@pytest.fixture
def sample_signals_json() -> str:
    """Sample signals JSON for testing."""
    return """{
  "signals": [
    {"id": "sig-1", "signal_role": "problem", "content": "users struggle with X"},
    {"id": "sig-2", "signal_role": "solution", "content": "new tool Y launched"}
  ]
}"""


@pytest.fixture
def sample_prior_insights_json() -> str:
    """Sample prior insights JSON for incremental synthesis."""
    return """{
  "insights": [
    {"id": "ins-1", "category": "gap", "description": "missing capability Z"}
  ]
}"""


@pytest.fixture
def sample_cluster_context() -> str:
    """Sample cluster context text."""
    return "Signals sig-1 and sig-2 appear in multi-source cluster C1."


class TestGetSystemPrompt:
    """Tests for get_system_prompt()."""

    def test_no_domain_returns_default(self):
        """Should return _DEFAULT_SYSTEM when no domain provided."""
        result = get_system_prompt(domain=None)
        assert result == _DEFAULT_SYSTEM
        assert "technology analyst" in result
        assert "developer tools, AI/agent ecosystems" in result

    def test_with_domain_no_extra_instructions(self, mock_domain_minimal):
        """Should include domain name and description but no extra block."""
        result = get_system_prompt(domain=mock_domain_minimal)
        assert "test domain for unit testing" in result
        assert mock_domain_minimal.name not in result  # name not used in template
        assert "pain_point" in result
        assert "gap" in result
        # Should not have extra instructions block
        assert mock_domain_minimal.description in result

    def test_with_domain_with_extra_instructions(self, mock_domain_with_extra):
        """Should include domain description and extra_instructions."""
        result = get_system_prompt(domain=mock_domain_with_extra)
        assert "healthcare and medical systems" in result
        assert "Always prioritize patient safety and HIPAA compliance." in result
        assert "technology analyst specializing in" in result


class TestBuildSynthesisPrompt:
    """Tests for build_synthesis_prompt()."""

    def test_minimal_params(self, sample_signals_json):
        """Should build prompt with signals only, no optional blocks."""
        result = build_synthesis_prompt(sample_signals_json)
        assert "SIGNALS:" in result
        assert sample_signals_json in result
        assert "CROSS-SOURCE CORROBORATION:" not in result
        assert "the developer/AI ecosystem" in result
        assert "Return a list of 3-7 insights" in result

    def test_with_cluster_context(self, sample_signals_json, sample_cluster_context):
        """Should include cluster context block when provided."""
        result = build_synthesis_prompt(
            sample_signals_json, cluster_context=sample_cluster_context
        )
        assert "CROSS-SOURCE CORROBORATION:" in result
        assert sample_cluster_context in result
        assert "multi-source clusters are independently corroborated" in result

    def test_with_domain(self, sample_signals_json, mock_domain_with_extra):
        """Should use domain-specific label when domain provided."""
        result = build_synthesis_prompt(sample_signals_json, domain=mock_domain_with_extra)
        assert f"the {mock_domain_with_extra.name} ecosystem" in result
        assert "the developer/AI ecosystem" not in result
        assert "SIGNALS:" in result

    def test_with_all_params(
        self, sample_signals_json, sample_cluster_context, mock_domain_minimal
    ):
        """Should include all optional blocks when all params provided."""
        result = build_synthesis_prompt(
            sample_signals_json,
            cluster_context=sample_cluster_context,
            domain=mock_domain_minimal,
        )
        assert "CROSS-SOURCE CORROBORATION:" in result
        assert sample_cluster_context in result
        assert f"the {mock_domain_minimal.name} ecosystem" in result
        assert sample_signals_json in result


class TestBuildIncrementalSynthesisPrompt:
    """Tests for build_incremental_synthesis_prompt()."""

    def test_minimal_params(self, sample_signals_json, sample_prior_insights_json):
        """Should build incremental prompt with prior insights, no optional blocks."""
        result = build_incremental_synthesis_prompt(
            sample_signals_json, sample_prior_insights_json
        )
        assert "EXISTING INSIGHTS" in result
        assert sample_prior_insights_json in result
        assert "NEW SIGNALS:" in result
        assert sample_signals_json in result
        assert "do NOT restate these" in result
        assert "CROSS-SOURCE CORROBORATION:" not in result
        assert "the developer/AI ecosystem" in result

    def test_with_cluster_context(
        self, sample_signals_json, sample_prior_insights_json, sample_cluster_context
    ):
        """Should include cluster context block when provided."""
        result = build_incremental_synthesis_prompt(
            sample_signals_json,
            sample_prior_insights_json,
            cluster_context=sample_cluster_context,
        )
        assert "CROSS-SOURCE CORROBORATION:" in result
        assert sample_cluster_context in result
        assert "weight them more heavily" in result

    def test_with_domain(
        self, sample_signals_json, sample_prior_insights_json, mock_domain_minimal
    ):
        """Should use domain-specific label when domain provided."""
        result = build_incremental_synthesis_prompt(
            sample_signals_json, sample_prior_insights_json, domain=mock_domain_minimal
        )
        assert f"the {mock_domain_minimal.name} ecosystem" in result
        assert "the developer/AI ecosystem" not in result

    def test_with_all_params(
        self,
        sample_signals_json,
        sample_prior_insights_json,
        sample_cluster_context,
        mock_domain_with_extra,
    ):
        """Should include all optional blocks when all params provided."""
        result = build_incremental_synthesis_prompt(
            sample_signals_json,
            sample_prior_insights_json,
            cluster_context=sample_cluster_context,
            domain=mock_domain_with_extra,
        )
        assert "EXISTING INSIGHTS" in result
        assert "NEW SIGNALS:" in result
        assert "CROSS-SOURCE CORROBORATION:" in result
        assert sample_cluster_context in result
        assert f"the {mock_domain_with_extra.name} ecosystem" in result
        assert "do NOT restate these" in result
        assert "Return a list of 3-7 insights" in result
