"""Pipeline runner — orchestrates the full max pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from max.analysis.gap_detector import detect_gaps, format_gaps_for_ideation
from max.analysis.retrospective import analyze_retrospective, format_retrospective_for_ideation
from max.analysis.roles import annotate_signals
from max.analysis.triangulation import format_cluster_context, triangulate
from max.embeddings.engine import SemanticIndex
from max.evaluation.engine import evaluate
from max.evaluation.weights import get_adapted_weights
from max.ideation.engine import ideate, ideate_cross_domain, ideate_refinement
from max.llm.client import BudgetExceededError, token_tracker
from max.pipeline.dedup import dedup_buildable_units, dedup_insights
from max.sources.base import AdapterCircuitOpenError
from max.sources.registry import get_all_adapters
from max.store.db import Store
from max.synthesis.engine import synthesize
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation
from max.types.signal import Signal

if TYPE_CHECKING:
    from max.profiles.schema import DomainContext, PipelineProfile

logger = logging.getLogger(__name__)


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
    top_ideas: list[dict] = field(default_factory=list)

    # Quality metrics
    weights_adapted: bool = False
    avg_insight_confidence: float = 0.0
    avg_idea_score: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)

    # Per-adapter fetch metrics
    adapter_metrics: dict[str, dict] = field(default_factory=dict)

    # Meta-intelligence metrics
    clusters_found: int = 0
    multi_source_clusters: int = 0
    gaps_detected: int = 0
    fetch_allocation: dict[str, int] = field(default_factory=dict)

    # Feedback loop metrics
    run_id: str = ""
    learned_from_feedback: bool = False

    # Profile info
    profile_name: str = ""

    # Budget tracking
    estimated_cost_usd: float = 0.0
    cost_by_stage: dict[str, float] = field(default_factory=dict)
    budget_exceeded: bool = False


def run_pipeline(
    *,
    profile: PipelineProfile | None = None,
    output_dir: Path | None = None,
    signal_limit: int = 30,
    min_score: float = 50.0,
    weight_profile: str = "default",
    ideation_mode: str = "direct",
) -> PipelineResult:
    """Run the full pipeline: fetch → synthesize → ideate → evaluate → spec → publish.

    When *profile* is provided, pipeline parameters are extracted from it.
    Explicit keyword arguments override profile values when both are given.
    """
    # Extract params from profile (explicit kwargs take precedence)
    domain: DomainContext | None = None
    source_configs = None
    if profile is not None:
        domain = profile.domain
        source_configs = profile.sources or None
        output_dir = output_dir or Path(profile.output_dir)
        signal_limit = profile.signal_limit
        min_score = profile.evaluation.min_score
        weight_profile = profile.evaluation.weight_profile
        ideation_mode = profile.ideation_mode

    token_tracker.reset()
    store = Store()
    semantic_index = SemanticIndex(store)
    result = PipelineResult()
    if profile is not None:
        result.profile_name = profile.name

    # Record pipeline run
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    result.run_id = run_id
    config = {
        "signal_limit": signal_limit,
        "min_score": min_score,
        "weight_profile": weight_profile,
        "ideation_mode": ideation_mode,
        "profile": profile.name if profile else None,
    }
    store.insert_pipeline_run(run_id, config)

    # Adapt weights from feedback history
    feedback_outcomes = store.get_feedback_outcomes()
    weights, was_adapted = get_adapted_weights(weight_profile, feedback_outcomes)
    result.weights_adapted = was_adapted
    if was_adapted:
        logger.info("Using feedback-adapted weights (%d outcomes)", len(feedback_outcomes))
    else:
        logger.info("Using static weight profile '%s'", weight_profile)

    try:
        # 1. Fetch signals
        signals, fetch_alloc, adapter_metrics = _fetch_all_signals(
            signal_limit=signal_limit, store=store, source_configs=source_configs,
        )
        result.signals_fetched = len(signals)
        result.fetch_allocation = fetch_alloc
        result.adapter_metrics = adapter_metrics

        # 1.1 Annotate signal roles (problem / solution / market)
        annotate_signals(signals)

        pre_count = store.count_signals()
        for sig in signals:
            store.insert_signal(sig)
        result.signals_new = store.count_signals() - pre_count

        # 2. Synthesize insights (incremental — only new signals)
        new_signals = store.get_unsynthesized_signals(limit=signal_limit)
        result.signals_skipped = result.signals_fetched - len(new_signals)
        if new_signals:
            # 2.1 Triangulate signals for cross-source corroboration
            clusters = triangulate(new_signals)
            result.clusters_found = len(clusters)
            result.multi_source_clusters = sum(
                1 for c in clusters if len(c.distinct_sources) > 1
            )
            cluster_ctx = format_cluster_context(clusters)

            prior_insights = store.get_insights(limit=20)
            insights = synthesize(
                new_signals,
                prior_insights=prior_insights if prior_insights else None,
                cluster_context=cluster_ctx,
                domain=domain,
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

        # 3. Detect gaps (validated unmet needs)
        gaps = detect_gaps(store)
        result.gaps_detected = len(gaps)
        gaps_ctx = format_gaps_for_ideation(gaps)

        # 3.5 Retrospective analysis (learned patterns from feedback history)
        retrospective = analyze_retrospective(store)
        learned_ctx = format_retrospective_for_ideation(retrospective) if retrospective else None
        result.learned_from_feedback = retrospective is not None
        if retrospective:
            logger.info(
                "Retrospective: %d patterns, %d successful categories",
                retrospective.pattern_count,
                len(retrospective.successful_categories),
            )

        # 4. Ideate (supports multiple modes, with memory of existing ideas)
        recent_insights = store.get_insights(limit=20)
        recent_ideas = store.get_buildable_units(limit=30)
        units: list[BuildableUnit] = []

        if ideation_mode in ("direct", "all"):
            units.extend(ideate(
                recent_insights,
                existing_ideas=recent_ideas or None,
                gaps_context=gaps_ctx,
                learned_context=learned_ctx,
                domain=domain,
            ))

        if ideation_mode in ("refinement", "all"):
            existing = store.get_buildable_units(status="evaluated", limit=10)
            if existing:
                units.extend(ideate_refinement(existing, recent_insights, domain=domain))

        if ideation_mode in ("cross_domain", "all"):
            units.extend(ideate_cross_domain(
                recent_insights,
                existing_ideas=recent_ideas or None,
                gaps_context=gaps_ctx,
                learned_context=learned_ctx,
                domain=domain,
            ))

        dedup = dedup_buildable_units(units, semantic_index)
        units = dedup.kept
        result.ideas_duplicates_skipped = dedup.duplicates
        domain_name = domain.name if domain else ""
        for unit in units:
            unit.domain = domain_name
            store.insert_buildable_unit(unit)
        result.ideas_generated = len(units)

        # 4. Evaluate (using selected weight profile, with evidence grounding)
        evaluated: list[tuple[BuildableUnit, UtilityEvaluation]] = []
        for unit in units:
            evidence = _resolve_evidence_chain(unit, store)
            evaluation = evaluate(unit, weights=weights, evidence=evidence, domain=domain)
            store.insert_evaluation(evaluation)
            store.update_buildable_unit_status(unit.id, "evaluated")
            evaluated.append((unit, evaluation))
        result.ideas_evaluated = len(evaluated)
        if evaluated:
            result.avg_idea_score = sum(e.overall_score for _, e in evaluated) / len(evaluated)

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

        # Record per-domain stats
        domain_stats: dict[str, dict] = {}
        for unit, evaluation in evaluated:
            d = unit.domain or ""
            if d not in domain_stats:
                domain_stats[d] = {
                    "signals_fetched": 0,
                    "insights_generated": 0,
                    "ideas_generated": 0,
                    "ideas_evaluated": 0,
                    "total_score": 0.0,
                }
            domain_stats[d]["ideas_generated"] += 1
            domain_stats[d]["ideas_evaluated"] += 1
            domain_stats[d]["total_score"] += evaluation.overall_score

        # Attribute insight counts to domains via their buildable units
        for unit in units:
            d = unit.domain or ""
            if d in domain_stats:
                domain_stats[d]["insights_generated"] = len(unit.inspiring_insights)

        for d, stats in domain_stats.items():
            count = stats["ideas_evaluated"]
            stats["avg_score"] = stats.pop("total_score") / count if count > 0 else 0.0
            store.insert_pipeline_run_domain(run_id, d, stats)

    except BudgetExceededError as e:
        logger.warning("Budget exceeded during pipeline: %s", e)
        result.budget_exceeded = True
        # Partial results are preserved and will be recorded in finally block

    finally:
        # Populate cost metrics from token tracker
        result.token_usage = token_tracker.summary()
        result.estimated_cost_usd = token_tracker.estimated_cost_usd()
        result.cost_by_stage = token_tracker.cost_by_stage()
        store.update_pipeline_run(
            run_id,
            signals_fetched=result.signals_fetched,
            signals_new=result.signals_new,
            insights_generated=result.insights_generated,
            ideas_generated=result.ideas_generated,
            ideas_evaluated=result.ideas_evaluated,
            clusters_found=result.clusters_found,
            gaps_detected=result.gaps_detected,
            avg_idea_score=result.avg_idea_score,
            fetch_allocation=result.fetch_allocation,
            token_usage=result.token_usage,
            adapter_metrics=result.adapter_metrics,
        )
        store.close()

    return result


def _resolve_evidence_chain(unit: BuildableUnit, store: Store) -> str | None:
    """Resolve unit -> insights -> signals and format as JSON for the evaluator."""
    insights_data = []
    signal_ids_seen: set[str] = set()
    signals_data = []

    # Resolve inspiring insights
    for ins_id in unit.inspiring_insights:
        insight = store.get_insight(ins_id)
        if insight:
            insights_data.append({
                "id": insight.id,
                "title": insight.title,
                "summary": insight.summary,
                "confidence": insight.confidence,
            })
            # Collect signals referenced by this insight
            for sig_id in insight.evidence:
                if sig_id not in signal_ids_seen:
                    signal = store.get_signal(sig_id)
                    if signal:
                        signal_ids_seen.add(sig_id)
                        signals_data.append({
                            "id": signal.id,
                            "title": signal.title,
                            "content": signal.content[:500],
                            "source": signal.source_adapter,
                            "signal_role": signal.signal_role,
                            "url": signal.url,
                        })

    # Also resolve direct evidence signals on the unit
    for sig_id in unit.evidence_signals:
        if sig_id not in signal_ids_seen:
            signal = store.get_signal(sig_id)
            if signal:
                signal_ids_seen.add(sig_id)
                signals_data.append({
                    "id": signal.id,
                    "title": signal.title,
                    "content": signal.content[:500],
                    "source": signal.source_adapter,
                    "url": signal.url,
                })

    if not insights_data and not signals_data:
        return None

    return json.dumps({"insights": insights_data, "signals": signals_data}, indent=2)


def _fetch_all_signals(
    *,
    signal_limit: int = 30,
    store: Store | None = None,
    source_configs: list | None = None,
) -> tuple[list[Signal], dict[str, int], dict[str, dict]]:
    """Fetch signals from all registered adapters with optional adaptive allocation.

    When *source_configs* is provided, only the configured (and enabled) adapters
    are instantiated with their per-adapter params.

    Returns (signals, allocation_used, adapter_metrics).
    """
    adapters = get_all_adapters(source_configs)
    all_signals: list[Signal] = []
    adapter_metrics: dict[str, dict] = {}

    if store:
        from max.pipeline.fetch_strategy import compute_fetch_allocation

        adapter_names = [a.name for a in adapters]
        allocation = compute_fetch_allocation(signal_limit, adapter_names, store)
    else:
        per_adapter = max(signal_limit // len(adapters), 5) if adapters else signal_limit
        allocation = {a.name: per_adapter for a in adapters}

    for adapter in adapters:
        limit = allocation.get(adapter.name, 5)
        t0 = time.monotonic()
        try:
            signals = asyncio.run(adapter.fetch(limit=limit))
            duration_ms = int((time.monotonic() - t0) * 1000)
            all_signals.extend(signals)
            adapter_metrics[adapter.name] = {
                "status": "ok",
                "signal_count": len(signals),
                "error_message": None,
                "duration_ms": duration_ms,
            }
        except AdapterCircuitOpenError as e:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "%s circuit breaker open, skipping (retry in %.0fs)",
                adapter.name,
                e.retry_after,
            )
            adapter_metrics[adapter.name] = {
                "status": "circuit_open",
                "signal_count": 0,
                "error_message": str(e),
                "duration_ms": duration_ms,
            }
        except Exception as e:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.warning("%s fetch failed: %s", adapter.name, e)
            adapter_metrics[adapter.name] = {
                "status": "error",
                "signal_count": 0,
                "error_message": str(e),
                "duration_ms": duration_ms,
            }

    return all_signals, allocation, adapter_metrics
