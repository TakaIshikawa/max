"""REST API routes for the max idea service."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from max import config
from max.server.dependencies import get_store
from max.server.evidence_chain import build_evidence_chain_graph
from max.server.rate_limit import rate_limit
from max.server.schemas import (
    BlueprintSourceBriefResponse,
    CircuitBreakerStateResponse,
    DesignBriefResponse,
    DomainQualityMemoryResponse,
    DomainQualityScoreResponse,
    DimensionScoreResponse,
    DryRunReportResponse,
    EvidenceChainResponse,
    EvaluationResponse,
    FeedbackCreate,
    HealthResponse,
    IdeaCreate,
    IdeaCritiqueResponse,
    IdeaDetailResponse,
    IdeaMemoryResponse,
    IdeaStatusSummaryResponse,
    IdeaSummaryResponse,
    InsightCreate,
    InsightDetailResponse,
    InsightResponse,
    PaginatedResponse,
    PaginationMeta,
    PipelineAggregateResultResponse,
    PipelineDryRunRequest,
    PipelinePostRunRequest,
    PipelinePostRunResponse,
    PipelineResultResponse,
    PipelineRunHistoryResponse,
    PipelineRunRequest,
    ProfileDetailResponse,
    ProfileSummaryResponse,
    ScheduleStatusResponse,
    ScheduleUpdateRequest,
    SignalCreate,
    SignalResponse,
    SimilarityRequest,
    SimilarityResult,
    StageSummaryResponse,
    StatsResponse,
)
from max.sources.base import snapshot_circuit_breakers
from max.sources.registry import list_adapters
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


@router.get("/profiles/{profile_name}", response_model=ProfileDetailResponse)
def get_pipeline_profile(profile_name: str) -> ProfileDetailResponse:
    return _profile_detail_to_response(_load_profile_or_404(profile_name))


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


@router.post("/signals", response_model=SignalResponse, status_code=201)
def create_signal(body: SignalCreate, store: Store = Depends(get_store)) -> SignalResponse:
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
    signal = store.insert_signal(signal)
    return _signal_to_response(signal)


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


# ── Ideas ───────────────────────────────────────────────────────────


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


@router.post("/ideas/{idea_id}/feedback", status_code=201)
def create_feedback(
    idea_id: str,
    body: FeedbackCreate,
    store: Store = Depends(get_store),
) -> dict:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    store.insert_feedback(idea_id, body.outcome, body.reason, approval_score=body.approval_score)
    store.update_buildable_unit_status(idea_id, body.outcome)
    return {"status": "ok", "idea_id": idea_id, "outcome": body.outcome}


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


@router.get("/design-briefs/{brief_id}", response_model=DesignBriefResponse)
def get_design_brief(brief_id: str, store: Store = Depends(get_store)) -> DesignBriefResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return _design_brief_to_response(brief)


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


def _apply_pipeline_request_overrides(profile, body: PipelineRunRequest):
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
    from max.pipeline.runner import run_pipeline
    from max.profiles.loader import get_default_profile, load_profile

    try:
        profile = load_profile(body.profile) if body.profile else get_default_profile()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {body.profile}")

    profile = profile.model_copy(deep=True)
    if "signal_limit" in body.model_fields_set:
        profile.signal_limit = body.signal_limit

    try:
        result = await asyncio.to_thread(
            run_pipeline,
            profile=profile,
            dry_run=True,
            stages=body.stages,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DryRunReportResponse(
        stages=[
            StageSummaryResponse(
                name=s.name,
                would_process=s.would_process,
                estimated_llm_calls=s.estimated_llm_calls,
                skipped=s.skipped,
                reason=s.reason,
            )
            for s in result.stages
        ],
        estimated_total_llm_calls=result.estimated_total_llm_calls,
        estimated_token_budget=result.estimated_token_budget,
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
        signal_limit=body.signal_limit,
        min_score=body.min_score,
        weight_profile=body.weight_profile,
        ideation_mode=body.ideation_mode,
        max_consecutive_failures=body.max_consecutive_failures,
    )
    if body.trigger_now:
        asyncio.ensure_future(scheduler.run_once())
    return scheduler.status()
