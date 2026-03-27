"""Pipeline runner — orchestrates the full max pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from max.embeddings.engine import SemanticIndex
from max.evaluation.engine import evaluate
from max.evaluation.weights import get_weights
from max.ideation.engine import ideate, ideate_cross_domain, ideate_refinement
from max.llm.client import token_tracker
from max.pipeline.dedup import dedup_buildable_units, dedup_insights
from max.publisher.file_writer import write_tact_spec
from max.sources.registry import get_all_adapters
from max.spec.generator import generate_spec
from max.store.db import Store
from max.synthesis.engine import synthesize
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation
from max.types.signal import Signal


@dataclass
class PipelineResult:
    """Summary of a pipeline run."""

    signals_fetched: int = 0
    signals_new: int = 0
    signals_skipped: int = 0
    insights_generated: int = 0
    insights_duplicates_skipped: int = 0
    ideas_generated: int = 0
    ideas_duplicates_skipped: int = 0
    ideas_evaluated: int = 0
    specs_generated: int = 0
    top_ideas: list[dict] = field(default_factory=list)

    # Quality metrics
    avg_insight_confidence: float = 0.0
    avg_idea_score: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)


def run_pipeline(
    *,
    output_dir: Path | None = None,
    signal_limit: int = 30,
    min_score: float = 50.0,
    weight_profile: str = "default",
    ideation_mode: str = "direct",
) -> PipelineResult:
    """Run the full pipeline: fetch → synthesize → ideate → evaluate → spec → publish."""
    token_tracker.reset()
    weights = get_weights(weight_profile)
    store = Store()
    semantic_index = SemanticIndex(store)
    result = PipelineResult()

    try:
        # 1. Fetch signals
        signals = _fetch_all_signals(signal_limit=signal_limit)
        result.signals_fetched = len(signals)

        pre_count = store.count_signals()
        for sig in signals:
            store.insert_signal(sig)
        result.signals_new = store.count_signals() - pre_count

        # 2. Synthesize insights (incremental — only new signals)
        new_signals = store.get_unsynthesized_signals(limit=signal_limit)
        result.signals_skipped = result.signals_fetched - len(new_signals)
        if new_signals:
            prior_insights = store.get_insights(limit=20)
            insights = synthesize(
                new_signals,
                prior_insights=prior_insights if prior_insights else None,
            )
            store.mark_signals_synthesized([s.id for s in new_signals])
            dedup = dedup_insights(insights, semantic_index)
            insights = dedup.kept
            result.insights_duplicates_skipped = dedup.duplicates
            for ins in insights:
                store.insert_insight(ins)
        else:
            insights = []
        result.insights_generated = len(insights)
        if insights:
            result.avg_insight_confidence = sum(i.confidence for i in insights) / len(insights)

        # 3. Ideate (supports multiple modes)
        recent_insights = store.get_insights(limit=20)
        units: list[BuildableUnit] = []

        if ideation_mode in ("direct", "all"):
            units.extend(ideate(recent_insights))

        if ideation_mode in ("refinement", "all"):
            existing = store.get_buildable_units(status="evaluated", limit=10)
            if existing:
                units.extend(ideate_refinement(existing, recent_insights))

        if ideation_mode in ("cross_domain", "all"):
            units.extend(ideate_cross_domain(recent_insights))

        dedup = dedup_buildable_units(units, semantic_index)
        units = dedup.kept
        result.ideas_duplicates_skipped = dedup.duplicates
        for unit in units:
            store.insert_buildable_unit(unit)
        result.ideas_generated = len(units)

        # 4. Evaluate (using selected weight profile)
        evaluated: list[tuple[BuildableUnit, UtilityEvaluation]] = []
        for unit in units:
            evaluation = evaluate(unit, weights=weights)
            store.insert_evaluation(evaluation)
            store.update_buildable_unit_status(unit.id, "evaluated")
            evaluated.append((unit, evaluation))
        result.ideas_evaluated = len(evaluated)
        if evaluated:
            result.avg_idea_score = sum(e.overall_score for _, e in evaluated) / len(evaluated)

        # 5. Generate specs for ideas above threshold
        specs_written = 0
        for unit, evaluation in sorted(evaluated, key=lambda x: x[1].overall_score, reverse=True):
            if evaluation.overall_score < min_score:
                continue

            spec = generate_spec(unit, evaluation)
            store.insert_tact_spec(spec)
            store.update_buildable_unit_status(unit.id, "approved")

            if output_dir:
                spec_dir = output_dir / spec.product.name
                write_tact_spec(spec, spec_dir)

            specs_written += 1

        result.specs_generated = specs_written

        # Summary of top ideas
        result.top_ideas = [
            {
                "id": unit.id,
                "title": unit.title,
                "score": evaluation.overall_score,
                "recommendation": evaluation.recommendation,
            }
            for unit, evaluation in sorted(
                evaluated, key=lambda x: x[1].overall_score, reverse=True
            )[:5]
        ]

        # Token usage
        result.token_usage = token_tracker.summary()

    finally:
        store.close()

    return result


def _fetch_all_signals(*, signal_limit: int = 30) -> list[Signal]:
    """Fetch signals from all registered adapters."""
    adapters = get_all_adapters()
    all_signals: list[Signal] = []

    per_adapter = max(signal_limit // len(adapters), 5) if adapters else signal_limit

    for adapter in adapters:
        try:
            signals = asyncio.run(adapter.fetch(limit=per_adapter))
            all_signals.extend(signals)
        except Exception as e:
            print(f"  Warning: {adapter.name} fetch failed: {e}")

    return all_signals
