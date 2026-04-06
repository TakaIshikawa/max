"""Tests for token cost estimation and budget enforcement."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.llm.client import (
    BudgetExceededError,
    MODEL_PRICING,
    TokenTracker,
    structured_call,
    text_call,
)
from pydantic import BaseModel


class TestModelPricing:
    """Tests for MODEL_PRICING configuration."""

    def test_opus_pricing_defined(self):
        assert "claude-opus-4-6" in MODEL_PRICING
        opus = MODEL_PRICING["claude-opus-4-6"]
        assert "input_per_1k" in opus
        assert "output_per_1k" in opus
        assert opus["input_per_1k"] > 0
        assert opus["output_per_1k"] > 0

    def test_sonnet_pricing_defined(self):
        assert "claude-sonnet-4-5-20250929" in MODEL_PRICING
        sonnet = MODEL_PRICING["claude-sonnet-4-5-20250929"]
        assert sonnet["input_per_1k"] < MODEL_PRICING["claude-opus-4-6"]["input_per_1k"]

    def test_haiku_pricing_defined(self):
        assert "claude-haiku-4-5-20251001" in MODEL_PRICING


class TestTokenTracker:
    """Tests for TokenTracker cost estimation."""

    def test_estimated_cost_usd_calculates_correctly(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 1000, 500)

        expected_input = (1000 / 1000) * 0.015  # 1K * $0.015
        expected_output = (500 / 1000) * 0.075   # 0.5K * $0.075
        expected = expected_input + expected_output  # $0.0525

        assert abs(tracker.estimated_cost_usd() - expected) < 0.0001

    def test_estimated_cost_usd_with_zero_tokens(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        assert tracker.estimated_cost_usd() == 0.0

    def test_estimated_cost_usd_uses_fallback_for_unknown_model(self):
        tracker = TokenTracker(model="unknown-model")
        tracker.record("test", 1000, 500)

        # Should fall back to Opus pricing
        opus_pricing = MODEL_PRICING["claude-opus-4-6"]
        expected = (1000 / 1000) * opus_pricing["input_per_1k"] + (500 / 1000) * opus_pricing["output_per_1k"]

        assert abs(tracker.estimated_cost_usd() - expected) < 0.0001

    def test_cost_by_stage_breaks_down_correctly(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("synthesis", 1000, 500)
        tracker.record("ideation", 2000, 1000)

        costs = tracker.cost_by_stage()

        assert "synthesis" in costs
        assert "ideation" in costs

        # Synthesis: 1K input * 0.015 + 0.5K output * 0.075 = 0.0525
        assert abs(costs["synthesis"] - 0.0525) < 0.0001

        # Ideation: 2K input * 0.015 + 1K output * 0.075 = 0.105
        assert abs(costs["ideation"] - 0.105) < 0.0001

    def test_budget_remaining_unlimited_when_budget_zero(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 10000, 5000)
        assert tracker.budget_remaining(0) == float("inf")

    def test_budget_remaining_returns_correct_value(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 1000, 500)

        cost = tracker.estimated_cost_usd()
        budget = 1.0
        expected_remaining = budget - cost

        assert abs(tracker.budget_remaining(budget) - expected_remaining) < 0.0001

    def test_budget_remaining_negative_when_over_budget(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 100000, 50000)

        budget = 0.01  # Very small budget
        remaining = tracker.budget_remaining(budget)

        assert remaining < 0

    def test_is_over_budget_returns_false_when_under(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 100, 50)

        assert not tracker.is_over_budget(10.0)

    def test_is_over_budget_returns_true_when_over(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 100000, 50000)

        assert tracker.is_over_budget(0.01)

    def test_is_over_budget_returns_false_when_budget_unlimited(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 100000, 50000)

        assert not tracker.is_over_budget(0)

    def test_summary_includes_cost_fields(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("stage1", 1000, 500)
        tracker.record("stage2", 2000, 1000)

        summary = tracker.summary()

        assert "estimated_cost_usd" in summary
        assert "cost_by_stage" in summary
        assert isinstance(summary["cost_by_stage"], dict)
        assert summary["estimated_cost_usd"] > 0

    def test_reset_clears_cost_tracking(self):
        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("test", 1000, 500)

        assert tracker.estimated_cost_usd() > 0

        tracker.reset()

        assert tracker.estimated_cost_usd() == 0.0
        assert tracker.cost_by_stage() == {}


class TestBudgetEnforcement:
    """Tests for budget enforcement in LLM call functions."""

    def test_structured_call_raises_when_token_budget_exceeded(self):
        class DummyOutput(BaseModel):
            result: str

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100000
        mock_response.usage.output_tokens = 50000
        mock_response.content = [MagicMock(type="tool_use", input={"result": "test"})]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.llm.client.token_tracker") as mock_tracker,
            patch("max.config.MAX_TOKEN_BUDGET", 1000),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            mock_tracker.total.return_value = 150001  # Over budget
            mock_tracker.is_over_budget.return_value = False

            with pytest.raises(BudgetExceededError, match="Token budget exceeded"):
                structured_call(
                    system="test",
                    prompt="test",
                    output_type=DummyOutput,
                    stage="test_stage",
                )

    def test_structured_call_raises_when_cost_budget_exceeded(self):
        class DummyOutput(BaseModel):
            result: str

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 10000
        mock_response.usage.output_tokens = 5000
        mock_response.content = [MagicMock(type="tool_use", input={"result": "test"})]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.llm.client.token_tracker") as mock_tracker,
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.001),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            mock_tracker.total.return_value = 15000
            mock_tracker.is_over_budget.return_value = True
            mock_tracker.estimated_cost_usd.return_value = 0.01

            with pytest.raises(BudgetExceededError, match="Cost budget exceeded"):
                structured_call(
                    system="test",
                    prompt="test",
                    output_type=DummyOutput,
                    stage="test_stage",
                )

    def test_structured_call_succeeds_when_budget_unlimited(self):
        class DummyOutput(BaseModel):
            result: str

        mock_response = MagicMock()
        mock_response.usage.input_tokens = 10000
        mock_response.usage.output_tokens = 5000
        mock_response.content = [MagicMock(type="tool_use", input={"result": "success"})]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.llm.client.token_tracker") as mock_tracker,
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            mock_tracker.total.return_value = 15000
            mock_tracker.is_over_budget.return_value = False

            result = structured_call(
                system="test",
                prompt="test",
                output_type=DummyOutput,
                stage="test_stage",
            )

            assert result.result == "success"

    def test_text_call_raises_when_token_budget_exceeded(self):
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100000
        mock_response.usage.output_tokens = 50000
        mock_response.content = [MagicMock(text="test response")]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.llm.client.token_tracker") as mock_tracker,
            patch("max.config.MAX_TOKEN_BUDGET", 1000),
            patch("max.config.MAX_COST_BUDGET", 0.0),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            mock_tracker.total.return_value = 150001
            mock_tracker.is_over_budget.return_value = False

            with pytest.raises(BudgetExceededError, match="Token budget exceeded"):
                text_call(
                    system="test",
                    prompt="test",
                    stage="test_stage",
                )

    def test_text_call_raises_when_cost_budget_exceeded(self):
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 10000
        mock_response.usage.output_tokens = 5000
        mock_response.content = [MagicMock(text="test response")]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.llm.client.token_tracker") as mock_tracker,
            patch("max.config.MAX_TOKEN_BUDGET", 0),
            patch("max.config.MAX_COST_BUDGET", 0.001),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            mock_tracker.total.return_value = 15000
            mock_tracker.is_over_budget.return_value = True
            mock_tracker.estimated_cost_usd.return_value = 0.01

            with pytest.raises(BudgetExceededError, match="Cost budget exceeded"):
                text_call(
                    system="test",
                    prompt="test",
                    stage="test_stage",
                )

    def test_budget_not_checked_when_stage_not_provided(self):
        """Budget enforcement only happens when stage is provided."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test")]

        with (
            patch("max.llm.client.get_client") as mock_get_client,
            patch("max.config.MAX_TOKEN_BUDGET", 1),
            patch("max.config.MAX_COST_BUDGET", 0.001),
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_get_client.return_value = mock_client

            # Should not raise even though budgets are very low
            result = text_call(system="test", prompt="test")
            assert result == "test"


class TestPipelineBudgetIntegration:
    """Tests for budget tracking in pipeline runs."""

    @pytest.fixture
    def mock_pipeline_deps(self):
        """Mock all dependencies for pipeline runner."""
        with (
            patch("max.pipeline.runner._fetch_all_signals") as mock_fetch,
            patch("max.pipeline.runner.annotate_signals"),
            patch("max.pipeline.runner.Store") as mock_store,
            patch("max.pipeline.runner.SemanticIndex"),
            patch("max.pipeline.runner.get_adapted_weights") as mock_weights,
            patch("max.pipeline.runner.token_tracker") as mock_tracker,
        ):
            # Setup mocks
            mock_fetch.return_value = ([], {}, {})
            mock_store_instance = MagicMock()
            mock_store_instance.count_signals.return_value = 0
            mock_store_instance.get_unsynthesized_signals.return_value = []
            mock_store_instance.get_feedback_outcomes.return_value = []
            mock_store.return_value = mock_store_instance

            mock_weights.return_value = ({}, False)

            mock_tracker.summary.return_value = {
                "total_input": 1000,
                "total_output": 500,
                "total": 1500,
                "estimated_cost_usd": 0.05,
                "cost_by_stage": {"synthesis": 0.03, "ideation": 0.02},
            }
            mock_tracker.estimated_cost_usd.return_value = 0.05
            mock_tracker.cost_by_stage.return_value = {"synthesis": 0.03, "ideation": 0.02}

            yield {
                "fetch": mock_fetch,
                "store": mock_store_instance,
                "tracker": mock_tracker,
            }

    def test_pipeline_catches_budget_exceeded_and_preserves_partial_results(self, mock_pipeline_deps):
        from max.pipeline.runner import run_pipeline

        # Make synthesize raise BudgetExceededError
        with patch("max.pipeline.runner.synthesize") as mock_synth:
            mock_synth.side_effect = BudgetExceededError("Cost limit reached")

            # Make signals available to trigger synthesis
            mock_pipeline_deps["store"].get_unsynthesized_signals.return_value = [
                MagicMock(id="sig1")
            ]

            result = run_pipeline(signal_limit=5)

            assert result.budget_exceeded is True
            # Partial results should be preserved
            assert result.signals_fetched == 0  # From mock

    def test_pipeline_result_includes_cost_fields(self, mock_pipeline_deps):
        from max.pipeline.runner import run_pipeline

        # Mock the entire pipeline stages to avoid real LLM calls
        with (
            patch("max.pipeline.runner.detect_gaps") as mock_gaps,
            patch("max.pipeline.runner.analyze_retrospective") as mock_retro,
            patch("max.pipeline.runner.ideate") as mock_ideate,
            patch("max.pipeline.runner.ideate_refinement"),
            patch("max.pipeline.runner.ideate_cross_domain"),
        ):
            mock_gaps.return_value = []
            mock_retro.return_value = None
            mock_ideate.return_value = []

            result = run_pipeline(signal_limit=5)

            assert hasattr(result, "estimated_cost_usd")
            assert hasattr(result, "cost_by_stage")
            assert hasattr(result, "budget_exceeded")

            assert result.estimated_cost_usd == 0.05
            assert result.cost_by_stage == {"synthesis": 0.03, "ideation": 0.02}
            assert result.budget_exceeded is False

    def test_pipeline_populates_cost_metrics_in_finally_block(self, mock_pipeline_deps):
        """Cost metrics are populated even if an exception occurs."""
        from max.pipeline.runner import run_pipeline

        # Make fetch raise a non-budget exception
        mock_pipeline_deps["fetch"].side_effect = RuntimeError("Network error")

        with pytest.raises(RuntimeError):
            run_pipeline(signal_limit=5)

        # Token tracker summary methods should have been called in finally
        mock_pipeline_deps["tracker"].summary.assert_called_once()
        mock_pipeline_deps["tracker"].estimated_cost_usd.assert_called_once()
        mock_pipeline_deps["tracker"].cost_by_stage.assert_called_once()


class TestConfigBudgetDefaults:
    """Tests for budget config defaults."""

    def test_token_budget_defaults_to_zero(self):
        import os
        import importlib

        clean_env = {k: v for k, v in os.environ.items() if "MAX_TOKEN_BUDGET" not in k}
        with patch.dict("os.environ", clean_env, clear=True):
            import max.config as cfg
            importlib.reload(cfg)

            assert cfg.MAX_TOKEN_BUDGET == 0

        importlib.reload(cfg)

    def test_cost_budget_defaults_to_zero(self):
        import os
        import importlib

        clean_env = {k: v for k, v in os.environ.items() if "MAX_COST_BUDGET" not in k}
        with patch.dict("os.environ", clean_env, clear=True):
            import max.config as cfg
            importlib.reload(cfg)

            assert cfg.MAX_COST_BUDGET == 0.0

        importlib.reload(cfg)
