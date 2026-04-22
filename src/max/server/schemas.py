"""Request/response models for the REST API."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from max.profiles.schema import DomainContext, EvaluationConfig, SourceConfig

T = TypeVar("T")


# ── Request models ──────────────────────────────────────────────────


class SignalCreate(BaseModel):
    title: str
    content: str
    url: str
    source_type: str = "forum"
    source_adapter: str = "api"
    signal_role: str | None = None
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
    target_users: str = Field(default="both", min_length=1)
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


class PriorArtCheckRequest(BaseModel):
    force: bool = False


class IdeaEvaluateBatchRequest(BaseModel):
    idea_ids: list[str] = Field(min_length=1, max_length=25)
    skip_existing: bool = False


class PipelineRunRequest(BaseModel):
    profile: str | None = None
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
    include_all: bool = False


class PipelineDryRunRequest(BaseModel):
    profile: str | None = None
    signal_limit: int = Field(default=30, ge=1, le=500)
    stages: list[str] | None = None


class PipelinePostRunRequest(BaseModel):
    domain: str | None = None


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
    signal_role: str = ""
    title: str
    content: str
    url: str
    author: str | None = None
    published_at: str | None = None
    fetched_at: str
    tags: list[str]
    credibility: float
    metadata: dict


class SignalCreateResponse(SignalResponse):
    status: Literal["created", "duplicate"]


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


class InsightDetailResponse(InsightResponse):
    evidence_signals: list[SignalResponse] = Field(default_factory=list)
    missing_evidence_ids: list[str] = Field(default_factory=list)


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


class IdeaCritiqueResponse(BaseModel):
    id: str
    buildable_unit_id: str
    pipeline_run_id: str | None = None
    stage: str
    dimensions: dict[str, float]
    reasoning: str
    rejection_tags: list[str]
    created_at: str


class IdeaMemoryResponse(BaseModel):
    id: str
    buildable_unit_id: str | None = None
    domain: str
    outcome: str
    pattern: str
    rejection_tags: list[str]
    score: float
    evidence_rationale: str
    created_at: str


class IdeaSummaryResponse(BaseModel):
    id: str
    title: str
    one_liner: str
    category: str
    domain: str = ""
    status: str
    review_state: str = "pending"
    feedback_outcome: str | None = None
    feedback_reason: str = ""
    reviewed_at: str | None = None
    graph_labels: list[str] = Field(default_factory=list)
    is_approved: bool = False
    target_users: str
    specific_user: str = ""
    buyer: str = ""
    workflow_context: str = ""
    quality_score: float = 0.0
    novelty_score: float = 0.0
    usefulness_score: float = 0.0
    rejection_tags: list[str] = Field(default_factory=list)
    latest_critique: IdeaCritiqueResponse | None = None
    score: float | None = None
    recommendation: str | None = None


class EvaluationSummaryResponse(BaseModel):
    overall_score: float
    rank: int | None
    recommendation: str
    strengths: list[str]
    weaknesses: list[str]


class EvaluationWeightProfileResponse(BaseModel):
    name: str
    weights: dict[str, float]
    adapted: bool = False
    adapted_weights: dict[str, float] | None = None


class ReviewQueueItemResponse(IdeaSummaryResponse):
    evaluation: EvaluationSummaryResponse
    latest_critique: IdeaCritiqueResponse | None = None


class IdeaEvaluateBatchItemResponse(BaseModel):
    idea_id: str
    status: Literal["evaluated", "skipped", "error"]
    success: bool
    evaluation: EvaluationSummaryResponse | None = None
    error: str | None = None


class IdeaEvaluateBatchResponse(BaseModel):
    results: list[IdeaEvaluateBatchItemResponse]


class IdeaStatusCountResponse(BaseModel):
    status: str
    count: int


class IdeaDomainStatusSummaryResponse(BaseModel):
    domain: str
    count: int
    statuses: dict[str, int]


class IdeaRecommendationStatusSummaryResponse(BaseModel):
    recommendation: str
    count: int
    statuses: dict[str, int]


class IdeaStatusSummaryGroupResponse(BaseModel):
    status: str
    domain: str
    recommendation: str | None = None
    count: int


class IdeaStatusSummaryResponse(BaseModel):
    total: int
    totals: dict[str, int]
    by_status: list[IdeaStatusCountResponse]
    by_domain: list[IdeaDomainStatusSummaryResponse]
    by_recommendation: list[IdeaRecommendationStatusSummaryResponse]
    groups: list[IdeaStatusSummaryGroupResponse]


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
    review_state: str = "pending"
    feedback_outcome: str | None = None
    feedback_reason: str = ""
    reviewed_at: str | None = None
    graph_labels: list[str] = Field(default_factory=list)
    is_approved: bool = False
    created_at: str
    updated_at: str
    latest_critique: IdeaCritiqueResponse | None = None
    evaluation: EvaluationResponse | None = None


class PriorArtMatchResponse(BaseModel):
    id: str
    buildable_unit_id: str
    source: str
    title: str
    url: str
    description: str
    relevance_score: float
    match_signals: dict
    search_query: str
    created_at: str


class PriorArtResponse(BaseModel):
    idea_id: str
    prior_art_status: str
    matches: list[PriorArtMatchResponse]


class EvidenceChainEdgeResponse(BaseModel):
    source: str
    target: str
    type: str
    role: Literal["inspires", "evidenced_by"]


class EvidenceChainResponse(BaseModel):
    idea_id: str
    idea: dict
    insights: list[dict]
    signals: list[dict]
    edges: list[EvidenceChainEdgeResponse]


class DesignBriefSourceResponse(BaseModel):
    idea_id: str
    role: str
    rank: int


class DesignBriefResponse(BaseModel):
    id: str
    title: str
    domain: str
    theme: str
    readiness_score: float
    lead_idea_id: str
    buyer: str
    specific_user: str
    workflow_context: str
    why_this_now: str
    merged_product_concept: str
    synthesis_rationale: str
    mvp_scope: list[str]
    first_milestones: list[str]
    validation_plan: str
    risks: list[str]
    source_idea_ids: list[str]
    design_status: str
    created_at: str
    updated_at: str
    sources: list[DesignBriefSourceResponse]


class DesignBriefStatusUpdate(BaseModel):
    status: Literal["draft", "approved", "published", "archived", "rejected"]


class FeedbackTrendDomainResponse(BaseModel):
    domain: str
    total_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    avg_score: float


class FeedbackTrendWindowResponse(BaseModel):
    window_start: str
    window_end: str
    total_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    avg_score: float
    domains: list[FeedbackTrendDomainResponse]


class FeedbackTrendResponse(BaseModel):
    days: int
    bucket: Literal["day", "week", "month"]
    window_count: int
    total_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    avg_score: float
    windows: list[FeedbackTrendWindowResponse]


class BlueprintSourceBriefResponse(BaseModel):
    schema_version: str
    source: dict
    design_brief: dict
    source_ideas: list[dict]
    blueprint_import_hints: dict


class DomainQualityScoreResponse(BaseModel):
    id: str
    buildable_unit_id: str
    domain: str
    profile_name: str
    rubric_version: str
    dimensions: dict[str, float]
    overall_score: float
    passed_gate: bool
    rejection_tags: list[str]
    reasoning: str
    created_at: str


class DomainQualityMemoryResponse(BaseModel):
    id: str
    domain: str
    outcome: str
    pattern: str
    source_idea_id: str | None = None
    source_design_brief_id: str | None = None
    tags: list[str]
    score: float
    notes: str
    created_at: str


class ProfileSummaryResponse(BaseModel):
    name: str
    domain: str
    description: str
    enabled_source_count: int
    signal_limit: int
    min_score: float
    weight_profile: str
    ideation_mode: str
    quality_loop_enabled: bool


class ProfileDetailResponse(BaseModel):
    name: str
    domain: DomainContext
    sources: list[SourceConfig]
    evaluation: EvaluationConfig
    output_dir: str
    signal_limit: int
    ideation_mode: str
    quality_loop_enabled: bool
    draft_count: int


class PipelineResultResponse(BaseModel):
    profile_name: str | None = None
    domain: str | None = None
    signals_fetched: int
    signals_new: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    draft_ideas_generated: int = 0
    ideas_revised: int = 0
    ideas_rejected_by_quality_gate: int = 0
    ideas_rejected_by_domain_quality: int = 0
    avg_domain_quality_score: float = 0.0
    avg_novelty_score: float = 0.0
    avg_usefulness_score: float = 0.0
    avg_insight_confidence: float
    avg_idea_score: float
    token_usage: dict[str, int]
    top_ideas: list[dict]


class PipelineAggregateResultResponse(BaseModel):
    profile: Literal["all"] = "all"
    include_all: bool = False
    focus_domains: list[str] | None = None
    skipped_profiles: list[str] = Field(default_factory=list)
    profiles_run: int
    totals: PipelineResultResponse
    profiles: list[PipelineResultResponse]


class LLMUsageRunResponse(BaseModel):
    id: str
    started_at: str
    finished_at: str | None = None
    status: str
    model: str
    total_input: int
    total_output: int
    total_cost_usd: float | None = None
    token_usage: dict[str, object] = Field(default_factory=dict)


class LLMUsageResponse(BaseModel):
    limit: int
    run_count: int
    total_input: int
    total_output: int
    total_cost_usd: float | None = None
    runs: list[LLMUsageRunResponse]


class PipelinePostRunResponse(BaseModel):
    duplicates_marked: int
    ideas_synthesized: int
    source_ideas_merged: int
    synthesis_clusters: int
    prior_art_checked: int
    prior_art_strong: int
    prior_art_weak: int
    prior_art_clear: int
    triage_auto_approved: int
    triage_auto_rejected: int
    triage_pending_review: int


class SimilarityResult(BaseModel):
    entity_id: str
    score: float


class StatsResponse(BaseModel):
    signals_count: int
    insights_count: int
    ideas_count: int
    evaluated_count: int
    avg_score: float | None = None


class AdapterMetadataResponse(BaseModel):
    name: str
    config_keys: list[str]
    required_keys: list[str]
    description: str


class CircuitBreakerStateResponse(BaseModel):
    adapter_name: str
    state: str
    failure_count: int
    last_failure_at: float | None = None
    retry_after: float


class AdapterHealthItemResponse(BaseModel):
    adapter_name: str
    registered: bool
    enabled_for_profile: bool | None = None
    circuit_breaker: CircuitBreakerStateResponse | None = None
    total_signals: int = 0
    insight_hit_rate: float = 0.0
    idea_hit_rate: float = 0.0
    total_feedbacked: int = 0
    approved: int = 0
    rejected: int = 0
    approval_rate: float = 0.0


class AdapterHealthResponse(BaseModel):
    profile: str | None = None
    registered_adapters: list[str]
    enabled_profile_sources: list[str] = Field(default_factory=list)
    circuit_breakers: list[CircuitBreakerStateResponse]
    adapters: list[AdapterHealthItemResponse]


class FetchAllocationAdapterExplainResponse(BaseModel):
    adapter_name: str
    enabled: bool
    configured_weight: float
    total_signals: int = 0
    insight_hit_rate: float = 0.0
    idea_hit_rate: float = 0.0
    approval_rate: float | None = None
    allocated_limit: int = 0


class FetchAllocationExplainResponse(BaseModel):
    profile: str
    total_budget: int
    allocation: dict[str, int]
    adapters: list[FetchAllocationAdapterExplainResponse]


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
    profile: str | None = None
    include_all: bool = False
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
    profile: str | None = None
    include_all: bool | None = None
    signal_limit: int | None = Field(default=None, ge=1, le=500)
    min_score: float | None = Field(default=None, ge=0.0, le=100.0)
    weight_profile: Literal[
        "default", "quick_wins", "moonshots", "ecosystem", "agent_first"
    ] | None = None
    ideation_mode: Literal["direct", "refinement", "cross_domain"] | None = None
    quality_loop_enabled: bool | None = None
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
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class DryRunReportResponse(BaseModel):
    stages: list[StageSummaryResponse]
    estimated_total_llm_calls: int
    estimated_token_budget: int
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cost_by_stage: dict[str, float] = Field(default_factory=dict)
