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
from max.ideation.critique import apply_critiques, critique_ideas, critique_to_record
from max.ideation.evidence import build_evidence_pack
from max.ideation.engine import ideate, ideate_cross_domain, ideate_refinement
from max.ideation.quality_gate import quality_gate
from max.ideation.revision import revise_ideas
from max.llm.client import BudgetExceededError, token_tracker
from max.pipeline.dedup import dedup_buildable_units, dedup_insights
from max.sources.base import AdapterCircuitOpenError
from max.sources.registry import get_all_adapters
from max.store.db import Store
from max.synthesis.engine import synthesize
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation
from max.types.pipeline import DryRunReport, StageSummary
from max.types.signal import Signal

if TYPE_CHECKING:
    from max.profiles.schema import DomainContext, PipelineProfile

logger = logging.getLogger(__name__)

IDEATION_CONTEXT_LIMIT = 12

# Pipeline stage execution order
STAGE_ORDER = [
    'fetch',
    'annotate',
    'synthesize',
    'detect_gaps',
    'retrospective',
    'ideate',
    'evaluate',
]

# Post-evaluation stages (run after all profiles complete)
POST_EVAL_STAGES = [
    'dedup',
    'synthesize_ideas',
    'prior_art',
    'triage',
]


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
    draft_ideas_generated: int = 0
    ideas_revised: int = 0
    ideas_rejected_by_quality_gate: int = 0
    avg_novelty_score: float = 0.0
    avg_usefulness_score: float = 0.0

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
    status: str = "completed"
    error_message: str = ""


@dataclass
class PostPipelineResult:
    """Summary of post-evaluation stages (dedup → synthesize → prior-art → triage)."""

    # Dedup
    duplicates_found: int = 0
    duplicates_marked: int = 0

    # Synthesize ideas
    synthesis_clusters: int = 0
    ideas_synthesized: int = 0
    source_ideas_merged: int = 0

    # Prior art
    prior_art_checked: int = 0
    prior_art_strong: int = 0
    prior_art_weak: int = 0
    prior_art_clear: int = 0

    # Triage
    triage_auto_approved: int = 0
    triage_auto_rejected: int = 0
    triage_pending_review: int = 0


def run_pipeline(
    *,
    profile: PipelineProfile | None = None,
    output_dir: Path | None = None,
    signal_limit: int = 30,
    min_score: float = 50.0,
    weight_profile: str = "default",
    ideation_mode: str = "direct",
    quality_loop_enabled: bool = False,
    draft_count: int = 8,
    dry_run: bool = False,
    stages: list[str] | None = None,
) -> PipelineResult | DryRunReport:
    """Run the full pipeline: fetch → synthesize → ideate → evaluate → spec → publish.

    When *profile* is provided, pipeline parameters are extracted from it.
    Explicit keyword arguments override profile values when both are given.

    Args:
        dry_run: If True, simulate execution without LLM calls or writes, return DryRunReport
        stages: If provided, only execute the listed stages (in pipeline order)
    """
    # Validate stages parameter
    if stages is not None:
        unknown = set(stages) - set(STAGE_ORDER)
        if unknown:
            raise ValueError(f"Unknown stages: {', '.join(sorted(unknown))}. Valid stages: {', '.join(STAGE_ORDER)}")
        # Filter to requested stages in pipeline order
        active_stages = [s for s in STAGE_ORDER if s in stages]
    else:
        active_stages = STAGE_ORDER[:]
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
        quality_loop_enabled = profile.quality_loop_enabled
        draft_count = profile.draft_count

    token_tracker.reset()
    store = Store()

    # Dry-run mode: simulate execution without LLM calls or writes
    if dry_run:
        report = _generate_dry_run_report(
            store=store,
            active_stages=active_stages,
            signal_limit=signal_limit,
            ideation_mode=ideation_mode,
            quality_loop_enabled=quality_loop_enabled,
            draft_count=draft_count,
            source_configs=source_configs,
            domain=domain,
        )
        store.close()
        return report

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
        "quality_loop_enabled": quality_loop_enabled,
        "draft_count": draft_count,
        "profile": profile.name if profile else None,
    }
    store.insert_pipeline_run(run_id, config)
    pipeline_error: BaseException | None = None

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
        signals = []
        if 'fetch' in active_stages:
            signals, fetch_alloc, adapter_metrics = _fetch_all_signals(
                signal_limit=signal_limit, store=store, source_configs=source_configs,
            )
            result.signals_fetched = len(signals)
            result.fetch_allocation = fetch_alloc
            result.adapter_metrics = adapter_metrics

        # 1.1 Annotate signal roles (problem / solution / market)
        if 'annotate' in active_stages and signals:
            annotate_signals(signals)

        if 'fetch' in active_stages:
            pre_count = store.count_signals()
            for sig in signals:
                store.insert_signal(sig)
            result.signals_new = store.count_signals() - pre_count

        # 2. Synthesize insights (incremental — only new signals)
        insights = []
        if 'synthesize' in active_stages:
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
        gaps = []
        gaps_ctx = None
        if 'detect_gaps' in active_stages:
            gaps = detect_gaps(store)
            result.gaps_detected = len(gaps)
            gaps_ctx = format_gaps_for_ideation(gaps)

        # 3.5 Retrospective analysis (learned patterns from feedback history)
        retrospective = None
        learned_ctx = None
        if 'retrospective' in active_stages:
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
        units: list[BuildableUnit] = []
        rejected_by_quality_gate: list[BuildableUnit] = []
        critique_records_by_title: dict[str, dict] = {}
        critique_records_by_unit_id: dict[str, dict] = {}
        evidence_pack_json: str | None = None
        if 'ideate' in active_stages:
            # Prefer current-run insights; fall back to domain-filtered store insights
            if insights:
                recent_insights = insights[:IDEATION_CONTEXT_LIMIT]
            else:
                all_insights = store.get_insights(limit=50)
                recent_insights = _filter_insights_for_domain(all_insights, domain)

            # Scope existing ideas to current domain to avoid cross-domain contamination
            domain_name = domain.name if domain else None
            recent_ideas = store.get_buildable_units(limit=30, domain=domain_name)

            if ideation_mode in ("direct", "all"):
                units.extend(ideate(
                    recent_insights,
                    existing_ideas=recent_ideas or None,
                    gaps_context=gaps_ctx,
                    learned_context=learned_ctx,
                    domain=domain,
                ))

            if ideation_mode in ("refinement", "all"):
                existing = store.get_buildable_units(
                    status="evaluated", limit=10, domain=domain_name,
                )
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

            result.draft_ideas_generated = len(units)

            if quality_loop_enabled and units:
                evidence_pack = build_evidence_pack(
                    insights=recent_insights,
                    store=store,
                    domain=domain,
                    gaps=gaps,
                )
                draft_units = units[: max(1, draft_count)]
                critiques = critique_ideas(draft_units, evidence_pack)
                critique_records_by_title = {
                    c.title.lower(): critique_to_record(c)
                    for c in critiques
                }
                evidence_pack_json = evidence_pack.to_json()
                draft_units = apply_critiques(draft_units, critiques)
                revised_units = revise_ideas(
                    draft_units,
                    critiques,
                    evidence_pack,
                    recent_insights,
                )
                revised_units = apply_critiques(revised_units, critiques)
                for i, unit in enumerate(revised_units):
                    if i >= len(critiques):
                        continue
                    critique = critiques[i]
                    critique_record = critique_to_record(critique)
                    critique_records_by_unit_id[unit.id] = critique_record
                    if unit.quality_score == 0.0:
                        unit.novelty_score = max(0.0, min(10.0, critique.novelty))
                        unit.usefulness_score = max(0.0, min(10.0, critique.usefulness))
                        unit.quality_score = max(0.0, min(10.0, critique.quality_score))
                        unit.rejection_tags = critique.rejection_tags
                kept_units, rejected_units = quality_gate(revised_units)
                rejected_by_quality_gate = rejected_units
                units = kept_units
                result.ideas_revised = len(revised_units)
                result.ideas_rejected_by_quality_gate = len(rejected_units)
                if revised_units:
                    result.avg_novelty_score = (
                        sum(u.novelty_score for u in revised_units) / len(revised_units)
                    )
                    result.avg_usefulness_score = (
                        sum(u.usefulness_score for u in revised_units) / len(revised_units)
                    )

            # Collect product names from existing ideas in the store
            from max.pipeline.dedup import _extract_product_name

            existing_units = store.get_buildable_units(limit=500)
            existing_names = {
                _extract_product_name(u.title)
                for u in existing_units
                if u.status not in ("rejected", "duplicate")
            }

            # Index existing ideas into semantic index so dedup catches
            # semantically similar ideas across runs (not just within a batch)
            for eu in existing_units:
                if eu.status not in ("rejected", "duplicate"):
                    eu_text = f"{eu.title} {eu.one_liner or ''}"
                    semantic_index.index_entity(eu.id, "buildable_unit", eu_text)

            dedup = dedup_buildable_units(
                units, semantic_index, existing_names=existing_names,
            )
            units = dedup.kept
            result.ideas_duplicates_skipped = dedup.duplicates
            domain_name = domain.name if domain else ""
            for rejected in rejected_by_quality_gate:
                rejected.domain = domain_name
                rejected.status = "rejected"
                store.insert_buildable_unit(rejected)
                critique = critique_records_by_unit_id.get(
                    rejected.id
                ) or critique_records_by_title.get(
                    rejected.title.lower()
                ) or _unit_quality_record(rejected)
                if critique:
                    store.insert_idea_critique(
                        rejected.id,
                        critique,
                        evidence_pack=evidence_pack_json,
                        pipeline_run_id=run_id,
                        stage="quality_gate_rejected",
                    )
                store.insert_idea_memory(
                    unit_id=rejected.id,
                    domain=domain_name,
                    outcome="quality_rejected",
                    pattern=f"{rejected.title}: {rejected.one_liner or rejected.problem}",
                    rejection_tags=rejected.rejection_tags,
                    score=rejected.quality_score,
                    evidence_rationale=rejected.evidence_rationale,
                )
            for unit in units:
                unit.domain = domain_name
                store.insert_buildable_unit(unit)
                critique = critique_records_by_unit_id.get(
                    unit.id
                ) or critique_records_by_title.get(
                    unit.title.lower()
                ) or _unit_quality_record(unit)
                if critique:
                    store.insert_idea_critique(
                        unit.id,
                        critique,
                        evidence_pack=evidence_pack_json,
                        pipeline_run_id=run_id,
                    )
                if quality_loop_enabled:
                    store.insert_idea_memory(
                        unit_id=unit.id,
                        domain=domain_name,
                        outcome="quality_passed",
                        pattern=f"{unit.title}: {unit.one_liner or unit.problem}",
                        rejection_tags=unit.rejection_tags,
                        score=unit.quality_score,
                        evidence_rationale=unit.evidence_rationale,
                    )
            result.ideas_generated = len(units)

        # 5. Evaluate (using selected weight profile, with evidence grounding)
        evaluated: list[tuple[BuildableUnit, UtilityEvaluation]] = []
        if 'evaluate' in active_stages and units:
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
        result.status = "budget_exceeded"
        result.error_message = str(e)
        # Partial results are preserved and will be recorded in finally block
    except Exception as e:
        logger.exception("Pipeline failed during run %s", run_id)
        result.status = "failed"
        result.error_message = f"{type(e).__name__}: {e}"
        pipeline_error = e

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
            status=result.status,
            error_message=result.error_message,
        )
        store.close()

    if pipeline_error is not None:
        raise pipeline_error

    return result


def _filter_insights_for_domain(
    insights: list, domain: DomainContext | None,
) -> list:
    """Filter insights to those relevant to the given domain.

    Uses a strict whitelist of domain-specific terms derived from the profile
    domain name.  Only insight ``domains`` entries are checked (not titles),
    reducing false matches from generic words.

    Returns up to the ideation context limit, or an empty list if nothing matches.
    """
    if domain is None or not insights:
        return insights[:IDEATION_CONTEXT_LIMIT]

    # Map profile domain names to strict keyword sets for insight domain matching
    _DOMAIN_KEYWORDS: dict[str, set[str]] = {
        "developer-tools": {
            "developer_tools", "developer_tool", "devtools", "mcp",
            "mcp_ecosystem", "cli", "sdk", "ide",
        },
        "ai-infrastructure": {
            "ai_infrastructure", "ml_infrastructure", "mlops", "ml_ops",
            "model_serving", "inference", "training", "fine_tuning",
            "vector_database", "gpu", "cuda",
        },
        "healthcare": {
            "healthcare", "health_tech", "healthtech", "digital_health",
            "clinical", "ehr", "fhir", "medical", "patient",
            "telemedicine", "hipaa",
        },
    }

    match_terms = _DOMAIN_KEYWORDS.get(domain.name, set())
    if not match_terms:
        # Unknown domain — derive from domain name
        match_terms = {domain.name.lower().replace("-", "_")}

    matched = []
    for ins in insights:
        ins_domains_lower = {d.lower() for d in (ins.domains or [])}
        if ins_domains_lower & match_terms:
            matched.append(ins)

    return matched[:IDEATION_CONTEXT_LIMIT]


def _unit_quality_record(unit: BuildableUnit) -> dict | None:
    """Build a persistence record from scores already copied onto a unit."""
    if (
        unit.quality_score == 0.0
        and unit.novelty_score == 0.0
        and unit.usefulness_score == 0.0
        and not unit.rejection_tags
    ):
        return None
    return {
        "urgency": 0.0,
        "buyer_clarity": 0.0,
        "specificity": 0.0,
        "evidence_support": 0.0,
        "feasibility": 0.0,
        "differentiation": 0.0,
        "distribution_path": 0.0,
        "domain_risk": 0.0,
        "novelty": unit.novelty_score,
        "usefulness": unit.usefulness_score,
        "quality_score": unit.quality_score,
        "reasoning": unit.evidence_rationale,
        "rejection_tags": unit.rejection_tags,
    }


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


def _generate_dry_run_report(
    *,
    store: Store,
    active_stages: list[str],
    signal_limit: int,
    ideation_mode: str,
    quality_loop_enabled: bool = False,
    draft_count: int = 8,
    source_configs: list | None = None,
    domain: DomainContext | None = None,
) -> DryRunReport:
    """Generate a dry-run report simulating pipeline execution without LLM calls or writes."""
    stage_summaries: list[StageSummary] = []
    total_llm_calls = 0

    # Stage: fetch
    if 'fetch' in active_stages:
        adapters = get_all_adapters(source_configs)
        if store:
            from max.pipeline.fetch_strategy import compute_fetch_allocation
            adapter_names = [a.name for a in adapters]
            allocation = compute_fetch_allocation(signal_limit, adapter_names, store)
        else:
            per_adapter = max(signal_limit // len(adapters), 5) if adapters else signal_limit
            allocation = {a.name: per_adapter for a in adapters}

        total_to_fetch = sum(allocation.values())
        stage_summaries.append(StageSummary(
            name='fetch',
            would_process=total_to_fetch,
            estimated_llm_calls=0,  # No LLM calls in fetch
            skipped=total_to_fetch == 0,
            reason='no adapters configured' if total_to_fetch == 0 else '',
        ))
    else:
        stage_summaries.append(StageSummary(
            name='fetch',
            would_process=0,
            estimated_llm_calls=0,
            skipped=True,
            reason='stage not selected',
        ))

    # Stage: annotate
    if 'annotate' in active_stages:
        # Estimate based on fetch count
        fetch_count = stage_summaries[0].would_process if stage_summaries else 0
        stage_summaries.append(StageSummary(
            name='annotate',
            would_process=fetch_count,
            estimated_llm_calls=0,  # Role annotation uses heuristics, not LLM
            skipped=fetch_count == 0,
            reason='no signals to annotate' if fetch_count == 0 else '',
        ))
    else:
        stage_summaries.append(StageSummary(
            name='annotate',
            would_process=0,
            estimated_llm_calls=0,
            skipped=True,
            reason='stage not selected',
        ))

    # Stage: synthesize
    if 'synthesize' in active_stages:
        unsynthesized = store.get_unsynthesized_signals(limit=signal_limit)
        unsynthesized_count = len(unsynthesized)
        # Estimate LLM calls: ~1 call per batch of 5 signals (rough estimate)
        llm_calls = max((unsynthesized_count + 4) // 5, 0)
        total_llm_calls += llm_calls
        stage_summaries.append(StageSummary(
            name='synthesize',
            would_process=unsynthesized_count,
            estimated_llm_calls=llm_calls,
            skipped=unsynthesized_count == 0,
            reason='no new signals since last run' if unsynthesized_count == 0 else '',
        ))
    else:
        stage_summaries.append(StageSummary(
            name='synthesize',
            would_process=0,
            estimated_llm_calls=0,
            skipped=True,
            reason='stage not selected',
        ))

    # Stage: detect_gaps
    if 'detect_gaps' in active_stages:
        # Gap detection analyzes existing insights, no new LLM calls
        recent_insights = store.get_insights(limit=20)
        stage_summaries.append(StageSummary(
            name='detect_gaps',
            would_process=len(recent_insights),
            estimated_llm_calls=0,
            skipped=len(recent_insights) == 0,
            reason='no insights to analyze' if len(recent_insights) == 0 else '',
        ))
    else:
        stage_summaries.append(StageSummary(
            name='detect_gaps',
            would_process=0,
            estimated_llm_calls=0,
            skipped=True,
            reason='stage not selected',
        ))

    # Stage: retrospective
    if 'retrospective' in active_stages:
        feedback_outcomes = store.get_feedback_outcomes()
        stage_summaries.append(StageSummary(
            name='retrospective',
            would_process=len(feedback_outcomes),
            estimated_llm_calls=0,
            skipped=len(feedback_outcomes) == 0,
            reason='no feedback history' if len(feedback_outcomes) == 0 else '',
        ))
    else:
        stage_summaries.append(StageSummary(
            name='retrospective',
            would_process=0,
            estimated_llm_calls=0,
            skipped=True,
            reason='stage not selected',
        ))

    # Stage: ideate
    if 'ideate' in active_stages:
        all_insights = store.get_insights(limit=50)
        recent_insights = _filter_insights_for_domain(all_insights, domain)
        # Estimate LLM calls based on ideation mode
        modes_count = {
            'direct': 1,
            'refinement': 1,
            'cross_domain': 1,
            'all': 3,
        }.get(ideation_mode, 1)
        llm_calls = modes_count * max(1, len(recent_insights) // 10)  # Rough estimate
        if quality_loop_enabled and recent_insights:
            # critique + revision; quality gate itself is deterministic.
            llm_calls += 2
        total_llm_calls += llm_calls
        stage_summaries.append(StageSummary(
            name='ideate',
            would_process=len(recent_insights),
            estimated_llm_calls=llm_calls,
            skipped=len(recent_insights) == 0,
            reason='no insights to ideate from' if len(recent_insights) == 0 else '',
        ))
    else:
        stage_summaries.append(StageSummary(
            name='ideate',
            would_process=0,
            estimated_llm_calls=0,
            skipped=True,
            reason='stage not selected',
        ))

    # Stage: evaluate
    if 'evaluate' in active_stages:
        # Estimate new ideas to evaluate (rough estimate based on ideation)
        ideate_summary = next((s for s in stage_summaries if s.name == 'ideate'), None)
        if ideate_summary and not ideate_summary.skipped:
            estimated_ideas = max(ideate_summary.would_process // 5, 1)
            if quality_loop_enabled:
                estimated_ideas = min(estimated_ideas, max(1, draft_count))
        else:
            estimated_ideas = 0
        llm_calls = estimated_ideas  # 1 LLM call per idea for evaluation
        total_llm_calls += llm_calls
        stage_summaries.append(StageSummary(
            name='evaluate',
            would_process=estimated_ideas,
            estimated_llm_calls=llm_calls,
            skipped=estimated_ideas == 0,
            reason='no ideas to evaluate' if estimated_ideas == 0 else '',
        ))
    else:
        stage_summaries.append(StageSummary(
            name='evaluate',
            would_process=0,
            estimated_llm_calls=0,
            skipped=True,
            reason='stage not selected',
        ))

    # Estimate token budget (rough: 2000 tokens per LLM call on average)
    estimated_tokens = total_llm_calls * 2000

    return DryRunReport(
        stages=stage_summaries,
        estimated_total_llm_calls=total_llm_calls,
        estimated_token_budget=estimated_tokens,
    )


def run_post_pipeline(
    *,
    domain: str | None = None,
    stages: list[str] | None = None,
    dedup_threshold: float = 0.85,
    triage_approve_threshold: float = 68.0,
    triage_reject_threshold: float = 50.0,
    prior_art_auto_reject: bool = False,
    limit: int = 500,
) -> PostPipelineResult:
    """Run post-evaluation stages: dedup → synthesize_ideas → prior_art → triage.

    These stages operate across all domains and should run after all per-profile
    pipeline runs complete.

    Args:
        domain: Optional domain filter (None = all domains).
        stages: If provided, only run these post-eval stages.
        dedup_threshold: Similarity threshold for dedup clustering.
        triage_approve_threshold: Score threshold for auto-approve.
        triage_reject_threshold: Score threshold for auto-reject.
        prior_art_auto_reject: Auto-reject ideas with strong prior-art matches.
        limit: Max ideas to process per stage.
    """
    active_stages = stages if stages else POST_EVAL_STAGES[:]

    store = Store()
    result = PostPipelineResult()

    try:
        # 1. Dedup — cluster similar ideas, mark lower-scored duplicates
        if 'dedup' in active_stages:
            result.duplicates_found, result.duplicates_marked = _run_dedup(
                store, domain=domain, threshold=dedup_threshold, limit=limit,
            )

        # 2. Synthesize ideas — merge similar idea clusters into combined ideas
        if 'synthesize_ideas' in active_stages:
            synth = _run_synthesize_ideas(
                store, domain=domain, threshold=dedup_threshold, limit=limit,
            )
            result.synthesis_clusters = synth[0]
            result.ideas_synthesized = synth[1]
            result.source_ideas_merged = synth[2]

        # 3. Prior art — check for existing implementations
        if 'prior_art' in active_stages:
            pa = _run_prior_art(
                store, domain=domain, auto_reject=prior_art_auto_reject, limit=limit,
            )
            result.prior_art_checked = pa[0]
            result.prior_art_strong = pa[1]
            result.prior_art_weak = pa[2]
            result.prior_art_clear = pa[3]

        # 4. Triage — auto-approve/reject by score thresholds
        if 'triage' in active_stages:
            tri = _run_triage(
                store, domain=domain,
                approve_threshold=triage_approve_threshold,
                reject_threshold=triage_reject_threshold,
                limit=limit,
            )
            result.triage_auto_approved = tri[0]
            result.triage_auto_rejected = tri[1]
            result.triage_pending_review = tri[2]

    finally:
        store.close()

    return result


def _run_dedup(
    store: Store,
    *,
    domain: str | None,
    threshold: float,
    limit: int,
) -> tuple[int, int]:
    """Dedup stage: cluster ideas, mark duplicates. Returns (found, marked)."""
    from max.analysis.dedup import cluster_ideas

    units = store.get_buildable_units(limit=limit, domain=domain)
    ideas = []
    for unit in units:
        if unit.status in ("duplicate", "archived"):
            continue
        ev = store.get_evaluation(unit.id)
        if ev:
            ideas.append((unit, ev))

    if not ideas:
        return 0, 0

    clusters = cluster_ideas(ideas, similarity_threshold=threshold)
    dup_clusters = [c for c in clusters if c.size > 1]

    if not dup_clusters:
        return 0, 0

    total_found = sum(len(c.duplicates) for c in dup_clusters)
    marked = 0
    for cluster in dup_clusters:
        cluster_marked = 0
        for unit, ev in cluster.duplicates:
            # Preserve prior user decisions — don't overwrite approved/rejected status
            if unit.status in ("approved", "rejected"):
                continue
            reason = f"duplicate of {cluster.representative.id} ({cluster.representative.title[:50]})"
            store.insert_feedback(unit.id, "rejected", f"auto-dedup: {reason}")
            store.update_buildable_unit_status(unit.id, "duplicate")
            marked += 1
            cluster_marked += 1
        logger.info(
            "Dedup cluster: KEEP %s (status=%s), marked %d/%d duplicates",
            cluster.representative.title[:50],
            cluster.representative.status,
            cluster_marked,
            len(cluster.duplicates),
        )

    return total_found, marked


def _run_synthesize_ideas(
    store: Store,
    *,
    domain: str | None,
    threshold: float,
    limit: int,
) -> tuple[int, int, int]:
    """Synthesize stage: merge similar idea clusters. Returns (clusters, synthesized, source_count)."""
    from max.analysis.dedup import cluster_ideas
    from max.analysis.synthesize_ideas import run_synthesis

    units = store.get_buildable_units(limit=limit, domain=domain)
    active = [
        u for u in units
        if u.status not in ("rejected", "duplicate", "synthesized", "archived")
    ]

    pairs = []
    for u in active:
        ev = store.get_evaluation(u.id)
        if ev:
            pairs.append((u, ev))

    if not pairs:
        return 0, 0, 0

    clusters = cluster_ideas(pairs, similarity_threshold=threshold)
    multi_clusters = [c for c in clusters if c.size > 1]

    if not multi_clusters:
        return 0, 0, 0

    synth_result = run_synthesis(clusters)

    # Store synthesized ideas and update source statuses
    for new_unit in synth_result.intra_synthesized:
        store.insert_buildable_unit(new_unit)
        for src_id in new_unit.source_idea_ids:
            store.insert_feedback(src_id, "synthesized", f"merged into {new_unit.id}")
            store.update_buildable_unit_status(src_id, "synthesized")
        logger.info("Synthesized: %s", new_unit.title[:60])

    for new_unit in synth_result.cross_synthesized:
        store.insert_buildable_unit(new_unit)
        for src_id in new_unit.source_idea_ids:
            store.insert_feedback(src_id, "synthesized", f"cross-merged into {new_unit.id}")
            store.update_buildable_unit_status(src_id, "synthesized")
        logger.info("Cross-synthesized: %s", new_unit.title[:60])

    total_synth = len(synth_result.intra_synthesized) + len(synth_result.cross_synthesized)
    return len(multi_clusters), total_synth, len(synth_result.source_idea_ids)


def _run_prior_art(
    store: Store,
    *,
    domain: str | None,
    auto_reject: bool,
    limit: int,
) -> tuple[int, int, int, int]:
    """Prior-art stage: search for existing implementations. Returns (checked, strong, weak, clear)."""
    from max.analysis.prior_art import check_prior_art

    units = store.get_buildable_units(limit=limit, domain=domain)
    # Only unchecked, non-rejected/duplicate/archived ideas
    units = [
        u for u in units
        if u.prior_art_status == "unchecked"
        and u.status not in ("rejected", "duplicate", "archived")
    ]

    if not units:
        return 0, 0, 0, 0

    results = check_prior_art(units, dry_run=False)

    strong = 0
    weak = 0
    clear = 0

    for pa_result in results:
        unit = next(u for u in units if u.id == pa_result.buildable_unit_id)

        for match in pa_result.matches:
            store.insert_prior_art_match(unit.id, {
                "source": match.source,
                "title": match.title,
                "url": match.url,
                "description": match.description,
                "relevance_score": match.relevance_score,
                "match_signals": match.match_signals,
                "search_query": match.search_query,
            })

        store.update_prior_art_status(unit.id, pa_result.status)

        if pa_result.status == "strong_match":
            strong += 1
            logger.info("Prior-art STRONG match: %s", unit.title[:60])
            if auto_reject:
                store.insert_feedback(unit.id, "rejected", "auto-rejected: strong prior art match")
                store.update_buildable_unit_status(unit.id, "rejected")
        elif pa_result.status == "weak_match":
            weak += 1
        else:
            clear += 1

    return len(units), strong, weak, clear


def _run_triage(
    store: Store,
    *,
    domain: str | None,
    approve_threshold: float,
    reject_threshold: float,
    limit: int,
) -> tuple[int, int, int]:
    """Triage stage: auto-approve/reject by thresholds. Returns (approved, rejected, pending)."""
    units = store.get_buildable_units(limit=limit, domain=domain)

    auto_approved = []
    auto_rejected = []
    pending = 0

    for unit in units:
        if unit.status == "archived":
            continue
        ev = store.get_evaluation(unit.id)
        if not ev:
            continue
        if store.has_feedback(unit.id):
            continue

        if ev.overall_score >= approve_threshold and ev.recommendation == "yes":
            auto_approved.append((unit, ev))
        elif ev.overall_score < reject_threshold or ev.recommendation == "no":
            auto_rejected.append((unit, ev))
        else:
            pending += 1

    for unit, ev in auto_approved:
        store.insert_feedback(unit.id, "approved", "auto-triage: score >= threshold + rec=yes")
        store.update_buildable_unit_status(unit.id, "approved")
        logger.info("Auto-approved: %.1f  %s", ev.overall_score, unit.title[:60])

    for unit, ev in auto_rejected:
        reason = f"auto-triage: score={ev.overall_score:.1f}, rec={ev.recommendation}"
        store.insert_feedback(unit.id, "rejected", reason)
        store.update_buildable_unit_status(unit.id, "rejected")

    return len(auto_approved), len(auto_rejected), pending
