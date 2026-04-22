"""REST API routes for the max idea service."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from max import config
from max.analysis.export import idea_export_records, render_idea_export
from max.analysis.budget_usage import build_llm_budget_usage
from max.analysis.contradictions import (
    build_idea_contradiction_report,
    build_insight_contradiction_report,
)
from max.analysis.evidence_density import build_evidence_density_report
from max.analysis.evaluation_calibration import build_evaluation_calibration_report
from max.analysis.idea_similarity import find_similar_ideas
from max.analysis.opportunity_heatmap import build_opportunity_heatmap
from max.analysis.portfolio_overlap import find_portfolio_overlap_clusters
from max.analysis.profile_drift import (
    DEFAULT_INSIGHT_LIMIT as DEFAULT_PROFILE_DRIFT_INSIGHT_LIMIT,
    DEFAULT_SIGNAL_LIMIT as DEFAULT_PROFILE_DRIFT_SIGNAL_LIMIT,
    DEFAULT_UNIT_LIMIT as DEFAULT_PROFILE_DRIFT_UNIT_LIMIT,
    build_profile_drift_report,
)
from max.analysis.run_comparison import (
    PipelineRunComparisonNotFound,
    compare_pipeline_runs,
)
from max.analysis.roi_forecast import generate_roi_forecast
from max.analysis.signal_freshness import DEFAULT_MAX_AGE_DAYS, build_signal_freshness_report
from max.analysis.source_reliability import DEFAULT_SIGNAL_LIMIT, build_source_reliability_report
from max.analysis.status import (
    InvalidBuildableUnitStatusTransition,
    validate_buildable_unit_status_transition,
)
from max.analysis.thresholds import (
    DEFAULT_APPROVE_THRESHOLD,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_REJECT_THRESHOLD,
    recommend_review_thresholds,
)
from max.server.dependencies import get_store
from max.server.evidence_chain import build_evidence_chain_graph
from max.server.rate_limit import rate_limit
from max.server.schemas import (
    AdapterHealthItemResponse,
    AdapterHealthResponse,
    AdapterMetadataResponse,
    BlueprintSourceBriefResponse,
    CircuitBreakerStateResponse,
    ContradictionReportResponse,
    DesignBriefResponse,
    DesignBriefStatusUpdate,
    DesignBriefValidationPlanResponse,
    DomainQualityMemoryResponse,
    DomainQualityScoreResponse,
    DimensionScoreResponse,
    DryRunEffectiveConfigResponse,
    DryRunReportResponse,
    EvidenceChainResponse,
    EvidenceDensityResponse,
    EvaluationExplanationResponse,
    EvaluationCalibrationResponse,
    EvaluationResponse,
    EvaluationSummaryResponse,
    EvaluationWeightProfileResponse,
    FeedbackBatchItemResponse,
    FeedbackBatchRequest,
    FeedbackBatchResponse,
    FeedbackCreate,
    FeedbackTrendDomainResponse,
    FeedbackTrendResponse,
    FeedbackTrendWindowResponse,
    FeedbackWebhookRequest,
    FeedbackWebhookResponse,
    FetchAllocationAdapterExplainResponse,
    FetchAllocationExplainResponse,
    HealthResponse,
    IdeaCreate,
    IdeaCritiqueResponse,
    IdeaDetailResponse,
    IdeaEvaluateBatchItemResponse,
    IdeaEvaluateBatchRequest,
    IdeaEvaluateBatchResponse,
    IdeaMemoryResponse,
    OpportunityHeatmapBucketResponse,
    IdeaSimilarityRequest,
    IdeaSimilarityResultResponse,
    IdeaScoreDistributionResponse,
    IdeaStatusSummaryResponse,
    IdeaSummaryResponse,
    InsightCreate,
    InsightDetailResponse,
    InsightResponse,
    InsightTrendItemResponse,
    InsightTrendResponse,
    LLMUsageResponse,
    LLMUsageRunResponse,
    LLMBudgetUsageResponse,
    LaunchChecklistResponse,
    LineageGraphEdgeResponse,
    LineageGraphNodeResponse,
    LineageGraphResponse,
    PaginatedResponse,
    PaginationMeta,
    PipelineAggregateResultResponse,
    PipelineDryRunRequest,
    PipelinePostRunRequest,
    PipelinePostRunResponse,
    PipelineRunComparisonResponse,
    PipelineResultResponse,
    PipelineRunHistoryResponse,
    PipelineRunRequest,
    PipelineTrendResponse,
    PipelineTrendWindowResponse,
    PortfolioOverlapClusterResponse,
    PublicationAttemptResponse,
    PriorArtCheckRequest,
    PriorArtResponse,
    ProfileDetailResponse,
    ProfileCoverageGapsResponse,
    ProfileCoverageTermResponse,
    ProfileDriftResponse,
    ProfileSummaryResponse,
    ProfileValidationIssueResponse,
    ProfileValidationResponse,
    ProfileValidationResultResponse,
    ReviewQueueItemResponse,
    ReviewThresholdRecommendationResponse,
    ReviewThresholdsResponse,
    RoiForecastResponse,
    ScheduleStatusResponse,
    ScheduleUpdateRequest,
    SignalCreate,
    SignalCreateResponse,
    SignalFreshnessResponse,
    SignalImportRequest,
    SignalImportResponse,
    SignalImportRowResult,
    SourceReliabilityResponse,
    SignalResponse,
    SimilarityRequest,
    SimilarityResult,
    StageSummaryResponse,
    StatsResponse,
)
from max.evaluation.explain import explain_evaluation
from max.evaluation.weights import WEIGHT_PROFILES, get_adapted_weights, get_weights
from max.llm.client import estimate_token_cost_usd, token_counts_from_usage
from max.spec.generator import generate_spec_preview
from max.spec.implementation_plan import generate_implementation_plan
from max.spec.launch_checklist import generate_launch_checklist
from max.spec.readiness import evaluate_spec_readiness
from max.sources.base import snapshot_circuit_breakers
from max.sources.registry import list_adapter_metadata, list_adapters
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation
from max.types.insight import Insight
from max.types.signal import Signal

router = APIRouter()


# ── Health ──────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
def health_check(request: Request, store: Store = Depends(get_store)) -> HealthResponse:
    try:
        store.count_signals()
        db_ok = True
    except Exception:
        db_ok = False

    version = store.get_schema_version() if db_ok else 0
    started_at = getattr(request.app.state, "started_at", None)
    uptime = time.monotonic() - started_at if started_at is not None else 0.0

    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        database=db_ok,
        version=version,
        uptime_seconds=uptime,
    )


# ── Pipeline Run History ────────────────────────────────────────────


@router.get("/pipeline/runs", response_model=list[PipelineRunHistoryResponse])
def list_pipeline_runs(limit: int = 10, store: Store = Depends(get_store)) -> list[PipelineRunHistoryResponse]:
    runs = store.get_pipeline_runs(limit=limit)
    return [
        PipelineRunHistoryResponse(
            id=r["id"],
            started_at=r["started_at"],
            finished_at=r["completed_at"],
            signals_fetched=r["signals_fetched"],
            insights_generated=r["insights_generated"],
            ideas_generated=r["ideas_generated"],
            ideas_evaluated=r["ideas_evaluated"],
            status="completed" if r["completed_at"] else "running",
        )
        for r in runs
    ]


@router.get("/pipeline/runs/compare", response_model=PipelineRunComparisonResponse)
def compare_pipeline_runs_endpoint(
    base_run_id: str = Query(..., min_length=1),
    target_run_id: str = Query(..., min_length=1),
    store: Store = Depends(get_store),
) -> PipelineRunComparisonResponse:
    try:
        comparison = compare_pipeline_runs(
            store,
            base_run_id=base_run_id,
            target_run_id=target_run_id,
        )
    except PipelineRunComparisonNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Pipeline run ID not found",
                "missing_run_ids": exc.missing_run_ids,
            },
        ) from exc
    return PipelineRunComparisonResponse.model_validate(comparison)


# ── LLM Usage ───────────────────────────────────────────────────────


@router.get("/usage/llm", response_model=LLMUsageResponse)
def llm_usage(
    limit: int = Query(20, ge=1, le=500),
    store: Store = Depends(get_store),
) -> LLMUsageResponse:
    runs = store.get_pipeline_runs(limit=limit)
    total_input = 0
    total_output = 0
    total_cost = 0.0
    run_breakdown: list[LLMUsageRunResponse] = []

    for run in runs:
        token_usage = run.get("token_usage", {})
        input_tokens, output_tokens = token_counts_from_usage(token_usage)
        model = str(run.get("config", {}).get("model") or config.MODEL)
        stored_cost = token_usage.get("estimated_cost_usd")
        cost = (
            float(stored_cost)
            if isinstance(stored_cost, (int, float))
            else estimate_token_cost_usd(input_tokens, output_tokens, model=model)
        )

        total_input += input_tokens
        total_output += output_tokens
        total_cost += cost
        run_breakdown.append(
            LLMUsageRunResponse(
                id=run["id"],
                started_at=run["started_at"],
                finished_at=run["completed_at"],
                status=run.get("status")
                or ("completed" if run["completed_at"] else "running"),
                model=model,
                total_input=input_tokens,
                total_output=output_tokens,
                total_cost_usd=cost,
                token_usage=token_usage,
            )
        )

    return LLMUsageResponse(
        limit=limit,
        run_count=len(run_breakdown),
        total_input=total_input,
        total_output=total_output,
        total_cost_usd=total_cost,
        runs=run_breakdown,
    )


@router.get("/budget/usage", response_model=LLMBudgetUsageResponse)
def llm_budget_usage(
    limit: int = Query(20, ge=1, le=500),
    include_current: bool = Query(True),
    store: Store = Depends(get_store),
) -> LLMBudgetUsageResponse:
    return LLMBudgetUsageResponse.model_validate(
        build_llm_budget_usage(store, limit=limit, include_current=include_current)
    )


# ── Helpers ─────────────────────────────────────────────────────────


def _signal_to_response(sig: Signal) -> SignalResponse:
    return SignalResponse(
        id=sig.id,
        source_type=sig.source_type.value if hasattr(sig.source_type, "value") else sig.source_type,
        source_adapter=sig.source_adapter,
        signal_role=sig.signal_role,
        title=sig.title,
        content=sig.content,
        url=sig.url,
        author=sig.author,
        published_at=sig.published_at.isoformat() if sig.published_at else None,
        fetched_at=sig.fetched_at.isoformat() if hasattr(sig.fetched_at, "isoformat") else sig.fetched_at,
        tags=sig.tags,
        credibility=sig.credibility,
        metadata=sig.metadata,
    )


def _parse_signal_import_metadata(value) -> dict:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("metadata must be a JSON object")
        return parsed
    raise ValueError("metadata must be an object")


def _merge_signal_import_tags(default_tags: list[str], row_tags) -> list[str]:
    parsed: list[str] = []
    if isinstance(row_tags, list):
        parsed = [str(tag).strip() for tag in row_tags]
    elif isinstance(row_tags, str) and row_tags.strip():
        text = row_tags.strip()
        if text.startswith("["):
            loaded = json.loads(text)
            if not isinstance(loaded, list):
                raise ValueError("tags must be a list")
            parsed = [str(tag).strip() for tag in loaded]
        else:
            parsed = [tag.strip() for tag in text.split(",")]

    merged: list[str] = []
    for tag in [*default_tags, *parsed]:
        normalized = str(tag).strip()
        if normalized and normalized not in merged:
            merged.append(normalized)
    return merged


def _signal_from_import_row(row, body: SignalImportRequest) -> Signal:
    clean = {
        key: value
        for key, value in row.model_dump().items()
        if value not in (None, "")
    }
    missing = [
        field
        for field in ("title", "content", "url")
        if not str(clean.get(field, "")).strip()
    ]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")

    metadata = _parse_signal_import_metadata(clean.get("metadata"))
    if clean.get("signal_role"):
        metadata["signal_role"] = str(clean["signal_role"]).strip()

    signal_kwargs = dict(
        id=str(clean.get("id", "")),
        source_type=str(clean.get("source_type") or body.source_type or "forum"),
        source_adapter=str(clean.get("source_adapter") or body.source_adapter or "import"),
        title=str(clean["title"]).strip(),
        content=str(clean["content"]).strip(),
        url=str(clean["url"]).strip(),
        author=str(clean["author"]).strip() if clean.get("author") else None,
        published_at=clean.get("published_at"),
        tags=_merge_signal_import_tags(body.tags, clean.get("tags")),
        credibility=float(
            clean.get(
                "credibility",
                body.credibility if body.credibility is not None else 0.5,
            )
        ),
        metadata=metadata,
    )
    if clean.get("fetched_at"):
        signal_kwargs["fetched_at"] = clean["fetched_at"]
    return Signal(**signal_kwargs)


def _insight_to_response(ins: Insight) -> InsightResponse:
    return InsightResponse(
        id=ins.id,
        category=ins.category.value if hasattr(ins.category, "value") else ins.category,
        title=ins.title,
        summary=ins.summary,
        evidence=ins.evidence,
        confidence=ins.confidence,
        domains=ins.domains,
        implications=ins.implications,
        time_horizon=ins.time_horizon,
        created_at=ins.created_at.isoformat() if hasattr(ins.created_at, "isoformat") else ins.created_at,
    )


def _insight_detail_to_response(ins: Insight, store: Store) -> InsightDetailResponse:
    evidence_signals: list[SignalResponse] = []
    missing_evidence_ids: list[str] = []

    for signal_id in ins.evidence:
        signal = store.get_signal(signal_id)
        if signal:
            evidence_signals.append(_signal_to_response(signal))
        else:
            missing_evidence_ids.append(signal_id)

    return InsightDetailResponse(
        **_insight_to_response(ins).model_dump(),
        evidence_signals=evidence_signals,
        missing_evidence_ids=missing_evidence_ids,
    )


def _review_metadata(unit, latest_feedback: dict | None = None) -> dict:
    """Return explicit review fields for graph/API consumers."""
    outcome = latest_feedback["outcome"] if latest_feedback else None
    state = outcome or unit.status or "pending"
    if state == "evaluated":
        state = "pending_review"
    elif state == "draft":
        state = "draft"
    graph_state = "".join(part.capitalize() for part in state.replace("-", "_").split("_"))
    return {
        "review_state": state,
        "feedback_outcome": outcome,
        "feedback_reason": latest_feedback["reason"] if latest_feedback else "",
        "reviewed_at": latest_feedback["created_at"] if latest_feedback else None,
        "graph_labels": ["Idea", f"Review{graph_state}"],
        "is_approved": state in ("approved", "published"),
    }


def _unit_summary(unit, evaluation=None, latest_feedback=None) -> IdeaSummaryResponse:
    return IdeaSummaryResponse(
        id=unit.id,
        title=unit.title,
        one_liner=unit.one_liner,
        category=unit.category,
        domain=unit.domain,
        status=unit.status,
        **_review_metadata(unit, latest_feedback),
        target_users=unit.target_users,
        specific_user=unit.specific_user,
        buyer=unit.buyer,
        workflow_context=unit.workflow_context,
        quality_score=unit.quality_score,
        novelty_score=unit.novelty_score,
        usefulness_score=unit.usefulness_score,
        rejection_tags=unit.rejection_tags,
        score=evaluation.overall_score if evaluation else None,
        recommendation=evaluation.recommendation if evaluation else None,
    )


def _critique_to_response(row: dict) -> IdeaCritiqueResponse:
    return IdeaCritiqueResponse(
        id=row["id"],
        buildable_unit_id=row["buildable_unit_id"],
        pipeline_run_id=row.get("pipeline_run_id"),
        stage=row["stage"],
        dimensions=row["dimensions"],
        reasoning=row["reasoning"],
        rejection_tags=row["rejection_tags"],
        created_at=row["created_at"],
    )


def _evaluation_to_response(ev: UtilityEvaluation) -> EvaluationResponse:
    def dim(d) -> DimensionScoreResponse:
        return DimensionScoreResponse(value=d.value, confidence=d.confidence, reasoning=d.reasoning)

    return EvaluationResponse(
        buildable_unit_id=ev.buildable_unit_id,
        pain_severity=dim(ev.pain_severity),
        addressable_scale=dim(ev.addressable_scale),
        build_effort=dim(ev.build_effort),
        composability=dim(ev.composability),
        competitive_density=dim(ev.competitive_density),
        timing_fit=dim(ev.timing_fit),
        compounding_value=dim(ev.compounding_value),
        overall_score=ev.overall_score,
        rank=ev.rank,
        strengths=ev.strengths,
        weaknesses=ev.weaknesses,
        recommendation=ev.recommendation,
        weights_used=ev.weights_used,
    )


def _evaluation_summary_to_response(ev: UtilityEvaluation) -> EvaluationSummaryResponse:
    return EvaluationSummaryResponse(
        overall_score=ev.overall_score,
        rank=ev.rank,
        recommendation=ev.recommendation,
        strengths=ev.strengths,
        weaknesses=ev.weaknesses,
    )


def _weight_profile_or_404(profile_name: str) -> dict[str, float]:
    if profile_name not in WEIGHT_PROFILES:
        raise HTTPException(
            status_code=404,
            detail=f"Evaluation weight profile not found: {profile_name}",
        )
    return get_weights(profile_name)


def _unit_detail(
    unit,
    evaluation=None,
    latest_critique=None,
    latest_feedback=None,
) -> IdeaDetailResponse:
    return IdeaDetailResponse(
        id=unit.id,
        title=unit.title,
        one_liner=unit.one_liner,
        category=unit.category,
        domain=unit.domain,
        ideation_mode=unit.ideation_mode.value if hasattr(unit.ideation_mode, "value") else unit.ideation_mode,
        problem=unit.problem,
        solution=unit.solution,
        target_users=unit.target_users,
        value_proposition=unit.value_proposition,
        specific_user=unit.specific_user,
        buyer=unit.buyer,
        workflow_context=unit.workflow_context,
        current_workaround=unit.current_workaround,
        why_now=unit.why_now,
        validation_plan=unit.validation_plan,
        first_10_customers=unit.first_10_customers,
        domain_risks=unit.domain_risks,
        evidence_rationale=unit.evidence_rationale,
        novelty_score=unit.novelty_score,
        usefulness_score=unit.usefulness_score,
        quality_score=unit.quality_score,
        rejection_tags=unit.rejection_tags,
        inspiring_insights=unit.inspiring_insights,
        evidence_signals=unit.evidence_signals,
        tech_approach=unit.tech_approach,
        suggested_stack=unit.suggested_stack,
        composability_notes=unit.composability_notes,
        status=unit.status,
        **_review_metadata(unit, latest_feedback),
        created_at=unit.created_at.isoformat() if hasattr(unit.created_at, "isoformat") else unit.created_at,
        updated_at=unit.updated_at.isoformat() if hasattr(unit.updated_at, "isoformat") else unit.updated_at,
        latest_critique=_critique_to_response(latest_critique) if latest_critique else None,
        evaluation=_evaluation_to_response(evaluation) if evaluation else None,
    )


def _design_brief_to_response(brief: dict) -> DesignBriefResponse:
    return DesignBriefResponse(**brief)


def _profile_summary_to_response(profile) -> ProfileSummaryResponse:
    return ProfileSummaryResponse(
        name=profile.name,
        domain=profile.domain.name,
        description=profile.domain.description,
        enabled_source_count=sum(1 for source in profile.sources if source.enabled),
        signal_limit=profile.signal_limit,
        min_score=profile.evaluation.min_score,
        weight_profile=profile.evaluation.weight_profile,
        ideation_mode=profile.ideation_mode,
        quality_loop_enabled=profile.quality_loop_enabled,
    )


def _profile_detail_to_response(profile) -> ProfileDetailResponse:
    return ProfileDetailResponse(
        name=profile.name,
        domain=profile.domain,
        sources=profile.sources,
        evaluation=profile.evaluation,
        output_dir=profile.output_dir,
        signal_limit=profile.signal_limit,
        ideation_mode=profile.ideation_mode,
        quality_loop_enabled=profile.quality_loop_enabled,
        draft_count=profile.draft_count,
    )


def _profile_validation_to_response(result) -> ProfileValidationResultResponse:
    return ProfileValidationResultResponse(
        name=result.name,
        path=str(result.path),
        ok=result.ok,
        errors=[
            ProfileValidationIssueResponse(
                severity=issue.severity,
                code=issue.code,
                message=issue.message,
                path=issue.path,
            )
            for issue in result.error_issues
        ],
        warnings=[
            ProfileValidationIssueResponse(
                severity=issue.severity,
                code=issue.code,
                message=issue.message,
                path=issue.path,
            )
            for issue in result.warning_issues
        ],
    )


def _profile_coverage_gaps_to_response(report) -> ProfileCoverageGapsResponse:
    return ProfileCoverageGapsResponse(
        profile_name=report.profile_name,
        domain=report.domain,
        low_coverage_threshold=report.low_coverage_threshold,
        enabled_adapters=report.enabled_adapters,
        terms=[
            ProfileCoverageTermResponse(
                term=term.term,
                term_type=term.term_type,
                total_count=term.total_count,
                adapter_counts=term.adapter_counts,
                enabled_adapters=term.enabled_adapters,
                suggested_source_adapters=term.suggested_source_adapters,
            )
            for term in report.terms
        ],
    )


def _prior_art_response(unit: BuildableUnit, matches: list[dict]) -> PriorArtResponse:
    return PriorArtResponse(
        idea_id=unit.id,
        prior_art_status=unit.prior_art_status,
        matches=matches,
    )


def _lineage_node_id(node_type: str, entity_id: str) -> str:
    return f"{node_type}:{entity_id}"


def _lineage_edge_id(source: str, target: str, edge_type: str) -> str:
    return f"{source}->{target}:{edge_type}"


def _lineage_graph_response(unit: BuildableUnit, store: Store) -> LineageGraphResponse:
    chain = build_evidence_chain_graph(
        unit,
        store,
        insight_converter=lambda insight: _insight_to_response(insight).model_dump(),
        signal_converter=lambda signal: _signal_to_response(signal).model_dump(),
    )
    signal_links = {
        signal["id"]: signal["url"]
        for signal in chain["signals"]
        if signal.get("id") and signal.get("url")
    }
    insight_signal_ids = {
        insight["id"]: list(insight.get("evidence", []))
        for insight in chain["insights"]
    }
    insight_links = {
        insight_id: [
            signal_links[signal_id]
            for signal_id in signal_ids
            if signal_id in signal_links
        ]
        for insight_id, signal_ids in insight_signal_ids.items()
    }
    unit_links: list[str] = []
    for signal_id in unit.evidence_signals:
        if signal_id in signal_links and signal_links[signal_id] not in unit_links:
            unit_links.append(signal_links[signal_id])
    for insight_id in unit.inspiring_insights:
        for link in insight_links.get(insight_id, []):
            if link not in unit_links:
                unit_links.append(link)

    idea_node_id = _lineage_node_id("idea", unit.id)
    unit_node_id = _lineage_node_id("buildable_unit", unit.id)
    nodes = [
        LineageGraphNodeResponse(
            id=idea_node_id,
            entity_id=unit.id,
            type="idea",
            label=unit.title,
            evidence_links=unit_links,
            data={
                "one_liner": unit.one_liner,
                "domain": unit.domain,
                "status": unit.status,
            },
        ),
        LineageGraphNodeResponse(
            id=unit_node_id,
            entity_id=unit.id,
            type="buildable_unit",
            label=unit.one_liner or unit.title,
            evidence_links=unit_links,
            data=chain["idea"],
        ),
    ]
    edges = [
        LineageGraphEdgeResponse(
            id=_lineage_edge_id(idea_node_id, unit_node_id, "materialized_as"),
            source=idea_node_id,
            target=unit_node_id,
            type="materialized_as",
            label="materialized as",
        )
    ]

    for insight in chain["insights"]:
        node_id = _lineage_node_id("insight", insight["id"])
        nodes.append(
            LineageGraphNodeResponse(
                id=node_id,
                entity_id=insight["id"],
                type="insight",
                label=insight["title"],
                evidence_links=insight_links.get(insight["id"], []),
                data=insight,
            )
        )

    for signal in chain["signals"]:
        node_id = _lineage_node_id("signal", signal["id"])
        nodes.append(
            LineageGraphNodeResponse(
                id=node_id,
                entity_id=signal["id"],
                type="signal",
                label=signal["title"],
                evidence_links=[signal["url"]] if signal.get("url") else [],
                data=signal,
            )
        )

    edge_labels = {
        "inspired_by": "inspired by",
        "supported_by": "supported by",
        "direct_evidence": "direct evidence",
    }
    edge_source_prefix = {
        "inspired_by": "buildable_unit",
        "supported_by": "insight",
        "direct_evidence": "buildable_unit",
    }
    edge_target_prefix = {
        "inspired_by": "insight",
        "supported_by": "signal",
        "direct_evidence": "signal",
    }
    for edge in chain["edges"]:
        source = _lineage_node_id(edge_source_prefix[edge["type"]], edge["source"])
        target = _lineage_node_id(edge_target_prefix[edge["type"]], edge["target"])
        edges.append(
            LineageGraphEdgeResponse(
                id=_lineage_edge_id(source, target, edge["type"]),
                source=source,
                target=target,
                type=edge["type"],
                label=edge_labels[edge["type"]],
            )
        )

    return LineageGraphResponse(idea_id=unit.id, nodes=nodes, edges=edges)


def run_prior_art_check_for_idea(store: Store, idea_id: str, *, force: bool = False) -> PriorArtResponse:
    """Check prior art for a single idea and persist the latest result."""
    from max.analysis.prior_art import PriorArtResult, check_prior_art

    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise ValueError(f"Idea not found: {idea_id}")

    matches = store.get_prior_art_matches(idea_id)
    if not force and (unit.prior_art_status != "unchecked" or matches):
        return _prior_art_response(unit, matches)

    if force:
        store.delete_prior_art_matches(idea_id)

    results = check_prior_art([unit], dry_run=False)
    result = results[0] if results else PriorArtResult(
        buildable_unit_id=idea_id,
        matches=[],
        status="clear",
    )

    for match in result.matches:
        store.insert_prior_art_match(idea_id, {
            "source": match.source,
            "title": match.title,
            "url": match.url,
            "description": match.description,
            "relevance_score": match.relevance_score,
            "match_signals": match.match_signals,
            "search_query": match.search_query,
        })

    store.update_prior_art_status(idea_id, result.status)
    refreshed = store.get_buildable_unit(idea_id) or unit
    return _prior_art_response(refreshed, store.get_prior_art_matches(idea_id))


def _load_profile_or_404(profile_name: str):
    from max.profiles.loader import load_profile

    try:
        return load_profile(profile_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")


# ── Profiles ────────────────────────────────────────────────────────


@router.get("/profiles", response_model=list[ProfileSummaryResponse])
def list_pipeline_profiles() -> list[ProfileSummaryResponse]:
    from max.profiles.loader import list_profiles

    return [_profile_summary_to_response(_load_profile_or_404(name)) for name in list_profiles()]


@router.get("/profiles/validate", response_model=ProfileValidationResponse)
def validate_pipeline_profiles(
    profile: str | None = Query(default=None, description="Optional profile name to validate"),
) -> ProfileValidationResponse:
    from max.profiles.loader import validate_profile_files

    try:
        results = validate_profile_files(profile=profile)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile}")

    response_results = [_profile_validation_to_response(result) for result in results]
    return ProfileValidationResponse(
        ok=all(result.ok for result in results),
        profile=profile,
        results=response_results,
    )


@router.get("/profiles/{profile_name}", response_model=ProfileDetailResponse)
def get_pipeline_profile(profile_name: str) -> ProfileDetailResponse:
    return _profile_detail_to_response(_load_profile_or_404(profile_name))


@router.get("/profiles/{profile_name}/validate", response_model=ProfileValidationResponse)
def validate_pipeline_profile(profile_name: str) -> ProfileValidationResponse:
    return validate_pipeline_profiles(profile=profile_name)


@router.get("/profiles/{profile_name}/coverage-gaps", response_model=ProfileCoverageGapsResponse)
def get_profile_coverage_gaps(
    profile_name: str,
    low_coverage_threshold: int = Query(
        default=1,
        ge=1,
        le=100,
        description="Minimum active matching signals required before a term is considered covered",
    ),
    store: Store = Depends(get_store),
) -> ProfileCoverageGapsResponse:
    from max.analysis.profile_coverage import compute_profile_coverage_gaps

    profile = _load_profile_or_404(profile_name)
    report = compute_profile_coverage_gaps(
        profile,
        store,
        low_coverage_threshold=low_coverage_threshold,
    )
    return _profile_coverage_gaps_to_response(report)


@router.get("/profiles/{profile_name}/drift", response_model=ProfileDriftResponse)
@router.get("/profiles/{profile_name}/profile-drift", response_model=ProfileDriftResponse)
def get_profile_drift(
    profile_name: str,
    signal_limit: int = Query(DEFAULT_PROFILE_DRIFT_SIGNAL_LIMIT, ge=1, le=10_000),
    unit_limit: int = Query(DEFAULT_PROFILE_DRIFT_UNIT_LIMIT, ge=1, le=10_000),
    insight_limit: int = Query(DEFAULT_PROFILE_DRIFT_INSIGHT_LIMIT, ge=1, le=10_000),
    store: Store = Depends(get_store),
) -> ProfileDriftResponse:
    profile = _load_profile_or_404(profile_name)
    report = build_profile_drift_report(
        profile,
        store,
        signal_limit=signal_limit,
        unit_limit=unit_limit,
        insight_limit=insight_limit,
    )
    return ProfileDriftResponse.model_validate(report.to_dict())


# ── Evaluation Weights ──────────────────────────────────────────────


@router.get("/evaluation/weights", response_model=list[EvaluationWeightProfileResponse])
def list_evaluation_weight_profiles() -> list[EvaluationWeightProfileResponse]:
    return [
        EvaluationWeightProfileResponse(name=name, weights=get_weights(name))
        for name in WEIGHT_PROFILES
    ]


@router.get("/evaluation/weights/{profile_name}", response_model=EvaluationWeightProfileResponse)
def get_evaluation_weight_profile(
    profile_name: str,
    store: Store = Depends(get_store),
) -> EvaluationWeightProfileResponse:
    weights = _weight_profile_or_404(profile_name)
    adapted_weights, adapted = get_adapted_weights(profile_name, store.get_feedback_outcomes())
    return EvaluationWeightProfileResponse(
        name=profile_name,
        weights=weights,
        adapted=adapted,
        adapted_weights=adapted_weights if adapted else None,
    )


@router.get("/evaluation/calibration", response_model=EvaluationCalibrationResponse)
def get_evaluation_calibration(
    domain: str | None = None,
    min_samples: int = Query(default=1, ge=1, le=1000),
    limit: int = Query(default=50, ge=1, le=500),
    store: Store = Depends(get_store),
) -> EvaluationCalibrationResponse:
    report = build_evaluation_calibration_report(
        store,
        domain=domain,
        min_samples=min_samples,
        limit=limit,
    )
    return EvaluationCalibrationResponse(**asdict(report))


@router.get("/roi-forecast", response_model=RoiForecastResponse)
@router.get("/ideas/roi-forecast", response_model=RoiForecastResponse)
def get_roi_forecast(
    domain: str | None = None,
    status: str | None = None,
    profile: str | None = None,
    weight_profile: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    store: Store = Depends(get_store),
) -> RoiForecastResponse:
    if profile and weight_profile:
        raise HTTPException(
            status_code=400,
            detail="Use either profile or weight_profile, not both.",
        )
    profile_input = None
    if profile:
        profile_input = _load_profile_or_404(profile)
    elif weight_profile:
        _weight_profile_or_404(weight_profile)
        profile_input = weight_profile

    units = store.get_buildable_units(limit=limit, status=status, domain=domain)
    evaluations = {unit.id: store.get_evaluation(unit.id) for unit in units}
    report = generate_roi_forecast(units, evaluations, profile=profile_input)
    return RoiForecastResponse(**asdict(report))


# ── Signals ─────────────────────────────────────────────────────────


@router.get("/signals")
def list_signals(
    cursor: str | None = None,
    limit: int = 20,
    source_type: str | None = None,
    source_adapter: str | None = None,
    signal_role: str | None = None,
    store: Store = Depends(get_store),
) -> PaginatedResponse[SignalResponse]:
    # Clamp limit to max 100
    limit = min(limit, 100)

    try:
        signals, next_cursor = store.get_signals_paginated(
            cursor=cursor,
            limit=limit,
            source_type=source_type,
            source_adapter=source_adapter,
            signal_role=signal_role,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_count = store.count_signals(
        source_type=source_type,
        source_adapter=source_adapter,
        signal_role=signal_role,
    )

    return PaginatedResponse[SignalResponse](
        items=[_signal_to_response(s) for s in signals],
        pagination=PaginationMeta(
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total_count=total_count,
        ),
    )


@router.get("/signals/freshness", response_model=SignalFreshnessResponse)
def get_signal_freshness(
    max_age_days: int = Query(DEFAULT_MAX_AGE_DAYS, ge=1),
    source_adapter: list[str] | None = Query(default=None),
    store: Store = Depends(get_store),
) -> SignalFreshnessResponse:
    report = build_signal_freshness_report(
        store,
        max_age_days=max_age_days,
        source_adapters=source_adapter,
    )
    return SignalFreshnessResponse.model_validate(report.to_dict())


@router.get("/source-reliability", response_model=SourceReliabilityResponse)
def get_source_reliability(
    signal_limit: int = Query(DEFAULT_SIGNAL_LIMIT, ge=1, le=10_000),
    store: Store = Depends(get_store),
) -> SourceReliabilityResponse:
    report = build_source_reliability_report(store, signal_limit=signal_limit)
    return SourceReliabilityResponse.model_validate(report.to_dict())


@router.post("/signals", response_model=SignalCreateResponse, status_code=201)
def create_signal(
    body: SignalCreate,
    response: Response,
    store: Store = Depends(get_store),
) -> SignalCreateResponse:
    metadata = dict(body.metadata)
    if body.signal_role is not None:
        metadata["signal_role"] = body.signal_role

    signal = Signal(
        source_type=body.source_type,
        source_adapter=body.source_adapter,
        title=body.title,
        content=body.content,
        url=body.url,
        author=body.author,
        tags=body.tags,
        credibility=body.credibility,
        metadata=metadata,
    )
    result = store.insert_signal_result(signal)
    response.status_code = 201 if result.created else 200
    return SignalCreateResponse(
        **_signal_to_response(result.signal).model_dump(),
        status=result.status,
    )


@router.post("/signals/import", response_model=SignalImportResponse)
def import_signals(
    body: SignalImportRequest,
    store: Store = Depends(get_store),
) -> SignalImportResponse:
    results: list[SignalImportRowResult] = []
    inserted_count = 0
    duplicate_count = 0
    error_count = 0

    for index, row in enumerate(body.rows):
        try:
            signal = _signal_from_import_row(row, body)
            result = store.insert_signal_result(signal)
        except (TypeError, ValueError, ValidationError) as e:
            error_count += 1
            results.append(SignalImportRowResult(index=index, error=str(e)))
            continue

        if result.created:
            inserted_count += 1
            results.append(SignalImportRowResult(index=index, signal_id=result.signal.id))
        else:
            duplicate_count += 1
            results.append(SignalImportRowResult(index=index, duplicate_id=result.signal.id))

    return SignalImportResponse(
        inserted_count=inserted_count,
        duplicate_count=duplicate_count,
        error_count=error_count,
        results=results,
    )


@router.post("/signals/{signal_id}/archive", response_model=SignalResponse)
def archive_signal(signal_id: str, store: Store = Depends(get_store)) -> SignalResponse:
    if not store.archive_signal(signal_id):
        raise HTTPException(status_code=404, detail=f"Signal not found: {signal_id}")

    signal = store.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal not found: {signal_id}")
    return _signal_to_response(signal)


@router.post("/signals/{signal_id}/restore", response_model=SignalResponse)
def restore_signal(signal_id: str, store: Store = Depends(get_store)) -> SignalResponse:
    if not store.restore_signal(signal_id):
        raise HTTPException(status_code=404, detail=f"Signal not found: {signal_id}")

    signal = store.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal not found: {signal_id}")
    return _signal_to_response(signal)


# ── Insights ────────────────────────────────────────────────────────


@router.get("/insights")
def list_insights(
    cursor: str | None = None,
    limit: int = 20,
    domain: str | None = None,
    category: str | None = None,
    store: Store = Depends(get_store),
) -> PaginatedResponse[InsightResponse]:
    # Clamp limit to max 100
    limit = min(limit, 100)

    try:
        insights, next_cursor = store.get_insights_paginated(
            cursor=cursor, limit=limit, domain=domain, category=category
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_count = store.count_insights(domain=domain, category=category)

    return PaginatedResponse[InsightResponse](
        items=[_insight_to_response(i) for i in insights],
        pagination=PaginationMeta(
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total_count=total_count,
        ),
    )


@router.post("/insights", response_model=InsightResponse, status_code=201)
def create_insight(body: InsightCreate, store: Store = Depends(get_store)) -> InsightResponse:
    insight = Insight(
        category=body.category,
        title=body.title,
        summary=body.summary,
        evidence=body.evidence,
        confidence=body.confidence,
        domains=body.domains,
        implications=body.implications,
        time_horizon=body.time_horizon,
    )
    insight = store.insert_insight(insight)
    return _insight_to_response(insight)


@router.get("/insights/{insight_id}", response_model=InsightDetailResponse)
def get_insight(insight_id: str, store: Store = Depends(get_store)) -> InsightDetailResponse:
    insight = store.get_insight(insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail=f"Insight not found: {insight_id}")
    return _insight_detail_to_response(insight, store)


@router.get("/insights/{insight_id}/contradictions", response_model=ContradictionReportResponse)
def get_insight_contradictions(
    insight_id: str,
    store: Store = Depends(get_store),
) -> ContradictionReportResponse:
    insight = store.get_insight(insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail=f"Insight not found: {insight_id}")
    return ContradictionReportResponse.model_validate(
        build_insight_contradiction_report(insight, store)
    )


# ── Ideas ───────────────────────────────────────────────────────────


@router.get("/review-queue", response_model=list[ReviewQueueItemResponse])
def get_review_queue(
    domain: str | None = None,
    min_score: float | None = Query(default=None, ge=0.0, le=100.0),
    limit: int = Query(default=50, ge=1, le=100),
    store: Store = Depends(get_store),
) -> list[ReviewQueueItemResponse]:
    rows = store.get_review_queue(domain=domain, min_score=min_score, limit=limit)
    items: list[ReviewQueueItemResponse] = []
    for row in rows:
        payload = _unit_summary(row["unit"], row["evaluation"]).model_dump()
        payload["evaluation"] = _evaluation_summary_to_response(row["evaluation"])
        payload["latest_critique"] = (
            _critique_to_response(row["latest_critique"])
            if row["latest_critique"]
            else None
        )
        items.append(
            ReviewQueueItemResponse(
                **payload,
            )
        )
    return items


@router.get("/review-thresholds", response_model=ReviewThresholdsResponse)
def get_review_thresholds(
    domain: str | None = None,
    min_samples: int = Query(default=DEFAULT_MIN_SAMPLES, ge=1, le=1000),
    store: Store = Depends(get_store),
) -> ReviewThresholdsResponse:
    recommendations = recommend_review_thresholds(
        store,
        domain=domain,
        min_samples=min_samples,
    )
    return ReviewThresholdsResponse(
        min_samples=min_samples,
        default_approve_threshold=DEFAULT_APPROVE_THRESHOLD,
        default_reject_threshold=DEFAULT_REJECT_THRESHOLD,
        recommendations=[
            ReviewThresholdRecommendationResponse(**item.__dict__)
            for item in recommendations
        ],
    )


@router.get("/exports/ideas", response_class=Response)
def export_ideas(
    fmt: Literal["jsonl", "csv"] = "jsonl",
    status: str | None = None,
    domain: str | None = None,
    min_score: float | None = Query(default=None, ge=0.0, le=100.0),
    include_archived: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    store: Store = Depends(get_store),
) -> Response:
    """Export filtered idea summaries as JSON Lines or CSV."""
    units = store.get_buildable_units(limit=limit, status=status, domain=domain)
    if not include_archived and status != "archived":
        units = [unit for unit in units if unit.status != "archived"]

    records = idea_export_records(
        units,
        get_evaluation=store.get_evaluation,
        get_latest_feedback=store.get_latest_feedback,
        min_score=min_score,
    )
    media_type = "text/csv" if fmt == "csv" else "text/plain"
    filename = f"ideas-export.{fmt}"
    return Response(
        content=render_idea_export(records, fmt=fmt),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ideas")
def list_ideas(
    cursor: str | None = None,
    limit: int = 20,
    status: str | None = None,
    category: str | None = None,
    domain: str | None = None,
    min_score: float | None = None,
    store: Store = Depends(get_store),
) -> PaginatedResponse[IdeaSummaryResponse]:
    # Clamp limit to max 100
    limit = min(limit, 100)

    # Get paginated units from DB (with status/domain filters)
    try:
        units, next_cursor = store.get_buildable_units_paginated(
            cursor=cursor, limit=limit, status=status, domain=domain
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Apply additional in-memory filters (category, min_score)
    results: list[IdeaSummaryResponse] = []
    for unit in units:
        if category and (unit.category) != category:
            continue
        evaluation = store.get_evaluation(unit.id)
        if min_score is not None and (evaluation is None or evaluation.overall_score < min_score):
            continue
        summary = _unit_summary(unit, evaluation, store.get_latest_feedback(unit.id))
        critiques = store.get_idea_critiques(unit.id)
        if critiques:
            summary.latest_critique = _critique_to_response(critiques[0])
        results.append(summary)

    total_count = store.count_buildable_units(status=status, domain=domain)

    return PaginatedResponse[IdeaSummaryResponse](
        items=results,
        pagination=PaginationMeta(
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total_count=total_count,
        ),
    )


@router.get("/ideas/status-summary", response_model=IdeaStatusSummaryResponse)
def get_idea_status_summary(store: Store = Depends(get_store)) -> IdeaStatusSummaryResponse:
    return IdeaStatusSummaryResponse(**store.get_idea_status_summary())


@router.get("/ideas/score-distribution", response_model=IdeaScoreDistributionResponse)
def get_idea_score_distribution(
    domain: str | None = None,
    status: str | None = None,
    bucket_size: int = Query(default=10, ge=1, le=100),
    store: Store = Depends(get_store),
) -> IdeaScoreDistributionResponse:
    return IdeaScoreDistributionResponse(
        **store.get_idea_score_distribution(
            domain=domain,
            status=status,
            bucket_size=bucket_size,
        )
    )


@router.get("/ideas/portfolio-overlap", response_model=list[PortfolioOverlapClusterResponse])
def get_portfolio_overlap(
    limit: int = Query(default=20, ge=1, le=100),
    min_overlap_score: float = Query(default=0.35, ge=0.0, le=1.0),
    include_archived: bool = False,
    store: Store = Depends(get_store),
) -> list[PortfolioOverlapClusterResponse]:
    clusters = find_portfolio_overlap_clusters(
        store,
        limit=limit,
        min_overlap_score=min_overlap_score,
        include_archived=include_archived,
    )
    return [PortfolioOverlapClusterResponse(**asdict(cluster)) for cluster in clusters]


def _opportunity_heatmap_response(
    *,
    domain: str | None,
    min_signals: int,
    limit: int,
    store: Store,
) -> list[OpportunityHeatmapBucketResponse]:
    try:
        buckets = build_opportunity_heatmap(
            store,
            domain=domain,
            min_signals=min_signals,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [OpportunityHeatmapBucketResponse(**bucket) for bucket in buckets]


@router.get("/opportunity-heatmap", response_model=list[OpportunityHeatmapBucketResponse])
def get_opportunity_heatmap(
    domain: str | None = None,
    min_signals: int = Query(default=1, ge=0),
    limit: int = Query(default=1000, ge=1, le=10000),
    store: Store = Depends(get_store),
) -> list[OpportunityHeatmapBucketResponse]:
    return _opportunity_heatmap_response(
        domain=domain,
        min_signals=min_signals,
        limit=limit,
        store=store,
    )


@router.get("/ideas/opportunity-heatmap", response_model=list[OpportunityHeatmapBucketResponse])
def get_ideas_opportunity_heatmap(
    domain: str | None = None,
    min_signals: int = Query(default=1, ge=0),
    limit: int = Query(default=1000, ge=1, le=10000),
    store: Store = Depends(get_store),
) -> list[OpportunityHeatmapBucketResponse]:
    return _opportunity_heatmap_response(
        domain=domain,
        min_signals=min_signals,
        limit=limit,
        store=store,
    )


def _idea_similarity_response(result) -> IdeaSimilarityResultResponse:
    return IdeaSimilarityResultResponse(
        idea_id=result.idea_id,
        title=result.title,
        problem_summary=result.problem_summary,
        similarity_score=result.similarity_score,
        overlapping_evidence_ids=result.overlapping_evidence_ids,
        overlapping_insight_ids=result.overlapping_insight_ids,
    )


def _find_similar_ideas_response(
    store: Store,
    *,
    idea_id: str | None,
    query: str | None,
    threshold: float,
    limit: int,
) -> list[IdeaSimilarityResultResponse]:
    try:
        results = find_similar_ideas(
            store,
            idea_id=idea_id,
            query=query,
            threshold=threshold,
            limit=limit,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [_idea_similarity_response(result) for result in results]


@router.get("/ideas/similar", response_model=list[IdeaSimilarityResultResponse])
def get_similar_ideas(
    idea_id: str | None = None,
    query: str | None = None,
    threshold: float = Query(default=0.1, ge=0.0, le=1.0),
    limit: int = Query(default=5, ge=1, le=100),
    store: Store = Depends(get_store),
) -> list[IdeaSimilarityResultResponse]:
    return _find_similar_ideas_response(
        store,
        idea_id=idea_id,
        query=query,
        threshold=threshold,
        limit=limit,
    )


@router.post("/ideas/similar", response_model=list[IdeaSimilarityResultResponse])
def post_similar_ideas(
    body: IdeaSimilarityRequest,
    store: Store = Depends(get_store),
) -> list[IdeaSimilarityResultResponse]:
    return _find_similar_ideas_response(
        store,
        idea_id=body.idea_id,
        query=body.query,
        threshold=body.threshold,
        limit=body.limit,
    )


def _evaluate_existing_idea(store: Store, idea_id: str) -> UtilityEvaluation:
    """Evaluate an existing idea and persist the result."""
    from max.evaluation.engine import evaluate
    from max.pipeline.runner import _resolve_evidence_chain

    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise ValueError(f"Idea not found: {idea_id}")

    evidence = _resolve_evidence_chain(unit, store)
    evaluation = evaluate(unit, evidence=evidence)
    store.insert_evaluation(evaluation)
    store.update_buildable_unit_status(idea_id, "evaluated")
    return evaluation


@router.post(
    "/ideas/evaluate-batch",
    response_model=IdeaEvaluateBatchResponse,
)
def evaluate_ideas_batch(
    body: IdeaEvaluateBatchRequest,
    store: Store = Depends(get_store),
) -> IdeaEvaluateBatchResponse:
    results: list[IdeaEvaluateBatchItemResponse] = []
    for idea_id in body.idea_ids:
        try:
            existing = store.get_evaluation(idea_id)
            if body.skip_existing and existing:
                results.append(
                    IdeaEvaluateBatchItemResponse(
                        idea_id=idea_id,
                        status="skipped",
                        success=True,
                        evaluation=_evaluation_summary_to_response(existing),
                    )
                )
                continue

            evaluation = _evaluate_existing_idea(store, idea_id)
            results.append(
                IdeaEvaluateBatchItemResponse(
                    idea_id=idea_id,
                    status="evaluated",
                    success=True,
                    evaluation=_evaluation_summary_to_response(evaluation),
                )
            )
        except Exception as exc:
            results.append(
                IdeaEvaluateBatchItemResponse(
                    idea_id=idea_id,
                    status="error",
                    success=False,
                    error=str(exc),
                )
            )

    return IdeaEvaluateBatchResponse(results=results)


@router.get("/ideas/{idea_id}", response_model=IdeaDetailResponse)
def get_idea(idea_id: str, store: Store = Depends(get_store)) -> IdeaDetailResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    critiques = store.get_idea_critiques(idea_id)
    return _unit_detail(
        unit,
        evaluation,
        latest_critique=critiques[0] if critiques else None,
        latest_feedback=store.get_latest_feedback(idea_id),
    )


@router.get(
    "/ideas/{idea_id}/evaluation-explanation",
    response_model=EvaluationExplanationResponse,
)
def get_idea_evaluation_explanation(
    idea_id: str,
    store: Store = Depends(get_store),
) -> EvaluationExplanationResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    insights = [
        insight
        for insight_id in unit.inspiring_insights
        if (insight := store.get_insight(insight_id))
    ]
    signal_ids = list(dict.fromkeys(
        [
            *unit.evidence_signals,
            *(signal_id for insight in insights for signal_id in insight.evidence),
        ]
    ))
    signals = [
        signal
        for signal_id in signal_ids
        if (signal := store.get_signal(signal_id))
    ]
    return EvaluationExplanationResponse.model_validate(
        explain_evaluation(
            unit,
            evaluation,
            insights=insights,
            signals=signals,
        )
    )


@router.get("/ideas/{idea_id}/prior-art", response_model=PriorArtResponse)
def get_idea_prior_art(idea_id: str, store: Store = Depends(get_store)) -> PriorArtResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return _prior_art_response(unit, store.get_prior_art_matches(idea_id))


@router.get("/ideas/{idea_id}/publications", response_model=list[PublicationAttemptResponse])
def get_idea_publications(
    idea_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    store: Store = Depends(get_store),
) -> list[PublicationAttemptResponse]:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return [
        PublicationAttemptResponse(**attempt)
        for attempt in store.list_publication_attempts(idea_id, limit=limit)
    ]


@router.post("/ideas/{idea_id}/prior-art/check", response_model=PriorArtResponse)
def check_idea_prior_art(
    idea_id: str,
    force: bool = Query(False),
    body: PriorArtCheckRequest | None = Body(default=None),
    store: Store = Depends(get_store),
) -> PriorArtResponse:
    try:
        return run_prior_art_check_for_idea(
            store,
            idea_id,
            force=force or (body.force if body else False),
        )
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")


@router.get("/ideas/{idea_id}/spec-preview")
def get_idea_spec_preview(idea_id: str, store: Store = Depends(get_store)) -> dict:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return generate_spec_preview(unit, store.get_evaluation(idea_id))


@router.get("/ideas/{idea_id}/spec-readiness")
def get_idea_spec_readiness(idea_id: str, store: Store = Depends(get_store)) -> dict:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return evaluate_spec_readiness(unit, store.get_evaluation(idea_id))


@router.get("/ideas/{idea_id}/implementation-plan")
def get_idea_implementation_plan(idea_id: str, store: Store = Depends(get_store)) -> dict:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    spec_preview = generate_spec_preview(unit, evaluation)
    return generate_implementation_plan(unit, evaluation, spec_preview)


@router.get("/ideas/{idea_id}/launch-checklist", response_model=LaunchChecklistResponse)
def get_idea_launch_checklist(idea_id: str, store: Store = Depends(get_store)) -> LaunchChecklistResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    tact_spec = generate_spec_preview(unit, evaluation)
    return LaunchChecklistResponse.model_validate(
        generate_launch_checklist(unit, evaluation, tact_spec)
    )


@router.get("/ideas/{idea_id}/critiques", response_model=list[IdeaCritiqueResponse])
def get_idea_critiques(
    idea_id: str,
    store: Store = Depends(get_store),
) -> list[IdeaCritiqueResponse]:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return [_critique_to_response(row) for row in store.get_idea_critiques(idea_id)]


@router.get("/idea-memory", response_model=list[IdeaMemoryResponse])
def list_idea_memory(
    domain: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
    store: Store = Depends(get_store),
) -> list[IdeaMemoryResponse]:
    limit = min(limit, 100)
    rows = store.get_idea_memory(domain=domain, outcome=outcome, limit=limit)
    return [IdeaMemoryResponse(**row) for row in rows]


@router.get("/ideas/{idea_id}/evidence-pack")
def get_idea_evidence_pack(idea_id: str, store: Store = Depends(get_store)) -> dict:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    critiques = store.get_idea_critiques(idea_id)
    if critiques and critiques[0].get("evidence_pack"):
        return critiques[0]["evidence_pack"]

    from max.ideation.evidence import build_evidence_pack

    insights = [
        insight
        for insight_id in unit.inspiring_insights
        if (insight := store.get_insight(insight_id))
    ]
    return json.loads(build_evidence_pack(insights=insights, store=store).to_json())


@router.get("/ideas/{idea_id}/evidence-chain", response_model=EvidenceChainResponse)
def get_idea_evidence_chain(idea_id: str, store: Store = Depends(get_store)) -> EvidenceChainResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    graph = build_evidence_chain_graph(
        unit,
        store,
        insight_converter=lambda insight: _insight_to_response(insight).model_dump(),
        signal_converter=lambda signal: _signal_to_response(signal).model_dump(),
    )
    return EvidenceChainResponse(**graph)


@router.get("/ideas/{idea_id}/evidence-density", response_model=EvidenceDensityResponse)
def get_idea_evidence_density(
    idea_id: str,
    store: Store = Depends(get_store),
) -> EvidenceDensityResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return EvidenceDensityResponse.model_validate(
        build_evidence_density_report(unit, store)
    )


@router.get("/ideas/{idea_id}/contradictions", response_model=ContradictionReportResponse)
def get_idea_contradictions(
    idea_id: str,
    store: Store = Depends(get_store),
) -> ContradictionReportResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return ContradictionReportResponse.model_validate(
        build_idea_contradiction_report(unit, store)
    )


@router.get("/ideas/{idea_id}/lineage", response_model=LineageGraphResponse)
@router.get("/ideas/{idea_id}/lineage-graph", response_model=LineageGraphResponse)
def get_idea_lineage_graph(idea_id: str, store: Store = Depends(get_store)) -> LineageGraphResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return _lineage_graph_response(unit, store)


@router.get("/ideas/{idea_id}/domain-quality", response_model=list[DomainQualityScoreResponse])
def get_idea_domain_quality(
    idea_id: str,
    store: Store = Depends(get_store),
) -> list[DomainQualityScoreResponse]:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return [DomainQualityScoreResponse(**row) for row in store.get_domain_quality_scores(idea_id)]


def _evaluate_idea_background(idea_id: str) -> None:
    """Run evaluation in background (blocking LLM call)."""
    from max.evaluation.engine import evaluate

    store = Store(wal_mode=True)
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            return
        evaluation = evaluate(unit)
        store.insert_evaluation(evaluation)
        store.update_buildable_unit_status(idea_id, "evaluated")
    finally:
        store.close()


@router.post("/ideas", response_model=IdeaDetailResponse, status_code=201)
def create_idea(
    body: IdeaCreate,
    background_tasks: BackgroundTasks,
    store: Store = Depends(get_store),
) -> IdeaDetailResponse:
    unit = BuildableUnit(
        title=body.title,
        one_liner=body.one_liner,
        category=body.category,
        problem=body.problem,
        solution=body.solution,
        target_users=body.target_users,
        value_proposition=body.value_proposition,
        specific_user=body.specific_user,
        buyer=body.buyer,
        workflow_context=body.workflow_context,
        current_workaround=body.current_workaround,
        why_now=body.why_now,
        validation_plan=body.validation_plan,
        first_10_customers=body.first_10_customers,
        domain_risks=body.domain_risks,
        evidence_rationale=body.evidence_rationale,
        tech_approach=body.tech_approach,
        suggested_stack=body.suggested_stack,
        composability_notes=body.composability_notes,
    )
    unit = store.insert_buildable_unit(unit)

    background_tasks.add_task(_evaluate_idea_background, unit.id)

    return _unit_detail(unit)


# ── Feedback ────────────────────────────────────────────────────────


def _feedback_webhook_secret() -> str:
    return config.MAX_FEEDBACK_WEBHOOK_SECRET.strip()


def _verify_feedback_webhook_signature(payload: bytes, signature: str | None) -> None:
    secret = _feedback_webhook_secret()
    if not secret:
        return
    if not signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    provided = signature.removeprefix("sha256=").strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _cached_request_body(request: Request, body: FeedbackWebhookRequest) -> bytes:
    payload = getattr(request, "_body", None)
    if isinstance(payload, bytes):
        return payload
    return json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _feedback_reason_with_external_metadata(body: FeedbackWebhookRequest) -> str:
    external_metadata: dict[str, Any] = {
        "external_run_id": body.external_run_id,
        "external_url": body.external_url,
    }
    if body.metadata:
        external_metadata["metadata"] = body.metadata
    encoded = json.dumps(external_metadata, sort_keys=True, separators=(",", ":"))
    if body.reason:
        return f"{body.reason}\n\nexternal_feedback={encoded}"
    return f"external_feedback={encoded}"


def _record_feedback(
    *,
    idea_id: str,
    outcome: Literal["approved", "rejected", "published", "abandoned"],
    reason: str,
    approval_score: int | None,
    store: Store,
) -> None:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    try:
        validate_buildable_unit_status_transition(unit.status, outcome)
    except InvalidBuildableUnitStatusTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    store.insert_feedback(
        idea_id,
        outcome,
        reason,
        approval_score=approval_score,
    )
    store.update_buildable_unit_status(idea_id, outcome)


@router.post("/ideas/{idea_id}/feedback", status_code=201)
def create_feedback(
    idea_id: str,
    body: FeedbackCreate,
    store: Store = Depends(get_store),
) -> dict:
    _record_feedback(
        idea_id=idea_id,
        outcome=body.outcome,
        reason=body.reason,
        approval_score=body.approval_score,
        store=store,
    )
    return {"status": "ok", "idea_id": idea_id, "outcome": body.outcome}


@router.post("/webhooks/feedback", response_model=FeedbackWebhookResponse, status_code=201)
def create_feedback_webhook(
    request: Request,
    body: FeedbackWebhookRequest,
    store: Store = Depends(get_store),
) -> FeedbackWebhookResponse:
    payload = _cached_request_body(request, body)
    _verify_feedback_webhook_signature(
        payload,
        request.headers.get("X-Max-Signature"),
    )
    reason = _feedback_reason_with_external_metadata(body)
    _record_feedback(
        idea_id=body.idea_id,
        outcome=body.outcome,
        reason=reason,
        approval_score=body.approval_score,
        store=store,
    )
    return FeedbackWebhookResponse(
        status="ok",
        idea_id=body.idea_id,
        outcome=body.outcome,
        external_run_id=body.external_run_id,
    )


@router.post("/ideas/feedback-batch", response_model=FeedbackBatchResponse, status_code=200)
def create_feedback_batch(
    body: FeedbackBatchRequest,
    store: Store = Depends(get_store),
) -> FeedbackBatchResponse:
    results: list[FeedbackBatchItemResponse] = []

    for item in body.items:
        unit = store.get_buildable_unit(item.idea_id)
        if not unit:
            results.append(
                FeedbackBatchItemResponse(
                    idea_id=item.idea_id,
                    outcome=item.outcome,
                    status="not_found",
                    success=False,
                    error=f"Idea not found: {item.idea_id}",
                )
            )
            continue

        try:
            validate_buildable_unit_status_transition(unit.status, item.outcome)
        except InvalidBuildableUnitStatusTransition as exc:
            results.append(
                FeedbackBatchItemResponse(
                    idea_id=item.idea_id,
                    outcome=item.outcome,
                    status="invalid_transition",
                    success=False,
                    error=str(exc),
                )
            )
            continue

        store.insert_feedback(
            item.idea_id,
            item.outcome,
            item.reason,
            approval_score=item.approval_score,
        )
        store.update_buildable_unit_status(item.idea_id, item.outcome)
        results.append(
            FeedbackBatchItemResponse(
                idea_id=item.idea_id,
                outcome=item.outcome,
                status="updated",
                success=True,
            )
        )

    return FeedbackBatchResponse(results=results)


# ── Feedback Trends ────────────────────────────────────────────────


@router.get("/trends/feedback", response_model=FeedbackTrendResponse)
def get_feedback_trends(
    days: int = Query(default=30, ge=1, le=3650),
    bucket: Literal["day", "week", "month"] = Query(default="day"),
    store: Store = Depends(get_store),
) -> FeedbackTrendResponse:
    from max.analysis.retrospective import detect_feedback_trends

    trends = detect_feedback_trends(store, days=days, bucket=bucket)
    return FeedbackTrendResponse(
        days=trends.days,
        bucket=trends.bucket,
        window_count=trends.window_count,
        total_count=trends.total_count,
        approved_count=trends.approved_count,
        rejected_count=trends.rejected_count,
        approval_rate=trends.approval_rate,
        avg_score=trends.avg_score,
        windows=[
            FeedbackTrendWindowResponse(
                window_start=window.window_start.isoformat(),
                window_end=window.window_end.isoformat(),
                total_count=window.total_count,
                approved_count=window.approved_count,
                rejected_count=window.rejected_count,
                approval_rate=window.approval_rate,
                avg_score=window.avg_score,
                domains=[
                    FeedbackTrendDomainResponse(
                        domain=domain.domain,
                        total_count=domain.total_count,
                        approved_count=domain.approved_count,
                        rejected_count=domain.rejected_count,
                        approval_rate=domain.approval_rate,
                        avg_score=domain.avg_score,
                    )
                    for domain in window.domains
                ],
            )
            for window in trends.windows
        ],
    )


@router.get("/trends/pipeline", response_model=PipelineTrendResponse)
def get_pipeline_trends(
    days: int = Query(default=30, ge=1, le=3650),
    bucket: Literal["day", "week", "month"] = Query(default="day"),
    store: Store = Depends(get_store),
) -> PipelineTrendResponse:
    from max.analysis.retrospective import detect_pipeline_trends

    trends = detect_pipeline_trends(store, days=days, bucket=bucket)
    return PipelineTrendResponse(
        days=trends.days,
        bucket=trends.bucket,
        window_count=trends.window_count,
        run_count=trends.run_count,
        completed_count=trends.completed_count,
        failed_count=trends.failed_count,
        signals_fetched=trends.signals_fetched,
        signals_new=trends.signals_new,
        insights_generated=trends.insights_generated,
        ideas_generated=trends.ideas_generated,
        ideas_evaluated=trends.ideas_evaluated,
        estimated_cost_usd=trends.estimated_cost_usd,
        avg_idea_score=trends.avg_idea_score,
        windows=[
            PipelineTrendWindowResponse(
                window_start=window.window_start.isoformat(),
                window_end=window.window_end.isoformat(),
                run_count=window.run_count,
                completed_count=window.completed_count,
                failed_count=window.failed_count,
                signals_fetched=window.signals_fetched,
                signals_new=window.signals_new,
                insights_generated=window.insights_generated,
                ideas_generated=window.ideas_generated,
                ideas_evaluated=window.ideas_evaluated,
                estimated_cost_usd=window.estimated_cost_usd,
                avg_idea_score=window.avg_idea_score,
            )
            for window in trends.windows
        ],
    )


@router.get("/trends/insights", response_model=InsightTrendResponse)
def get_insight_trends(
    domain: str | None = None,
    category: str | None = None,
    days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=20, ge=1, le=100),
    store: Store = Depends(get_store),
) -> InsightTrendResponse:
    from max.analysis.insight_trends import analyze_insight_trends

    summary = analyze_insight_trends(
        store,
        domain=domain,
        category=category,
        days=days,
        limit=limit,
    )
    return InsightTrendResponse(
        days=summary.days,
        domain=summary.domain,
        category=summary.category,
        total_insights=summary.total_insights,
        trend_count=len(summary.trends),
        trends=[
            InsightTrendItemResponse(
                category=trend.category,
                domain=trend.domain,
                time_horizon=trend.time_horizon,
                count=trend.count,
                average_confidence=trend.average_confidence,
                newest_insight_at=trend.newest_insight_at.isoformat(),
                top_evidence_signal_ids=trend.top_evidence_signal_ids,
            )
            for trend in summary.trends
        ],
    )


# ── Design Briefs ───────────────────────────────────────────────────


@router.get("/design-briefs", response_model=list[DesignBriefResponse])
def list_design_briefs(
    domain: str | None = None,
    status: str | None = None,
    limit: int = 20,
    store: Store = Depends(get_store),
) -> list[DesignBriefResponse]:
    limit = min(limit, 100)
    briefs = store.get_design_briefs(domain=domain, status=status, limit=limit)
    return [_design_brief_to_response(brief) for brief in briefs]


@router.post("/design-briefs/synthesize", response_model=list[DesignBriefResponse], status_code=201)
def synthesize_design_briefs(
    domain: str | None = None,
    top: int = Query(default=8, ge=1, le=100),
    store: Store = Depends(get_store),
) -> list[DesignBriefResponse]:
    from max.analysis.portfolio_synthesis import build_candidates, synthesize_project_briefs

    units = store.get_buildable_units(limit=500, domain=domain)
    evaluations = {unit.id: store.get_evaluation(unit.id) for unit in units}
    feedback = {unit.id: store.get_latest_feedback(unit.id) for unit in units}
    candidates = build_candidates(units, evaluations=evaluations, feedback=feedback)
    briefs = synthesize_project_briefs(candidates, top=top)

    persisted: list[DesignBriefResponse] = []
    for brief in briefs:
        brief_id = store.insert_design_brief(brief)
        stored = store.get_design_brief(brief_id)
        if stored:
            persisted.append(_design_brief_to_response(stored))
    return persisted


@router.get("/design-briefs/{brief_id}", response_model=DesignBriefResponse)
def get_design_brief(brief_id: str, store: Store = Depends(get_store)) -> DesignBriefResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return _design_brief_to_response(brief)


@router.patch("/design-briefs/{brief_id}/status", response_model=DesignBriefResponse)
def update_design_brief_status(
    brief_id: str,
    update: DesignBriefStatusUpdate,
    store: Store = Depends(get_store),
) -> DesignBriefResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    store.update_design_brief_status(brief_id, update.status)
    updated = store.get_design_brief(brief_id)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return _design_brief_to_response(updated)


@router.get("/design-briefs/{brief_id}/blueprint", response_model=BlueprintSourceBriefResponse)
def get_design_brief_blueprint(
    brief_id: str,
    store: Store = Depends(get_store),
) -> BlueprintSourceBriefResponse:
    from max.analysis.blueprint_export import build_blueprint_source_brief

    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return BlueprintSourceBriefResponse(**build_blueprint_source_brief(store, brief))


@router.get("/design-briefs/{brief_id}/markdown", response_class=Response)
def get_design_brief_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    from max.analysis.portfolio_synthesis import render_design_brief_markdown

    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return Response(
        content=render_design_brief_markdown(brief),
        media_type="text/markdown",
    )


@router.get("/design-briefs/{brief_id}/validation-plan", response_model=DesignBriefValidationPlanResponse)
def get_design_brief_validation_plan(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefValidationPlanResponse:
    from max.analysis.design_validation import build_validation_plan

    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefValidationPlanResponse(**build_validation_plan(store, brief))


# ── Domain Quality ──────────────────────────────────────────────────


@router.get("/domains/{domain}/quality-memory", response_model=list[DomainQualityMemoryResponse])
def get_domain_quality_memory(
    domain: str,
    outcome: str | None = None,
    limit: int = 50,
    store: Store = Depends(get_store),
) -> list[DomainQualityMemoryResponse]:
    limit = min(limit, 100)
    rows = store.get_domain_quality_memory(domain=domain, outcome=outcome, limit=limit)
    return [DomainQualityMemoryResponse(**row) for row in rows]


# ── Pipeline ────────────────────────────────────────────────────────


@router.post(
    "/pipeline/run",
    response_model=PipelineResultResponse | PipelineAggregateResultResponse,
    dependencies=[Depends(rate_limit(config.MAX_RATE_LIMIT_EXPENSIVE_RPM))],
)
async def run_pipeline_endpoint(
    body: PipelineRunRequest,
) -> PipelineResultResponse | PipelineAggregateResultResponse:
    from max.focus import focused_profile_names
    from max.pipeline.runner import run_pipeline
    from max.profiles.loader import load_profile

    output_dir = Path(body.output_dir) if body.output_dir else None
    if body.profile == "all":
        profile_names, skipped_profiles, focus_domains = focused_profile_names(
            include_all=body.include_all
        )
        if not profile_names and focus_domains is None:
            raise HTTPException(status_code=404, detail="No profiles found")
        if not profile_names:
            raise HTTPException(
                status_code=400,
                detail="No profiles match focus. Clear focus or set include_all=true.",
            )

        profile_results: list[PipelineResultResponse] = []
        for profile_name in profile_names:
            profile = load_profile(profile_name)
            profile = _apply_pipeline_request_overrides(profile, body)
            result = await asyncio.to_thread(
                run_pipeline,
                profile=profile,
                output_dir=output_dir,
                stages=body.stages,
            )
            profile_results.append(
                _pipeline_result_response(
                    result,
                    profile_name=profile.name,
                    domain=profile.domain.name,
                )
            )

        return PipelineAggregateResultResponse(
            include_all=body.include_all,
            focus_domains=focus_domains,
            skipped_profiles=skipped_profiles,
            profiles_run=len(profile_results),
            totals=_aggregate_pipeline_results(profile_results),
            profiles=profile_results,
        )

    profile = load_profile(body.profile) if body.profile else None
    if profile is not None:
        profile = _apply_pipeline_request_overrides(profile, body)
    result = await asyncio.to_thread(
        run_pipeline,
        profile=profile,
        output_dir=output_dir,
        signal_limit=body.signal_limit,
        min_score=body.min_score,
        weight_profile=body.weight_profile,
        ideation_mode=body.ideation_mode,
        quality_loop_enabled=body.quality_loop_enabled,
        draft_count=body.draft_count,
        stages=body.stages,
    )
    return _pipeline_result_response(
        result,
        profile_name=profile.name if profile else None,
        domain=profile.domain.name if profile else None,
    )


def _pipeline_result_response(
    result,
    *,
    profile_name: str | None = None,
    domain: str | None = None,
) -> PipelineResultResponse:
    return PipelineResultResponse(
        profile_name=profile_name or result.profile_name or None,
        domain=domain,
        signals_fetched=result.signals_fetched,
        signals_new=result.signals_new,
        insights_generated=result.insights_generated,
        ideas_generated=result.ideas_generated,
        ideas_evaluated=result.ideas_evaluated,
        draft_ideas_generated=result.draft_ideas_generated,
        ideas_revised=result.ideas_revised,
        ideas_rejected_by_quality_gate=result.ideas_rejected_by_quality_gate,
        ideas_rejected_by_domain_quality=result.ideas_rejected_by_domain_quality,
        avg_domain_quality_score=result.avg_domain_quality_score,
        avg_novelty_score=result.avg_novelty_score,
        avg_usefulness_score=result.avg_usefulness_score,
        avg_insight_confidence=result.avg_insight_confidence,
        avg_idea_score=result.avg_idea_score,
        token_usage=result.token_usage,
        top_ideas=result.top_ideas,
    )


def _apply_pipeline_request_overrides(profile, body: PipelineRunRequest | PipelineDryRunRequest):
    """Apply explicit API fields to a loaded profile, mirroring CLI overrides."""
    fields_set = body.model_fields_set
    profile = profile.model_copy(deep=True)
    if "signal_limit" in fields_set:
        profile.signal_limit = body.signal_limit
    if "min_score" in fields_set:
        profile.evaluation.min_score = body.min_score
    if "weight_profile" in fields_set:
        profile.evaluation.weight_profile = body.weight_profile
    if "ideation_mode" in fields_set:
        profile.ideation_mode = body.ideation_mode
    if "quality_loop_enabled" in fields_set:
        profile.quality_loop_enabled = body.quality_loop_enabled
    if "draft_count" in fields_set:
        profile.draft_count = body.draft_count
    return profile


def _aggregate_pipeline_results(results: list[PipelineResultResponse]) -> PipelineResultResponse:
    def total(field: str) -> int:
        return sum(getattr(result, field) for result in results)

    def weighted_average(score_field: str, weight_field: str) -> float:
        weighted_total = sum(
            getattr(result, score_field) * getattr(result, weight_field)
            for result in results
        )
        weights = total(weight_field)
        return weighted_total / weights if weights else 0.0

    token_usage: dict[str, int] = {}
    for result in results:
        for key, value in result.token_usage.items():
            token_usage[key] = token_usage.get(key, 0) + value

    top_ideas = [
        idea
        for result in results
        for idea in result.top_ideas
    ]
    top_ideas.sort(key=lambda idea: idea.get("score", idea.get("overall_score", 0)), reverse=True)

    return PipelineResultResponse(
        signals_fetched=total("signals_fetched"),
        signals_new=total("signals_new"),
        insights_generated=total("insights_generated"),
        ideas_generated=total("ideas_generated"),
        ideas_evaluated=total("ideas_evaluated"),
        draft_ideas_generated=total("draft_ideas_generated"),
        ideas_revised=total("ideas_revised"),
        ideas_rejected_by_quality_gate=total("ideas_rejected_by_quality_gate"),
        ideas_rejected_by_domain_quality=total("ideas_rejected_by_domain_quality"),
        avg_domain_quality_score=weighted_average(
            "avg_domain_quality_score", "draft_ideas_generated"
        ),
        avg_novelty_score=weighted_average("avg_novelty_score", "ideas_revised"),
        avg_usefulness_score=weighted_average("avg_usefulness_score", "ideas_revised"),
        avg_insight_confidence=weighted_average(
            "avg_insight_confidence", "insights_generated"
        ),
        avg_idea_score=weighted_average("avg_idea_score", "ideas_evaluated"),
        token_usage=token_usage,
        top_ideas=top_ideas[:10],
    )


@router.post(
    "/pipeline/post-run",
    response_model=PipelinePostRunResponse,
    dependencies=[Depends(rate_limit(config.MAX_RATE_LIMIT_EXPENSIVE_RPM))],
)
async def run_post_pipeline_endpoint(
    body: PipelinePostRunRequest,
) -> PipelinePostRunResponse:
    from max.pipeline.runner import run_post_pipeline

    result = await asyncio.to_thread(run_post_pipeline, domain=body.domain)
    return PipelinePostRunResponse(
        duplicates_marked=result.duplicates_marked,
        ideas_synthesized=result.ideas_synthesized,
        source_ideas_merged=result.source_ideas_merged,
        synthesis_clusters=result.synthesis_clusters,
        prior_art_checked=result.prior_art_checked,
        prior_art_strong=result.prior_art_strong,
        prior_art_weak=result.prior_art_weak,
        prior_art_clear=result.prior_art_clear,
        triage_auto_approved=result.triage_auto_approved,
        triage_auto_rejected=result.triage_auto_rejected,
        triage_pending_review=result.triage_pending_review,
    )


@router.post("/pipeline/dry-run", response_model=DryRunReportResponse)
async def dry_run_pipeline_endpoint(body: PipelineDryRunRequest) -> DryRunReportResponse:
    try:
        return await asyncio.to_thread(run_pipeline_dry_run, body)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Profile not found: {body.profile or 'default'}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def run_pipeline_dry_run(body: PipelineDryRunRequest) -> DryRunReportResponse:
    """Run the pipeline dry-run flow for REST and MCP callers."""
    from max.pipeline.runner import run_pipeline
    from max.profiles.loader import get_default_profile, load_profile

    profile = load_profile(body.profile) if body.profile else get_default_profile()
    profile = _apply_pipeline_request_overrides(profile, body)

    result = run_pipeline(
        profile=profile,
        dry_run=True,
        stages=body.stages,
    )
    return _dry_run_report_response(result, profile=profile)


def _dry_run_report_response(result, *, profile) -> DryRunReportResponse:
    return DryRunReportResponse(
        profile_name=profile.name if profile else None,
        domain=profile.domain.name if profile else None,
        enabled_adapters=result.enabled_adapters,
        fetch_allocation=result.fetch_allocation,
        effective_config=DryRunEffectiveConfigResponse(
            signal_limit=profile.signal_limit,
            min_score=profile.evaluation.min_score,
            weight_profile=profile.evaluation.weight_profile,
            ideation_mode=profile.ideation_mode,
            quality_loop_enabled=profile.quality_loop_enabled,
            draft_count=profile.draft_count,
        ) if profile else None,
        stages=[
            StageSummaryResponse(
                name=s.name,
                would_process=s.would_process,
                estimated_llm_calls=s.estimated_llm_calls,
                skipped=s.skipped,
                reason=s.reason,
                estimated_input_tokens=s.estimated_input_tokens,
                estimated_output_tokens=s.estimated_output_tokens,
                estimated_total_tokens=s.estimated_total_tokens,
                estimated_cost_usd=s.estimated_cost_usd,
            )
            for s in result.stages
        ],
        estimated_total_llm_calls=result.estimated_total_llm_calls,
        estimated_token_budget=result.estimated_token_budget,
        estimated_input_tokens=result.estimated_input_tokens,
        estimated_output_tokens=result.estimated_output_tokens,
        estimated_cost_usd=result.estimated_cost_usd,
        cost_by_stage=result.cost_by_stage,
    )


# ── Stats ───────────────────────────────────────────────────────────


@router.get("/stats", response_model=StatsResponse)
def get_stats(store: Store = Depends(get_store)) -> StatsResponse:
    signals_count = store.count_signals()

    insights = store.get_insights(limit=10000)
    insights_count = len(insights)

    all_units = store.get_buildable_units(limit=10000)
    ideas_count = len(all_units)
    evaluated_count = sum(1 for u in all_units if u.status in ("evaluated", "approved"))

    scores = []
    for unit in all_units:
        ev = store.get_evaluation(unit.id)
        if ev:
            scores.append(ev.overall_score)

    avg_score = sum(scores) / len(scores) if scores else None

    return StatsResponse(
        signals_count=signals_count,
        insights_count=insights_count,
        ideas_count=ideas_count,
        evaluated_count=evaluated_count,
        avg_score=avg_score,
    )


# ── Adapters ────────────────────────────────────────────────────────


@router.get("/adapters", response_model=list[AdapterMetadataResponse])
def get_adapters() -> list[AdapterMetadataResponse]:
    return [
        AdapterMetadataResponse(
            name=item.name,
            config_keys=item.config_keys,
            required_keys=item.required_keys,
            description=item.description,
        )
        for item in list_adapter_metadata()
    ]


@router.get("/adapters/circuit-breakers", response_model=list[CircuitBreakerStateResponse])
def get_adapter_circuit_breakers() -> list[CircuitBreakerStateResponse]:
    snapshots = snapshot_circuit_breakers(adapter_names=list_adapters())
    return [
        CircuitBreakerStateResponse(
            adapter_name=s.adapter_name,
            state=s.state,
            failure_count=s.failure_count,
            last_failure_at=s.last_failure_at,
            retry_after=s.retry_after,
        )
        for s in snapshots
    ]


@router.get("/adapters/health", response_model=AdapterHealthResponse)
def get_adapter_health(
    profile: str | None = Query(default=None, description="Optional profile name for enabled sources"),
    store: Store = Depends(get_store),
) -> AdapterHealthResponse:
    registered_adapters = sorted(list_adapters())
    enabled_profile_sources: list[str] = []

    if profile:
        profile_config = _load_profile_or_404(profile)
        enabled_profile_sources = sorted(
            source.adapter for source in profile_config.sources if source.enabled
        )

    circuit_breakers = [
        CircuitBreakerStateResponse(
            adapter_name=s.adapter_name,
            state=s.state,
            failure_count=s.failure_count,
            last_failure_at=s.last_failure_at,
            retry_after=s.retry_after,
        )
        for s in snapshot_circuit_breakers(adapter_names=registered_adapters)
    ]
    circuit_by_adapter = {cb.adapter_name: cb for cb in circuit_breakers}

    quality_stats = store.get_adapter_quality_stats()
    approval_stats = store.get_adapter_approval_stats()
    adapter_names = sorted(
        set(registered_adapters)
        | set(enabled_profile_sources)
        | set(circuit_by_adapter)
        | set(quality_stats)
        | set(approval_stats)
    )
    registered = set(registered_adapters)
    enabled = set(enabled_profile_sources)

    adapters = []
    for adapter_name in adapter_names:
        quality = quality_stats.get(adapter_name, {})
        approval = approval_stats.get(adapter_name, {})
        adapters.append(
            AdapterHealthItemResponse(
                adapter_name=adapter_name,
                registered=adapter_name in registered,
                enabled_for_profile=(adapter_name in enabled) if profile else None,
                circuit_breaker=circuit_by_adapter.get(adapter_name),
                total_signals=quality.get("total_signals", 0),
                insight_hit_rate=quality.get("insight_hit_rate", 0.0),
                idea_hit_rate=quality.get("idea_hit_rate", 0.0),
                total_feedbacked=approval.get("total_feedbacked", 0),
                approved=approval.get("approved", 0),
                rejected=approval.get("rejected", 0),
                approval_rate=approval.get("approval_rate", 0.0),
            )
        )

    return AdapterHealthResponse(
        profile=profile,
        registered_adapters=registered_adapters,
        enabled_profile_sources=enabled_profile_sources,
        circuit_breakers=circuit_breakers,
        adapters=adapters,
    )


@router.get("/fetch/allocation-explain", response_model=FetchAllocationExplainResponse)
def get_fetch_allocation_explain(
    profile: str = Query(
        ...,
        description="Profile name whose source configuration should be explained",
    ),
    total_budget: int = Query(..., ge=1, le=500, description="Total fetch signal budget"),
    store: Store = Depends(get_store),
) -> FetchAllocationExplainResponse:
    profile_config = _load_profile_or_404(profile)

    enabled_adapter_names = [source.adapter for source in profile_config.sources if source.enabled]

    from max.pipeline.fetch_strategy import compute_fetch_allocation

    allocation = compute_fetch_allocation(total_budget, enabled_adapter_names, store)
    quality_stats = store.get_adapter_quality_stats()
    approval_stats = store.get_adapter_approval_stats()

    adapters = []
    for source in profile_config.sources:
        quality = quality_stats.get(source.adapter, {})
        approval = approval_stats.get(source.adapter)
        adapters.append(
            FetchAllocationAdapterExplainResponse(
                adapter_name=source.adapter,
                enabled=source.enabled,
                configured_weight=source.weight,
                total_signals=quality.get("total_signals", 0),
                insight_hit_rate=quality.get("insight_hit_rate", 0.0),
                idea_hit_rate=quality.get("idea_hit_rate", 0.0),
                approval_rate=approval.get("approval_rate") if approval else None,
                allocated_limit=allocation.get(source.adapter, 0) if source.enabled else 0,
            )
        )

    return FetchAllocationExplainResponse(
        profile=profile,
        total_budget=total_budget,
        allocation=allocation,
        adapters=adapters,
    )


# ── Similarity ──────────────────────────────────────────────────────


@router.post("/similar", response_model=list[SimilarityResult])
def find_similar(body: SimilarityRequest, store: Store = Depends(get_store)) -> list[SimilarityResult]:
    from max.embeddings.engine import SemanticIndex

    index = SemanticIndex(store)
    results = index.find_similar(
        body.text,
        body.entity_type,
        threshold=body.threshold,
        limit=body.limit,
    )
    return [SimilarityResult(entity_id=eid, score=score) for eid, score in results]


# ── Schedule ────────────────────────────────────────────────────────


@router.get("/schedule", response_model=ScheduleStatusResponse)
def get_schedule(request: Request) -> ScheduleStatusResponse:
    scheduler = request.app.state.scheduler
    return scheduler.status()


@router.post("/schedule", response_model=ScheduleStatusResponse)
async def update_schedule(body: ScheduleUpdateRequest, request: Request) -> ScheduleStatusResponse:
    scheduler = request.app.state.scheduler
    scheduler.update(
        enabled=body.enabled,
        interval_seconds=body.interval_seconds,
        profile=body.profile,
        include_all=body.include_all,
        signal_limit=body.signal_limit,
        min_score=body.min_score,
        weight_profile=body.weight_profile,
        ideation_mode=body.ideation_mode,
        quality_loop_enabled=body.quality_loop_enabled,
        max_consecutive_failures=body.max_consecutive_failures,
    )
    if body.trigger_now:
        asyncio.ensure_future(scheduler.run_once())
    return scheduler.status()
