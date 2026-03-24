"""Pipeline runner — orchestrates the full max pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from max.evaluation.engine import evaluate
from max.ideation.engine import ideate
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
    insights_generated: int = 0
    ideas_generated: int = 0
    ideas_evaluated: int = 0
    specs_generated: int = 0
    top_ideas: list[dict] = field(default_factory=list)


def run_pipeline(
    *,
    output_dir: Path | None = None,
    signal_limit: int = 30,
    min_score: float = 50.0,
) -> PipelineResult:
    """Run the full pipeline: fetch → synthesize → ideate → evaluate → spec → publish."""
    store = Store()
    result = PipelineResult()

    try:
        # 1. Fetch signals
        signals = _fetch_all_signals(signal_limit=signal_limit)
        result.signals_fetched = len(signals)

        pre_count = store.count_signals()
        for sig in signals:
            store.insert_signal(sig)
        result.signals_new = store.count_signals() - pre_count

        # 2. Synthesize insights
        recent_signals = store.get_signals(limit=signal_limit)
        insights = synthesize(recent_signals)
        for ins in insights:
            store.insert_insight(ins)
        result.insights_generated = len(insights)

        # 3. Ideate
        recent_insights = store.get_insights(limit=20)
        units = ideate(recent_insights)
        for unit in units:
            store.insert_buildable_unit(unit)
        result.ideas_generated = len(units)

        # 4. Evaluate
        evaluated: list[tuple[BuildableUnit, UtilityEvaluation]] = []
        for unit in units:
            evaluation = evaluate(unit)
            store.insert_evaluation(evaluation)
            store.update_buildable_unit_status(unit.id, "evaluated")
            evaluated.append((unit, evaluation))
        result.ideas_evaluated = len(evaluated)

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
