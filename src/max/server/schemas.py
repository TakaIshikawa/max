"""Request/response models for the REST API."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ── Request models ──────────────────────────────────────────────────


class SignalCreate(BaseModel):
    title: str
    content: str
    url: str
    source_type: str = "forum"
    source_adapter: str = "api"
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


class InsightCreate(BaseModel):
    category: str = "emerging_pattern"
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    domains: list[str] = Field(default_factory=list)
    implications: list[str] = Field(default_factory=list)
    time_horizon: str = "near_term"


class IdeaCreate(BaseModel):
    title: str
    one_liner: str
    category: str = Field(default="application", min_length=1)
    problem: str
    solution: str
    target_users: str = "both"
    value_proposition: str
    specific_user: str = ""
    buyer: str = ""
    workflow_context: str = ""
    current_workaround: str = ""
    why_now: str = ""
    validation_plan: str = ""
    first_10_customers: str = ""
    domain_risks: list[str] = Field(default_factory=list)
    evidence_rationale: str = ""
    tech_approach: str = ""
    suggested_stack: dict = Field(default_factory=dict)
    composability_notes: str = ""


class FeedbackCreate(BaseModel):
    outcome: Literal["approved", "rejected", "published", "abandoned"]
    reason: str = ""
    approval_score: int | None = Field(default=None, ge=1, le=10)


class PipelineRunRequest(BaseModel):
    signal_limit: int = Field(default=30, ge=1, le=500)
    min_score: float = Field(default=50.0, ge=0.0, le=100.0)
    weight_profile: Literal[
        "default", "quick_wins", "moonshots", "ecosystem", "agent_first"
    ] = "default"
    ideation_mode: Literal["direct", "refinement", "cross_domain"] = "direct"
    quality_loop_enabled: bool = False
    draft_count: int = Field(default=8, ge=1, le=50)
    output_dir: str | None = None
    stages: list[str] | None = None


class PipelineDryRunRequest(BaseModel):
    profile: str | None = None
    signal_limit: int = Field(default=30, ge=1, le=500)
    stages: list[str] | None = None


class SimilarityRequest(BaseModel):
    text: str
    entity_type: str
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    limit: int = Field(default=5, ge=1, le=100)


class PaginationParams(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


# ── Response models ─────────────────────────────────────────────────


class PaginationMeta(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    pagination: PaginationMeta


class SignalResponse(BaseModel):
    id: str
    source_type: str
    source_adapter: str
    title: str
    content: str
    url: str
    author: str | None = None
    published_at: str | None = None
    fetched_at: str
    tags: list[str]
    credibility: float
    metadata: dict


class InsightResponse(BaseModel):
    id: str
    category: str
    title: str
    summary: str
    evidence: list[str]
    confidence: float
    domains: list[str]
    implications: list[str]
    time_horizon: str
    created_at: str


class DimensionScoreResponse(BaseModel):
    value: float
    confidence: float
    reasoning: str


class EvaluationResponse(BaseModel):
    buildable_unit_id: str
    pain_severity: DimensionScoreResponse
    addressable_scale: DimensionScoreResponse
    build_effort: DimensionScoreResponse
    composability: DimensionScoreResponse
    competitive_density: DimensionScoreResponse
    timing_fit: DimensionScoreResponse
    compounding_value: DimensionScoreResponse
    overall_score: float
    rank: int | None
    strengths: list[str]
    weaknesses: list[str]
    recommendation: str
    weights_used: dict[str, float]


class IdeaSummaryResponse(BaseModel):
    id: str
    title: str
    one_liner: str
    category: str
    domain: str = ""
    status: str
    target_users: str
    specific_user: str = ""
    buyer: str = ""
    workflow_context: str = ""
    quality_score: float = 0.0
    novelty_score: float = 0.0
    usefulness_score: float = 0.0
    rejection_tags: list[str] = Field(default_factory=list)
    score: float | None = None
    recommendation: str | None = None


class IdeaDetailResponse(BaseModel):
    id: str
    title: str
    one_liner: str
    category: str
    domain: str = ""
    ideation_mode: str
    problem: str
    solution: str
    target_users: str
    value_proposition: str
    specific_user: str = ""
    buyer: str = ""
    workflow_context: str = ""
    current_workaround: str = ""
    why_now: str = ""
    validation_plan: str = ""
    first_10_customers: str = ""
    domain_risks: list[str] = Field(default_factory=list)
    evidence_rationale: str = ""
    novelty_score: float = 0.0
    usefulness_score: float = 0.0
    quality_score: float = 0.0
    rejection_tags: list[str] = Field(default_factory=list)
    inspiring_insights: list[str]
    evidence_signals: list[str]
    tech_approach: str
    suggested_stack: dict
    composability_notes: str
    status: str
    created_at: str
    updated_at: str
    evaluation: EvaluationResponse | None = None


class PipelineResultResponse(BaseModel):
    signals_fetched: int
    signals_new: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    draft_ideas_generated: int = 0
    ideas_revised: int = 0
    ideas_rejected_by_quality_gate: int = 0
    avg_novelty_score: float = 0.0
    avg_usefulness_score: float = 0.0
    avg_insight_confidence: float
    avg_idea_score: float
    token_usage: dict[str, int]
    top_ideas: list[dict]


class SimilarityResult(BaseModel):
    entity_id: str
    score: float


class StatsResponse(BaseModel):
    signals_count: int
    insights_count: int
    ideas_count: int
    evaluated_count: int
    avg_score: float | None = None


class PipelineResultSummary(BaseModel):
    signals_fetched: int
    signals_new: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    avg_insight_confidence: float
    avg_idea_score: float


class ScheduleStatusResponse(BaseModel):
    enabled: bool
    interval_seconds: int
    running: bool
    last_run_at: str | None = None
    next_run_at: str | None = None
    run_count: int
    last_error: str | None = None
    last_error_at: str | None = None
    failure_streak: int = 0
    max_consecutive_failures: int = 3
    last_result: PipelineResultSummary | None = None
    pipeline_config: dict


class ScheduleUpdateRequest(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=60)
    signal_limit: int | None = Field(default=None, ge=1, le=500)
    min_score: float | None = Field(default=None, ge=0.0, le=100.0)
    weight_profile: Literal[
        "default", "quick_wins", "moonshots", "ecosystem", "agent_first"
    ] | None = None
    ideation_mode: Literal["direct", "refinement", "cross_domain"] | None = None
    max_consecutive_failures: int | None = Field(default=None, ge=1)
    trigger_now: bool = False


class HealthResponse(BaseModel):
    status: str
    database: bool
    version: int
    uptime_seconds: float


class PipelineRunHistoryResponse(BaseModel):
    id: str
    started_at: str
    finished_at: str | None
    signals_fetched: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    status: str


class StageSummaryResponse(BaseModel):
    name: str
    would_process: int
    estimated_llm_calls: int
    skipped: bool
    reason: str


class DryRunReportResponse(BaseModel):
    stages: list[StageSummaryResponse]
    estimated_total_llm_calls: int
    estimated_token_budget: int
