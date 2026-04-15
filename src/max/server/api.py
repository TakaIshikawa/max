"""REST API routes for the max idea service."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from max import config
from max.server.dependencies import get_store
from max.server.rate_limit import rate_limit
from max.server.schemas import (
    DimensionScoreResponse,
    EvaluationResponse,
    FeedbackCreate,
    HealthResponse,
    IdeaCreate,
    IdeaDetailResponse,
    IdeaSummaryResponse,
    InsightCreate,
    InsightResponse,
    PaginatedResponse,
    PaginationMeta,
    PipelineResultResponse,
    PipelineRunHistoryResponse,
    PipelineRunRequest,
    ScheduleStatusResponse,
    ScheduleUpdateRequest,
    SignalCreate,
    SignalResponse,
    SimilarityRequest,
    SimilarityResult,
    StatsResponse,
)
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


def _unit_summary(unit, evaluation=None) -> IdeaSummaryResponse:
    return IdeaSummaryResponse(
        id=unit.id,
        title=unit.title,
        one_liner=unit.one_liner,
        category=unit.category,
        domain=unit.domain,
        status=unit.status,
        target_users=unit.target_users,
        score=evaluation.overall_score if evaluation else None,
        recommendation=evaluation.recommendation if evaluation else None,
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


def _unit_detail(unit, evaluation=None) -> IdeaDetailResponse:
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
        inspiring_insights=unit.inspiring_insights,
        evidence_signals=unit.evidence_signals,
        tech_approach=unit.tech_approach,
        suggested_stack=unit.suggested_stack,
        composability_notes=unit.composability_notes,
        status=unit.status,
        created_at=unit.created_at.isoformat() if hasattr(unit.created_at, "isoformat") else unit.created_at,
        updated_at=unit.updated_at.isoformat() if hasattr(unit.updated_at, "isoformat") else unit.updated_at,
        evaluation=_evaluation_to_response(evaluation) if evaluation else None,
    )


# ── Signals ─────────────────────────────────────────────────────────


@router.get("/signals")
def list_signals(
    cursor: str | None = None,
    limit: int = 20,
    source_type: str | None = None,
    store: Store = Depends(get_store),
) -> PaginatedResponse[SignalResponse]:
    # Clamp limit to max 100
    limit = min(limit, 100)

    try:
        signals, next_cursor = store.get_signals_paginated(
            cursor=cursor, limit=limit, source_type=source_type
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_count = store.count_signals(source_type=source_type)

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
    signal = Signal(
        source_type=body.source_type,
        source_adapter=body.source_adapter,
        title=body.title,
        content=body.content,
        url=body.url,
        author=body.author,
        tags=body.tags,
        credibility=body.credibility,
        metadata=body.metadata,
    )
    signal = store.insert_signal(signal)
    return _signal_to_response(signal)


# ── Insights ────────────────────────────────────────────────────────


@router.get("/insights")
def list_insights(
    cursor: str | None = None,
    limit: int = 20,
    store: Store = Depends(get_store),
) -> PaginatedResponse[InsightResponse]:
    # Clamp limit to max 100
    limit = min(limit, 100)

    try:
        insights, next_cursor = store.get_insights_paginated(cursor=cursor, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_count = store.count_insights()

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
        results.append(_unit_summary(unit, evaluation))

    total_count = store.count_buildable_units(status=status, domain=domain)

    return PaginatedResponse[IdeaSummaryResponse](
        items=results,
        pagination=PaginationMeta(
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            total_count=total_count,
        ),
    )


@router.get("/ideas/{idea_id}", response_model=IdeaDetailResponse)
def get_idea(idea_id: str, store: Store = Depends(get_store)) -> IdeaDetailResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    return _unit_detail(unit, evaluation)


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

    store.insert_feedback(idea_id, body.outcome, body.reason)
    store.update_buildable_unit_status(idea_id, body.outcome)
    return {"status": "ok", "idea_id": idea_id, "outcome": body.outcome}


# ── Pipeline ────────────────────────────────────────────────────────


@router.post(
    "/pipeline/run",
    response_model=PipelineResultResponse,
    dependencies=[Depends(rate_limit(config.MAX_RATE_LIMIT_EXPENSIVE_RPM))],
)
async def run_pipeline_endpoint(body: PipelineRunRequest) -> PipelineResultResponse:
    from max.pipeline.runner import run_pipeline

    output_dir = Path(body.output_dir) if body.output_dir else None
    result = await asyncio.to_thread(
        run_pipeline,
        output_dir=output_dir,
        signal_limit=body.signal_limit,
        min_score=body.min_score,
        weight_profile=body.weight_profile,
        ideation_mode=body.ideation_mode,
    )
    return PipelineResultResponse(
        signals_fetched=result.signals_fetched,
        signals_new=result.signals_new,
        insights_generated=result.insights_generated,
        ideas_generated=result.ideas_generated,
        ideas_evaluated=result.ideas_evaluated,
        avg_insight_confidence=result.avg_insight_confidence,
        avg_idea_score=result.avg_idea_score,
        token_usage=result.token_usage,
        top_ideas=result.top_ideas,
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
