"""Unit tests for the synthesis engine (signals → insights)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from max.synthesis.engine import InsightOutput, SynthesisOutput, synthesize
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_signal(
    id: str = "sig-001",
    title: str = "Test signal",
    content: str = "Some content",
    source_type: SignalSourceType = SignalSourceType.FORUM,
    **kwargs,
) -> Signal:
    defaults = dict(
        id=id,
        source_type=source_type,
        source_adapter="test",
        title=title,
        content=content,
        url="https://example.com",
        tags=["test"],
        credibility=0.7,
    )
    defaults.update(kwargs)
    return Signal(**defaults)


def _make_insight(
    id: str = "ins-001",
    category: InsightCategory = InsightCategory.GAP,
    title: str = "Test insight",
    **kwargs,
) -> Insight:
    defaults = dict(
        id=id,
        category=category,
        title=title,
        summary="Test summary",
        evidence=["sig-001"],
        confidence=0.8,
        domains=["testing"],
        implications=["Build something"],
        time_horizon="near_term",
    )
    defaults.update(kwargs)
    return Insight(**defaults)


def _synthesis_output(**overrides) -> SynthesisOutput:
    """Build a SynthesisOutput with two insights, applying any field overrides."""
    base = [
        InsightOutput(
            category="gap",
            title="Missing testing framework",
            summary="No standard testing for MCP servers.",
            evidence=["sig-001"],
            confidence=0.85,
            domains=["mcp", "testing"],
            implications=["Testing framework needed"],
            time_horizon="near_term",
        ),
        InsightOutput(
            category="trend",
            title="Agent adoption surge",
            summary="LLM agent usage growing rapidly.",
            evidence=["sig-002"],
            confidence=0.72,
            domains=["ai"],
            implications=["More tooling needed"],
            time_horizon="medium_term",
        ),
    ]
    if overrides:
        for i, out in enumerate(base):
            for k, v in overrides.items():
                if hasattr(out, k):
                    object.__setattr__(out, k, v)
    return SynthesisOutput(insights=base)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSynthesizeEmptySignals:
    def test_returns_empty_list(self):
        assert synthesize([]) == []


class TestSynthesizeBasicFlow:
    @patch("max.synthesis.engine.structured_call")
    def test_returns_correct_number_of_insights(self, mock_call):
        mock_call.return_value = _synthesis_output()
        signals = [_make_signal(id="sig-001"), _make_signal(id="sig-002")]

        result = synthesize(signals)

        assert len(result) == 2
        assert all(isinstance(ins, Insight) for ins in result)

    @patch("max.synthesis.engine.structured_call")
    def test_category_parsed_to_enum(self, mock_call):
        mock_call.return_value = _synthesis_output()
        result = synthesize([_make_signal()])

        assert result[0].category == InsightCategory.GAP
        assert result[1].category == InsightCategory.TREND

    @patch("max.synthesis.engine.structured_call")
    def test_invalid_category_falls_back_to_emerging_pattern(self, mock_call):
        mock_call.return_value = SynthesisOutput(
            insights=[
                InsightOutput(
                    category="totally_made_up",
                    title="Invalid cat",
                    summary="Should fallback",
                    evidence=[],
                    confidence=0.5,
                    domains=[],
                    implications=[],
                    time_horizon="near_term",
                ),
            ]
        )
        result = synthesize([_make_signal()])

        assert result[0].category == InsightCategory.EMERGING_PATTERN

    @patch("max.synthesis.engine.structured_call")
    def test_confidence_clamped_low(self, mock_call):
        mock_call.return_value = SynthesisOutput(
            insights=[
                InsightOutput(
                    category="gap",
                    title="Low conf",
                    summary="Negative confidence",
                    confidence=-0.5,
                ),
            ]
        )
        result = synthesize([_make_signal()])
        assert result[0].confidence == 0.0

    @patch("max.synthesis.engine.structured_call")
    def test_confidence_clamped_high(self, mock_call):
        mock_call.return_value = SynthesisOutput(
            insights=[
                InsightOutput(
                    category="gap",
                    title="High conf",
                    summary="Over-confidence",
                    confidence=1.5,
                ),
            ]
        )
        result = synthesize([_make_signal()])
        assert result[0].confidence == 1.0

    @patch("max.synthesis.engine.structured_call")
    def test_valid_time_horizons_accepted(self, mock_call):
        for horizon in ("near_term", "medium_term", "long_term"):
            mock_call.return_value = SynthesisOutput(
                insights=[
                    InsightOutput(
                        category="trend",
                        title=f"Horizon {horizon}",
                        summary="ok",
                        time_horizon=horizon,
                    ),
                ]
            )
            result = synthesize([_make_signal()])
            assert result[0].time_horizon == horizon

    @patch("max.synthesis.engine.structured_call")
    def test_invalid_time_horizon_defaults_to_near_term(self, mock_call):
        mock_call.return_value = SynthesisOutput(
            insights=[
                InsightOutput(
                    category="trend",
                    title="Bad horizon",
                    summary="bad",
                    time_horizon="far_future",
                ),
            ]
        )
        result = synthesize([_make_signal()])
        assert result[0].time_horizon == "near_term"


class TestSynthesizeWithPriorInsights:
    @patch("max.synthesis.engine.build_incremental_synthesis_prompt")
    @patch("max.synthesis.engine.build_synthesis_prompt")
    @patch("max.synthesis.engine.structured_call")
    def test_uses_incremental_prompt(self, mock_call, mock_base_prompt, mock_inc_prompt):
        mock_call.return_value = SynthesisOutput(insights=[])
        mock_inc_prompt.return_value = "incremental prompt"

        prior = [_make_insight()]
        synthesize([_make_signal()], prior_insights=prior)

        mock_inc_prompt.assert_called_once()
        mock_base_prompt.assert_not_called()

    @patch("max.synthesis.engine.build_synthesis_prompt")
    @patch("max.synthesis.engine.build_incremental_synthesis_prompt")
    @patch("max.synthesis.engine.structured_call")
    def test_uses_base_prompt_without_priors(self, mock_call, mock_inc_prompt, mock_base_prompt):
        mock_call.return_value = SynthesisOutput(insights=[])
        mock_base_prompt.return_value = "base prompt"

        synthesize([_make_signal()])

        mock_base_prompt.assert_called_once()
        mock_inc_prompt.assert_not_called()


class TestSynthesizeWithClusterContext:
    @patch("max.synthesis.engine.build_synthesis_prompt")
    @patch("max.synthesis.engine.structured_call")
    def test_cluster_context_passed_to_prompt_builder(self, mock_call, mock_prompt):
        mock_call.return_value = SynthesisOutput(insights=[])
        mock_prompt.return_value = "prompt"

        synthesize([_make_signal()], cluster_context="cluster info here")

        _, kwargs = mock_prompt.call_args
        assert kwargs["cluster_context"] == "cluster info here"

    @patch("max.synthesis.engine.build_incremental_synthesis_prompt")
    @patch("max.synthesis.engine.structured_call")
    def test_cluster_context_passed_with_prior_insights(self, mock_call, mock_prompt):
        mock_call.return_value = SynthesisOutput(insights=[])
        mock_prompt.return_value = "prompt"

        synthesize(
            [_make_signal()],
            prior_insights=[_make_insight()],
            cluster_context="cluster info",
        )

        _, kwargs = mock_prompt.call_args
        assert kwargs["cluster_context"] == "cluster info"


class TestSignalTruncation:
    @patch("max.synthesis.engine.structured_call")
    def test_signal_content_truncated_to_500_chars(self, mock_call):
        mock_call.return_value = SynthesisOutput(insights=[])
        long_content = "x" * 1000
        signal = _make_signal(content=long_content)

        synthesize([signal])

        # Inspect the prompt passed to structured_call
        call_kwargs = mock_call.call_args
        prompt_arg = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt") or call_kwargs[0][1]

        # The signal JSON in the prompt should contain truncated content
        # Parse the signals JSON embedded in the prompt to verify truncation
        # We verify via the call args: the engine builds JSON with s.content[:500]
        assert mock_call.called
        # The engine does s.content[:500] before embedding in JSON, so the prompt
        # should contain exactly 500 'x' characters, not 1000.
        assert "x" * 501 not in prompt_arg
        assert "x" * 500 in prompt_arg
