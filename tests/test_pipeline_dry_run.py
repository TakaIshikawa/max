"""Tests for pipeline dry-run mode and selective stage execution."""

from __future__ import annotations

import pytest

from max.pipeline.runner import STAGE_ORDER, run_pipeline
from max.store.db import Store
from max.types.pipeline import DryRunReport


@pytest.fixture
def store():
    """Create a fresh in-memory store for tests."""
    s = Store(":memory:")
    yield s
    s.close()


def test_dry_run_returns_report(store):
    """Test that dry-run mode returns a DryRunReport without executing."""
    result = run_pipeline(dry_run=True, signal_limit=10)

    assert isinstance(result, DryRunReport)
    assert len(result.stages) == len(STAGE_ORDER)
    assert result.estimated_total_llm_calls >= 0
    assert result.estimated_token_budget >= 0
    assert result.estimated_input_tokens >= 0
    assert result.estimated_output_tokens >= 0
    assert result.estimated_cost_usd >= 0
    assert isinstance(result.cost_by_stage, dict)


def test_dry_run_does_not_write_to_store(store):
    """Test that dry-run mode does NOT write to the store."""
    initial_signal_count = store.count_signals()
    initial_insight_count = store.count_insights()
    initial_units_count = len(store.get_buildable_units(limit=1000))

    run_pipeline(dry_run=True, signal_limit=10)

    # Verify no changes were made
    assert store.count_signals() == initial_signal_count
    assert store.count_insights() == initial_insight_count
    assert len(store.get_buildable_units(limit=1000)) == initial_units_count


def test_dry_run_stage_summaries(store):
    """Test that dry-run produces correct stage summaries."""
    result = run_pipeline(dry_run=True, signal_limit=10)

    assert isinstance(result, DryRunReport)

    # All pipeline stages should be present
    stage_names = {s.name for s in result.stages}
    assert stage_names == set(STAGE_ORDER)

    # Each stage should have required fields
    for stage in result.stages:
        assert isinstance(stage.name, str)
        assert isinstance(stage.would_process, int)
        assert isinstance(stage.estimated_llm_calls, int)
        assert isinstance(stage.skipped, bool)
        assert isinstance(stage.reason, str)
        assert isinstance(stage.estimated_input_tokens, int)
        assert isinstance(stage.estimated_output_tokens, int)
        assert isinstance(stage.estimated_total_tokens, int)
        assert isinstance(stage.estimated_cost_usd, float)


def test_stages_filter_valid(store):
    """Test that valid stage filtering works correctly."""
    result = run_pipeline(
        dry_run=True,
        signal_limit=10,
        stages=['fetch', 'synthesize'],
    )

    assert isinstance(result, DryRunReport)

    requested = {'fetch', 'synthesize'}

    # Some stages might still be skipped if they have no data, but at minimum
    # we should see that non-requested stages are always skipped
    for stage in result.stages:
        if stage.name not in requested:
            # Stages not in the requested list should have "stage not selected" reason
            if stage.reason == 'stage not selected':
                assert stage.skipped


def test_stages_filter_maintains_order(store):
    """Test that stages are executed in pipeline order, not caller's order."""
    # Request stages in reverse order
    result = run_pipeline(
        dry_run=True,
        signal_limit=10,
        stages=['evaluate', 'fetch', 'ideate'],
    )

    assert isinstance(result, DryRunReport)

    # Stages should still appear in STAGE_ORDER
    stage_names = [s.name for s in result.stages]
    assert stage_names == STAGE_ORDER


def test_stages_filter_invalid_raises():
    """Test that invalid stage names raise ValueError."""
    with pytest.raises(ValueError, match="Unknown stages"):
        run_pipeline(
            dry_run=True,
            signal_limit=10,
            stages=['fetch', 'invalid_stage', 'another_bad_one'],
        )


def test_stages_filter_case_sensitive():
    """Test that stage names are case-sensitive."""
    with pytest.raises(ValueError, match="Unknown stages"):
        run_pipeline(
            dry_run=True,
            signal_limit=10,
            stages=['FETCH', 'Synthesize'],
        )


def test_dry_run_with_all_stages(store):
    """Test dry-run with all stages explicitly listed."""
    result = run_pipeline(
        dry_run=True,
        signal_limit=10,
        stages=STAGE_ORDER,
    )

    assert isinstance(result, DryRunReport)
    assert len(result.stages) == len(STAGE_ORDER)


def test_dry_run_estimates_llm_calls(store):
    """Test that dry-run estimates LLM calls reasonably."""
    result = run_pipeline(dry_run=True, signal_limit=20)

    assert isinstance(result, DryRunReport)

    # Stages that should have LLM calls
    synthesize_stage = next((s for s in result.stages if s.name == 'synthesize'), None)
    ideate_stage = next((s for s in result.stages if s.name == 'ideate'), None)
    evaluate_stage = next((s for s in result.stages if s.name == 'evaluate'), None)

    # Synthesize should estimate some LLM calls if there are signals
    if synthesize_stage and not synthesize_stage.skipped:
        assert synthesize_stage.estimated_llm_calls >= 0

    # Ideate should estimate LLM calls based on insights
    if ideate_stage and not ideate_stage.skipped:
        assert ideate_stage.estimated_llm_calls >= 0

    # Evaluate should estimate LLM calls based on ideas
    if evaluate_stage and not evaluate_stage.skipped:
        assert evaluate_stage.estimated_llm_calls >= 0

    # Total should sum up
    total_from_stages = sum(s.estimated_llm_calls for s in result.stages)
    assert result.estimated_total_llm_calls == total_from_stages

    input_from_stages = sum(s.estimated_input_tokens for s in result.stages)
    output_from_stages = sum(s.estimated_output_tokens for s in result.stages)
    tokens_from_stages = sum(s.estimated_total_tokens for s in result.stages)
    assert result.estimated_input_tokens == input_from_stages
    assert result.estimated_output_tokens == output_from_stages
    assert result.estimated_token_budget == tokens_from_stages


def test_dry_run_token_budget_estimate(store):
    """Test that dry-run estimates token budget."""
    result = run_pipeline(dry_run=True, signal_limit=10)

    assert isinstance(result, DryRunReport)
    # Token budget should be proportional to LLM calls
    # Rough estimate: ~2000 tokens per call
    expected_min = result.estimated_total_llm_calls * 1000
    assert result.estimated_token_budget >= expected_min
    assert result.estimated_token_budget == (
        result.estimated_input_tokens + result.estimated_output_tokens
    )


def test_normal_run_without_dry_run_flag(store):
    """Test that normal execution (without dry_run) does NOT return DryRunReport."""
    # This would normally execute the full pipeline; we're just checking the type
    # Since we don't want to actually run LLM calls in tests, we'll use stages=[]
    # to skip all execution
    result = run_pipeline(
        dry_run=False,
        signal_limit=5,
        stages=[],  # Empty stages list means nothing executes
    )

    # Should return PipelineResult, not DryRunReport
    assert not isinstance(result, DryRunReport)
    assert hasattr(result, 'signals_fetched')
    assert hasattr(result, 'insights_generated')


def test_stages_empty_list_skips_all(store):
    """Test that an empty stages list skips all stages."""
    result = run_pipeline(
        dry_run=True,
        signal_limit=10,
        stages=[],
    )

    assert isinstance(result, DryRunReport)

    # All stages should be skipped with "stage not selected" reason
    for stage in result.stages:
        assert stage.skipped
        assert stage.reason == 'stage not selected'


def test_stage_skip_reasons(store):
    """Test that stages have appropriate skip reasons."""
    result = run_pipeline(
        dry_run=True,
        signal_limit=10,
        stages=['synthesize'],  # Only synthesize, which might skip due to no signals
    )

    assert isinstance(result, DryRunReport)

    # Fetch should be skipped because not selected
    fetch_stage = next(s for s in result.stages if s.name == 'fetch')
    assert fetch_stage.skipped
    assert fetch_stage.reason == 'stage not selected'

    # Synthesize might be skipped if no unsynthesized signals
    synth_stage = next(s for s in result.stages if s.name == 'synthesize')
    if synth_stage.skipped:
        assert synth_stage.reason in ('no new signals since last run', 'stage not selected', '')
