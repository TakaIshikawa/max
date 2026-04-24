"""Request/response models for the REST API."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, model_validator

from max.profiles.schema import (
    ArchitectureConstraintsConfig,
    DomainContext,
    EvaluationConfig,
    SourceConfig,
)

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


class SignalImportRow(BaseModel):
    id: str | None = None
    title: Any = None
    content: Any = None
    url: Any = None
    source_type: str | None = None
    source_adapter: str | None = None
    signal_role: str | None = None
    author: Any = None
    published_at: Any = None
    fetched_at: Any = None
    tags: list[Any] | str | None = None
    credibility: Any = None
    metadata: dict[str, Any] | str | None = None


class SignalImportRequest(BaseModel):
    rows: list[SignalImportRow] = Field(min_length=1)
    source_adapter: str | None = None
    source_type: str | None = None
    credibility: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class MCPSecurityFindingImportRow(BaseModel):
    scanner: Any = None
    server_name: Any = None
    package_name: Any = None
    package_version: Any = None
    severity: Any = None
    finding_type: Any = None
    title: Any = None
    description: Any = None
    evidence_url: Any = None
    discovered_at: Any = None
    remediation: Any = None


class MCPSecurityFindingsImportRequest(BaseModel):
    findings: list[MCPSecurityFindingImportRow] = Field(min_length=1)


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


class FeedbackWebhookRequest(BaseModel):
    idea_id: str
    outcome: Literal["approved", "rejected", "published", "abandoned"]
    reason: str = ""
    approval_score: int | None = Field(default=None, ge=1, le=10)
    external_run_id: str
    external_url: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackBatchItem(BaseModel):
    idea_id: str
    outcome: Literal["approved", "rejected", "published", "abandoned"]
    reason: str = ""
    approval_score: int | None = Field(default=None, ge=1, le=10)


class FeedbackBatchRequest(BaseModel):
    items: list[FeedbackBatchItem] = Field(min_length=1)


class PriorArtCheckRequest(BaseModel):
    force: bool = False


class ValidationExperimentCreate(BaseModel):
    hypothesis: str = Field(min_length=1)
    method: str = Field(min_length=1)
    target_sample_size: int | None = Field(default=None, ge=1)
    success_metric: str = Field(min_length=1)
    status: str = Field(default="planned", min_length=1)
    started_at: str | None = None
    due_date: str | None = None
    completed_at: str | None = None
    result_summary: str = ""
    evidence_urls: list[str] = Field(default_factory=list)
    confidence_delta: float | None = Field(default=None, ge=-1.0, le=1.0)


class ValidationExperimentUpdate(BaseModel):
    hypothesis: str | None = Field(default=None, min_length=1)
    method: str | None = Field(default=None, min_length=1)
    target_sample_size: int | None = Field(default=None, ge=1)
    success_metric: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, min_length=1)
    started_at: str | None = None
    due_date: str | None = None
    completed_at: str | None = None
    result_summary: str | None = None
    evidence_urls: list[str] | None = None
    confidence_delta: float | None = Field(default=None, ge=-1.0, le=1.0)


class SlackPublishRequest(BaseModel):
    webhook_url: str | None = None
    channel: str | None = None
    dry_run: bool = False
    timeout: float = Field(default=10.0, gt=0.0)


class DiscordPublishRequest(BaseModel):
    webhook_url: str | None = None
    username: str | None = None
    dry_run: bool = False
    timeout: float = Field(default=10.0, gt=0.0)


class TeamsPublishRequest(BaseModel):
    webhook_url: str | None = None
    title: str | None = Field(default=None, min_length=1)
    dry_run: bool = False
    include_evidence: bool = True
    timeout: float = Field(default=10.0, gt=0.0)


WebhookPayloadField = Literal["idea", "evaluation", "evidence_links", "spec_preview"]


class WebhookPublishRequest(BaseModel):
    webhook_url: str = Field(min_length=1)
    payload_template: dict[str, Any] | None = None
    payload_fields: list[WebhookPayloadField] = Field(
        default_factory=lambda: ["idea", "evaluation", "evidence_links", "spec_preview"]
    )
    dry_run: bool = False
    timeout: float = Field(default=10.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0)


class GitHubIssuePublishRequest(BaseModel):
    repository: str | None = None
    token: str | None = None
    api_url: str | None = None
    labels: list[str] = Field(default_factory=list)
    timeout: float = Field(default=10.0, gt=0.0)
    dry_run: bool = True


class GitLabIssuePublishRequest(BaseModel):
    project: str | None = Field(default=None, min_length=1)
    project_id: str | None = Field(default=None, min_length=1)
    project_path: str | None = Field(default=None, min_length=1)
    token: str | None = None
    base_url: str | None = None
    title: str | None = Field(default=None, min_length=1)
    labels: list[str] = Field(default_factory=list)
    assignee_ids: list[int] = Field(default_factory=list)
    confidential: bool = False
    dry_run: bool = True
    timeout: float = Field(default=10.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0, le=5)


class GitHubGistPublishRequest(BaseModel):
    token: str | None = None
    api_url: str | None = None
    public: bool = False
    filename: str = Field(default="idea.md", min_length=1)
    description: str | None = Field(default=None, min_length=1)
    evidence_links: list[str] = Field(default_factory=list)
    timeout: float = Field(default=10.0, gt=0.0)
    dry_run: bool = True


class LinearIssuePublishRequest(BaseModel):
    api_key: str | None = None
    team_id: str | None = None
    project_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    priority: int | None = Field(default=None, ge=0, le=4)
    dry_run: bool = True
    timeout: float = Field(default=10.0, gt=0.0)


class AsanaTaskPublishRequest(BaseModel):
    access_token: str | None = None
    workspace_gid: str | None = Field(default=None, min_length=1)
    project_gid: str | None = Field(default=None, min_length=1)
    section_gid: str | None = Field(default=None, min_length=1)
    assignee_gid: str | None = Field(default=None, min_length=1)
    tags: list[str] = Field(default_factory=list)
    due_on: str | None = Field(default=None, min_length=1)
    dry_run: bool = True
    timeout: float = Field(default=10.0, gt=0.0)


class ClickUpTaskPublishRequest(BaseModel):
    api_token: str | None = None
    api_url: str | None = None
    list_id: str | None = Field(default=None, min_length=1)
    assignees: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    priority: int | None = Field(default=None, ge=1, le=4)
    due_date: int | str | None = None
    custom_fields: list[dict[str, Any]] = Field(default_factory=list)
    dry_run: bool = True
    timeout: float = Field(default=10.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0, le=5)


class JiraIssuePublishRequest(BaseModel):
    site_url: str | None = None
    project_key: str | None = None
    email: str | None = None
    api_token: str | None = None
    bearer_token: str | None = None
    issue_type: str | None = "Task"
    labels: list[str] = Field(default_factory=list)
    dry_run: bool = True
    timeout: float = Field(default=10.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0, le=5)


class AzureDevOpsWorkItemPublishRequest(BaseModel):
    organization: str | None = None
    project: str | None = None
    personal_access_token: str | None = None
    work_item_type: str | None = "User Story"
    area_path: str | None = None
    iteration_path: str | None = None
    tags: list[str] = Field(default_factory=list)
    dry_run: bool = True
    timeout: float = Field(default=10.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0, le=5)


class TrelloCardPublishRequest(BaseModel):
    key: str | None = None
    token: str | None = None
    api_url: str | None = None
    list_id: str | None = Field(default=None, min_length=1)
    labels: list[str] = Field(default_factory=list)
    due: str | None = Field(default=None, min_length=1)
    dry_run: bool = True
    timeout: float = Field(default=10.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0, le=5)


class NotionPagePublishRequest(BaseModel):
    token: str | None = None
    parent_page_id: str | None = None
    parent_database_id: str | None = None
    title: str | None = None
    dry_run: bool = False
    timeout: float = Field(default=10.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0, le=5)


PriorArtSource = Literal["github", "npm", "pypi", "product_hunt"]


class BatchPriorArtCheckRequest(BaseModel):
    idea_ids: list[str] = Field(min_length=1, max_length=25)
    force: bool = False
    max_concurrency: int = Field(default=3, ge=1, le=25)
    sources: list[PriorArtSource] | None = Field(default=None, min_length=1)


class IdeaEvaluateBatchRequest(BaseModel):
    idea_ids: list[str] = Field(min_length=1, max_length=25)
    skip_existing: bool = False


class SpecReadinessBatchRequest(BaseModel):
    idea_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    domain: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def require_ids_or_filter(self) -> "SpecReadinessBatchRequest":
        if not self.idea_ids and not (self.domain or self.status):
            raise ValueError("Provide idea_ids or at least one filter: domain or status")
        return self


class PipelineRunRequest(BaseModel):
    profile: str | None = None
    signal_limit: int = Field(default=30, ge=1, le=500)
    min_score: float = Field(default=50.0, ge=0.0, le=100.0)
    weight_profile: Literal["default", "quick_wins", "moonshots", "ecosystem", "agent_first"] = (
        "default"
    )
    ideation_mode: Literal["direct", "refinement", "cross_domain"] = "direct"
    quality_loop_enabled: bool = False
    draft_count: int = Field(default=8, ge=1, le=50)
    output_dir: str | None = None
    stages: list[str] | None = None
    include_all: bool = False


class PipelineDryRunRequest(BaseModel):
    profile: str | None = None
    signal_limit: int = Field(default=30, ge=1, le=500)
    min_score: float = Field(default=50.0, ge=0.0, le=100.0)
    weight_profile: Literal["default", "quick_wins", "moonshots", "ecosystem", "agent_first"] = (
        "default"
    )
    ideation_mode: Literal["direct", "refinement", "cross_domain"] = "direct"
    quality_loop_enabled: bool = False
    draft_count: int = Field(default=8, ge=1, le=50)
    stages: list[str] | None = None


class PipelinePostRunRequest(BaseModel):
    domain: str | None = None


class SimilarityRequest(BaseModel):
    text: str
    entity_type: str
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    limit: int = Field(default=5, ge=1, le=100)


class IdeaSimilarityRequest(BaseModel):
    idea_id: str | None = None
    query: str | None = None
    threshold: float = Field(default=0.1, ge=0.0, le=1.0)
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


class SignalImportRowResult(BaseModel):
    index: int
    signal_id: str | None = None
    duplicate_id: str | None = None
    error: str | None = None


class SignalImportResponse(BaseModel):
    inserted_count: int
    duplicate_count: int
    error_count: int
    results: list[SignalImportRowResult]


class MCPSecurityFindingImportResult(BaseModel):
    index: int
    signal_id: str | None = None
    duplicate_id: str | None = None
    error: str | None = None


class MCPSecurityFindingsImportResponse(BaseModel):
    inserted_count: int
    duplicate_count: int
    error_count: int
    results: list[MCPSecurityFindingImportResult]


class SignalFreshnessGroupResponse(BaseModel):
    key: str
    total_count: int
    newest_timestamp: str | None
    oldest_timestamp: str | None
    median_age_days: float | None
    stale_count: int


class SignalFreshnessRecommendationResponse(BaseModel):
    source_adapter: str
    stale_count: int
    total_count: int
    newest_timestamp: str | None
    median_age_days: float | None
    reason: str
    action: str


class SignalFreshnessResponse(BaseModel):
    generated_at: str
    max_age_days: int
    source_adapter_filters: list[str]
    total_signals: int
    stale_signals: int
    by_source_adapter: list[SignalFreshnessGroupResponse]
    by_source_type: list[SignalFreshnessGroupResponse]
    by_domain_tag: list[SignalFreshnessGroupResponse]
    by_signal_role: list[SignalFreshnessGroupResponse]
    recommendations: list[SignalFreshnessRecommendationResponse]


class SourceReliabilityTypeResponse(BaseModel):
    source_type: str
    total_signals: int
    source_adapters: list[str]
    registered_adapters: list[str]
    adapter_health_score: float
    signal_usefulness_score: float
    corroboration_rate: float
    downstream_idea_conversion_rate: float
    feedback_approval_rate: float | None = None
    reliability_score: float
    reasons: list[str]


class SourceReliabilityResponse(BaseModel):
    generated_at: str
    signal_limit: int
    total_signals: int
    source_types: list[SourceReliabilityTypeResponse]


class MCPCapabilityCategoryResponse(BaseModel):
    category: str
    total_count: int
    percentage: float
    source_adapters: dict[str, int]
    representative_signal_ids: list[str]


class MCPCapabilitySourceAdapterResponse(BaseModel):
    source_adapter: str
    total_count: int
    percentage: float
    categories: dict[str, int]


class MCPCapabilityCoverageResponse(BaseModel):
    generated_at: str
    domain: str | None
    min_count: int
    limit_representatives: int
    source_adapter_filter: str | None
    total_signals: int
    category_percentages: dict[str, float]
    categories: list[MCPCapabilityCategoryResponse]
    undercovered_categories: list[str]
    top_source_adapters: list[MCPCapabilitySourceAdapterResponse]


class OpenAPIMCPCandidateScoreComponentResponse(BaseModel):
    name: str
    score: float
    weight: float
    explanation: str


class OpenAPIMCPCandidateResponse(BaseModel):
    provider: str
    api_name: str
    domain: str
    score: float
    rank: int
    existing_mcp_coverage: bool
    coverage_signal_ids: list[str]
    evidence_signal_ids: list[str]
    source_adapters: dict[str, int]
    score_components: list[OpenAPIMCPCandidateScoreComponentResponse]
    implementation_complexity: str
    explanation: str


class OpenAPIMCPCandidateReportResponse(BaseModel):
    generated_at: str
    domain: str | None
    min_score: float
    total_candidates: int
    candidates: list[OpenAPIMCPCandidateResponse]


class MCPQualityEvidenceReferenceResponse(BaseModel):
    kind: str
    id: str
    title: str
    source_adapter: str | None = None
    source_type: str | None = None
    url: str | None = None
    reason: str = ""


class MCPQualityScoreComponentResponse(BaseModel):
    name: str
    score: float
    weight: float
    explanation: str


class MCPQualityCertificationResponse(BaseModel):
    generated_at: str
    scope: Literal["global", "idea"]
    idea_id: str | None = None
    score: float
    grade: str
    blocked: bool
    blockers: list[str]
    warnings: list[str]
    summary: str
    score_components: list[MCPQualityScoreComponentResponse]
    evidence_references: list[MCPQualityEvidenceReferenceResponse]


class ProfileSourceRecommendationResponse(BaseModel):
    adapter: str
    action: Literal[
        "increase_weight",
        "decrease_weight",
        "enable",
        "disable",
        "investigate",
        "keep",
    ]
    severity: Literal["low", "medium", "high"]
    enabled: bool
    registered: bool
    configured: bool
    current_weight: float
    suggested_weight: float
    reasons: list[str]
    evidence: dict[str, Any]


class ProfileSourceRecommendationsResponse(BaseModel):
    generated_at: str
    profile_name: str
    domain: str
    max_age_days: int
    recommendations: list[ProfileSourceRecommendationResponse]


class ProfileSourceLintIssueResponse(BaseModel):
    severity: Literal["info", "warning", "error"]
    code: str
    profile_name: str
    profile_path: str
    path: str
    adapter: str
    message: str
    suggested_fix: str


class ProfileSourceLintReportResponse(BaseModel):
    generated_at: str
    profile_name: str
    profile_path: str
    ok: bool
    issue_counts_by_severity: dict[str, int] = Field(default_factory=dict)
    issue_counts_by_adapter: dict[str, int] = Field(default_factory=dict)
    issues: list[ProfileSourceLintIssueResponse] = Field(default_factory=list)


class AllProfileSourceLintReportResponse(BaseModel):
    generated_at: str
    ok: bool
    profile_count: int
    issue_counts_by_severity: dict[str, int] = Field(default_factory=dict)
    issue_counts_by_adapter: dict[str, int] = Field(default_factory=dict)
    profiles: list[ProfileSourceLintReportResponse] = Field(default_factory=list)


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


class EvaluationDriverResponse(BaseModel):
    dimension: str
    label: str
    score: float | None = None
    confidence: float | None = None
    weight: float
    weighted_contribution: float
    reason: str


class EvaluationDimensionNoteResponse(BaseModel):
    dimension: str
    label: str
    score: float
    confidence: float
    weight: float
    weighted_contribution: float
    sentiment: Literal["positive", "mixed", "negative"]
    note: str


class EvaluationEvidenceDiversityResponse(BaseModel):
    signal_count: int
    insight_count: int
    source_count: int
    sources: list[str]
    source_types: list[str]
    signal_roles: dict[str, int]
    avg_credibility: float
    evidence_types: dict[str, int]
    diversity_score: float
    note: str


class EvaluationMissingFieldPenaltyResponse(BaseModel):
    field: str
    label: str
    severity: Literal["high", "medium", "low"]
    penalty: float
    note: str


class EvaluationExplanationResponse(BaseModel):
    idea_id: str
    overall_score: float
    recommendation: str
    summary: str
    top_positive_drivers: list[EvaluationDriverResponse]
    top_negative_drivers: list[EvaluationDriverResponse]
    dimension_notes: list[EvaluationDimensionNoteResponse]
    evidence_diversity: EvaluationEvidenceDiversityResponse
    triangulation_hints: list[str]
    missing_field_penalties: list[EvaluationMissingFieldPenaltyResponse]
    recommended_next_evidence: list[str]


class IdeaCritiqueResponse(BaseModel):
    id: str
    buildable_unit_id: str
    pipeline_run_id: str | None = None
    stage: str
    dimensions: dict[str, float]
    reasoning: str
    rejection_tags: list[str]
    created_at: str


class ValidationExperimentResponse(BaseModel):
    id: str
    idea_id: str
    hypothesis: str
    method: str
    target_sample_size: int | None = None
    success_metric: str
    status: str
    started_at: str | None = None
    due_date: str | None = None
    completed_at: str | None = None
    result_summary: str
    evidence_urls: list[str]
    confidence_delta: float | None = None
    created_at: str
    updated_at: str


class ValidationExperimentSignalExportResponse(BaseModel):
    signal_id: str
    status: Literal["created", "existing"]


class ValidationExperimentSummaryFilterResponse(BaseModel):
    domain: str | None = None
    idea_id: str | None = None
    status: str | None = None
    overdue_only: bool = False


class ValidationExperimentSummaryBreakdownResponse(BaseModel):
    key: str
    count: int


class ValidationExperimentFollowUpActionResponse(BaseModel):
    action: str
    count: int


class ValidationExperimentSummaryResponse(BaseModel):
    filters: ValidationExperimentSummaryFilterResponse
    total_count: int
    completed_count: int
    overdue_count: int
    completion_rate: float
    average_confidence_delta: float | None = None
    average_result_score: float | None = None
    by_status: list[ValidationExperimentSummaryBreakdownResponse]
    by_domain: list[ValidationExperimentSummaryBreakdownResponse]
    by_experiment_type: list[ValidationExperimentSummaryBreakdownResponse]
    by_outcome: list[ValidationExperimentSummaryBreakdownResponse]
    top_follow_up_actions: list[ValidationExperimentFollowUpActionResponse]


class CustomerDiscoveryQuestionResponse(BaseModel):
    prompt: str
    rationale: str
    source: str


class CustomerDiscoveryScreeningSectionResponse(BaseModel):
    goal: str
    questions: list[CustomerDiscoveryQuestionResponse]


class CustomerDiscoveryInterviewSectionResponse(BaseModel):
    goal: str
    questions: list[CustomerDiscoveryQuestionResponse]
    demo_prompts: list[str]
    disconfirming_questions: list[CustomerDiscoveryQuestionResponse]


class CustomerDiscoveryFollowUpSectionResponse(BaseModel):
    goal: str
    artifacts: list[str]
    success_signals: list[str]


class CustomerDiscoverySectionsResponse(BaseModel):
    screening: CustomerDiscoveryScreeningSectionResponse
    interview: CustomerDiscoveryInterviewSectionResponse
    follow_up: CustomerDiscoveryFollowUpSectionResponse


class CustomerDiscoveryScriptResponse(BaseModel):
    idea_id: str
    idea_title: str
    interview_goals: list[str]
    target_respondent_profiles: list[str]
    screening_questions: list[CustomerDiscoveryQuestionResponse]
    discovery_questions: list[CustomerDiscoveryQuestionResponse]
    demo_prompts: list[str]
    disconfirming_questions: list[CustomerDiscoveryQuestionResponse]
    success_signals: list[str]
    follow_up_artifacts: list[str]
    sections: CustomerDiscoverySectionsResponse


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


class CalibrationScoreBucketResponse(BaseModel):
    min_score: float
    max_score: float
    sample_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    rejection_rate: float


class EvaluationCalibrationGroupResponse(BaseModel):
    domain: str
    recommendation: str
    sample_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    rejection_rate: float
    average_overall_score: float
    score_buckets: list[CalibrationScoreBucketResponse]
    high_score_sample_count: int
    high_score_rejection_count: int
    high_score_rejection_rate: float
    low_score_sample_count: int
    low_score_approval_count: int
    low_score_approval_rate: float


class EvaluationCalibrationResponse(BaseModel):
    domain: str | None = None
    min_samples: int
    limit: int
    high_score_threshold: float
    low_score_threshold: float
    total_groups: int
    total_samples: int
    groups: list[EvaluationCalibrationGroupResponse]


class RoiForecastItemResponse(BaseModel):
    rank: int
    idea_id: str
    title: str
    domain: str
    status: str
    category: str
    roi_score: float
    evaluation_score: float | None
    weighted_utility_score: float
    evidence_count: int
    evidence_score: float
    estimated_complexity: float
    complexity_score: float
    confidence: float
    recommendation: str | None
    drivers: list[str]
    warnings: list[str]


class RoiForecastResponse(BaseModel):
    generated_at: str
    profile: str | None = None
    weight_profile: str
    weights: dict[str, float]
    total_units: int
    evaluated_units: int
    results: list[RoiForecastItemResponse]


class ReviewQueueItemResponse(IdeaSummaryResponse):
    evaluation: EvaluationSummaryResponse
    latest_critique: IdeaCritiqueResponse | None = None


class ReviewThresholdRecommendationResponse(BaseModel):
    domain: str
    approve_threshold: float
    reject_threshold: float
    sample_count: int
    approved_count: int
    rejected_count: int
    sufficient_samples: bool
    fallback_used: bool
    reason: str


class ReviewThresholdsResponse(BaseModel):
    min_samples: int
    default_approve_threshold: float
    default_reject_threshold: float
    recommendations: list[ReviewThresholdRecommendationResponse]


class ReviewGateEvidenceResponse(BaseModel):
    source: str
    status: str
    score: float | None = None
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class ReviewGateResponse(BaseModel):
    schema_version: str
    kind: str
    idea_id: str
    title: str
    decision: Literal["approve", "needs_revision", "hold", "reject"]
    confidence: float
    blocking_reasons: list[str]
    warnings: list[str]
    required_remediations: list[str]
    evidence_used: list[ReviewGateEvidenceResponse]


class IdeaEvaluateBatchItemResponse(BaseModel):
    idea_id: str
    status: Literal["evaluated", "skipped", "error"]
    success: bool
    evaluation: EvaluationSummaryResponse | None = None
    error: str | None = None


class IdeaEvaluateBatchResponse(BaseModel):
    results: list[IdeaEvaluateBatchItemResponse]


class SpecReadinessBatchItemResponse(BaseModel):
    idea_id: str
    status: Literal["evaluated", "not_found", "error"]
    success: bool
    score: float | None = None
    readiness_status: Literal["pass", "fail"] | None = None
    passed: bool | None = None
    missing_sections: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    failed_check_ids: list[str] = Field(default_factory=list)
    readiness: dict[str, Any] | None = None
    error: str | None = None


class SpecReadinessBatchResponse(BaseModel):
    results: list[SpecReadinessBatchItemResponse]


class LaunchChecklistItemResponse(BaseModel):
    id: str
    task: str
    rationale: str
    evidence: str
    owner: str
    status: str
    required: bool
    section_id: str | None = None
    section_title: str | None = None


class LaunchChecklistSectionResponse(BaseModel):
    id: str
    title: str
    description: str
    items: list[LaunchChecklistItemResponse]


class LaunchChecklistResponse(BaseModel):
    schema_version: str
    kind: str
    idea_id: str
    source: dict[str, Any]
    summary: dict[str, Any]
    sections: list[LaunchChecklistSectionResponse]
    checklist_items: list[LaunchChecklistItemResponse]
    risks: list[dict[str, str]]


class AcceptanceCriterionResponse(BaseModel):
    id: str
    title: str
    statement: str
    verification: str
    trace_fields: list[str]


class AcceptanceEdgeCaseResponse(BaseModel):
    id: str
    condition: str
    expected_behavior: str


class AcceptanceEvidenceLinkResponse(BaseModel):
    type: str
    id: str
    uri: str


class AcceptanceReviewChecklistItemResponse(BaseModel):
    id: str
    item: str
    status: str
    evidence_required: bool


class AcceptanceCriteriaResponse(BaseModel):
    schema_version: str
    kind: str
    idea_id: str
    source: dict[str, Any]
    summary: dict[str, Any]
    functional_criteria: list[AcceptanceCriterionResponse]
    non_functional_criteria: list[AcceptanceCriterionResponse]
    out_of_scope: list[str]
    edge_cases: list[AcceptanceEdgeCaseResponse]
    evidence_links: list[AcceptanceEvidenceLinkResponse]
    review_checklist: list[AcceptanceReviewChecklistItemResponse]


class ExperimentCardResponse(BaseModel):
    schema_version: str
    kind: str
    idea_id: str
    source: dict[str, Any]
    idea_summary: dict[str, Any]
    riskiest_assumptions: list[dict[str, str]]
    primary_hypothesis: str
    target_participant: dict[str, Any]
    recruitment_channel_suggestions: list[dict[str, str]]
    minimum_viable_test: dict[str, Any]
    success_metrics: list[dict[str, str]]
    failure_signals: list[dict[str, str]]
    seven_day_execution_plan: list[dict[str, str]]
    instrumentation_notes: list[str]
    decision_rules: dict[str, str]


class SpecBundleArtifactsResponse(BaseModel):
    spec_preview: dict[str, Any]
    readiness: dict[str, Any]
    implementation_plan: dict[str, Any]
    launch_checklist: LaunchChecklistResponse
    acceptance_criteria: AcceptanceCriteriaResponse
    experiment_card: ExperimentCardResponse
    risk_register: dict[str, Any]
    review_gate: ReviewGateResponse
    evidence_density: EvidenceDensityResponse
    evidence_chain_summary: dict[str, Any]


class SpecBundleResponse(BaseModel):
    schema_version: str
    kind: str
    idea_id: str
    generated_at: str
    warnings: list[str]
    artifacts: SpecBundleArtifactsResponse


class IdeaProductBriefResponse(BaseModel):
    schema_version: str
    kind: str
    idea_id: str
    generated_at: str
    markdown: str
    source_ids: dict[str, list[str]]


class FeedbackBatchItemResponse(BaseModel):
    idea_id: str
    outcome: Literal["approved", "rejected", "published", "abandoned"]
    status: Literal["updated", "not_found", "invalid_transition"]
    success: bool
    error: str | None = None


class FeedbackBatchResponse(BaseModel):
    results: list[FeedbackBatchItemResponse]


class FeedbackWebhookResponse(BaseModel):
    status: Literal["ok"]
    idea_id: str
    outcome: Literal["approved", "rejected", "published", "abandoned"]
    external_run_id: str


class FeedbackLogEntryResponse(BaseModel):
    unit_id: str
    title: str
    domain: str
    category: str
    outcome: str
    reason: str
    approval_score: int | None = None
    score: float | None = None
    recommendation: str | None = None
    created_at: str


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


class IdeaScoreDistributionBucketResponse(BaseModel):
    min_score: float
    max_score: float
    count: int
    average_score: float
    by_recommendation: dict[str, int]
    by_status: dict[str, int]


class IdeaScoreDistributionResponse(BaseModel):
    bucket_size: int
    evaluated_count: int
    unevaluated_count: int
    buckets: list[IdeaScoreDistributionBucketResponse]


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


class BlastRadiusSurfaceResponse(BaseModel):
    name: str
    score: float
    level: Literal["low", "medium", "high"]
    drivers: list[str] = Field(default_factory=list)


class BlastRadiusResponse(BaseModel):
    schema_version: str
    kind: Literal["max.blast_radius"]
    idea_id: str
    title: str
    score: float
    level: Literal["low", "medium", "high", "critical"]
    affected_surfaces: list[BlastRadiusSurfaceResponse]
    drivers: list[str]
    mitigations: list[str]
    confidence: float
    evaluation_available: bool


class BatchPriorArtCheckItemResponse(BaseModel):
    idea_id: str
    status: Literal["checked", "skipped", "error"]
    prior_art_status: str | None = None
    matches: list[PriorArtMatchResponse] = Field(default_factory=list)
    error: str | None = None
    skipped: bool = False


class BatchPriorArtCheckResponse(BaseModel):
    results: list[BatchPriorArtCheckItemResponse]


class PublicationAttemptResponse(BaseModel):
    id: str
    idea_id: str
    target_type: str
    target_url: str
    status: str
    response_status: int | None = None
    error: str = ""
    created_at: str


class SlackPublishResponse(BaseModel):
    idea_id: str
    dry_run: bool
    target_url: str
    response_status: int | None = None
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse | None = None


class DiscordPublishResponse(BaseModel):
    idea_id: str
    dry_run: bool
    target_url: str
    response_status: int | None = None
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse | None = None


class TeamsPublishResponse(BaseModel):
    idea_id: str
    dry_run: bool
    target_url: str
    response_status: int | None = None
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse | None = None


class WebhookPublishResponse(BaseModel):
    idea_id: str
    dry_run: bool
    target_url: str
    status_code: int | None = None
    attempts: int
    payload_type: str
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse | None = None


class GitHubIssuePublishResponse(BaseModel):
    idea_id: str
    repository: str
    issue_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class GitLabIssuePublishResponse(BaseModel):
    idea_id: str
    project: str
    issue_id: int | None = None
    issue_iid: int | None = None
    issue_url: str | None = None
    status_code: int | None = None
    attempts: int
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class GitHubGistPublishResponse(BaseModel):
    idea_id: str
    gist_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class LinearIssuePublishResponse(BaseModel):
    idea_id: str
    team_id: str
    issue_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class AsanaTaskPublishResponse(BaseModel):
    idea_id: str
    workspace_gid: str
    task_gid: str | None = None
    task_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class ClickUpTaskPublishResponse(BaseModel):
    idea_id: str
    list_id: str
    task_id: str | None = None
    task_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class JiraIssuePublishResponse(BaseModel):
    idea_id: str
    project_key: str
    issue_key: str | None = None
    issue_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class AzureDevOpsWorkItemPublishResponse(BaseModel):
    idea_id: str
    organization: str
    project: str
    work_item_type: str
    work_item_id: str | None = None
    work_item_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class TrelloCardPublishResponse(BaseModel):
    idea_id: str
    list_id: str
    card_id: str | None = None
    card_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]
    publication_attempt: PublicationAttemptResponse


class NotionPagePublishResponse(BaseModel):
    design_brief_id: str
    page_id: str | None = None
    page_url: str | None = None
    status_code: int | None = None
    dry_run: bool
    payload: dict[str, Any]


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


class EvidenceDensityResponse(BaseModel):
    idea_id: str
    signal_count: int
    insight_count: int
    counts_by_source_adapter: dict[str, int]
    counts_by_source_type: dict[str, int]
    counts_by_signal_role: dict[str, int]
    average_credibility: float | None
    newest_evidence_timestamp: str | None
    oldest_evidence_timestamp: str | None
    missing_evidence_warnings: list[str]
    missing_insight_ids: list[str]
    missing_signal_ids: list[str]
    density_score: float


class ContextBudgetAdapterWasteResponse(BaseModel):
    source_adapter: str
    signal_count: int
    estimated_tokens: int
    reused_signal_count: int
    evidence_link_count: int
    average_reuse_count: float
    evidence_reuse_rate: float
    low_utility_signal_count: int
    low_utility_rate: float
    stale_signal_count: int
    stale_rate: float
    projected_token_savings: int
    projected_cost_savings_usd: float
    candidate_signal_ids: list[str]
    reasons: list[str]


class ContextBudgetWasteResponse(BaseModel):
    generated_at: str
    days: int
    source_adapter_filter: str | None = None
    min_reuse_count: int
    cutoff_timestamp: str
    total_signals: int
    total_estimated_tokens: int
    estimated_context_cost_usd: float
    insight_count: int
    idea_count: int
    evidence_pack_estimated_tokens: int
    evidence_pack_signal_tokens: int
    reused_signal_count: int
    evidence_link_count: int
    evidence_reuse_rate: float
    low_utility_signal_count: int
    low_utility_signal_rate: float
    stale_signal_count: int
    stale_signal_rate: float
    projected_token_savings: int
    projected_cost_savings_usd: float
    adapters: list[ContextBudgetAdapterWasteResponse]


class ContradictionSummaryResponse(BaseModel):
    group_type: Literal["claim", "source_claim", "role_claim"]
    group_key: str
    claim: str
    normalized_claim: str
    severity: Literal["high", "medium", "low"]
    involved_signal_ids: list[str]
    sources: list[str]
    sentiments: dict[str, list[str]]
    roles: dict[str, list[str]]
    suggested_review_note: str


class ContradictionReportResponse(BaseModel):
    entity_type: Literal["idea", "insight"]
    entity_id: str
    signal_count: int
    contradiction_count: int
    contradictions: list[ContradictionSummaryResponse]


class LineageGraphNodeResponse(BaseModel):
    id: str
    entity_id: str
    type: Literal["idea", "buildable_unit", "insight", "signal"]
    label: str
    evidence_links: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)


class LineageGraphEdgeResponse(BaseModel):
    id: str
    source: str
    target: str
    type: Literal["materialized_as", "inspired_by", "supported_by", "direct_evidence"]
    label: str


class LineageGraphResponse(BaseModel):
    idea_id: str
    nodes: list[LineageGraphNodeResponse]
    edges: list[LineageGraphEdgeResponse]


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


class DesignBriefValidationPlanResponse(BaseModel):
    schema_version: str
    source: dict
    design_brief: dict
    target_user_hypotheses: list[dict]
    recruiting_criteria: dict
    interview_script: dict
    smoke_test_landing_page_copy: dict
    success_metrics: list[dict]
    failure_thresholds: list[dict]
    two_week_timeline: list[dict]
    risks_to_probe: list[str]
    source_ideas: list[dict]


class DesignBriefEvidenceMatrixRowResponse(BaseModel):
    claim_area: Literal[
        "problem",
        "buyer",
        "workflow",
        "why_now",
        "validation_plan",
        "risks",
        "first_milestones",
    ]
    claim: str
    supporting_signal_ids: list[str]
    supporting_source_adapters: list[str]
    supporting_insight_ids: list[str]
    supporting_source_idea_ids: list[str]
    evidence_strength: Literal["weak", "moderate", "strong"]
    gaps: list[str]
    validation_actions: list[str]


class DesignBriefEvidenceMatrixResponse(BaseModel):
    schema_version: str
    source: dict
    design_brief: dict
    rows: list[DesignBriefEvidenceMatrixRowResponse]


class DesignBriefRiskItemResponse(BaseModel):
    id: str
    category: Literal[
        "market",
        "workflow",
        "technical",
        "data",
        "compliance",
        "dependency",
        "evidence",
    ]
    title: str
    description: str
    severity: Literal["high", "medium", "low"]
    likelihood: Literal["likely", "possible", "unlikely"]
    priority: int
    source_idea_ids: list[str]
    source_fields: list[str]
    mitigation: str
    validation_action: str


class DesignBriefRiskRegisterResponse(BaseModel):
    schema_version: str
    source: dict
    design_brief: dict
    summary: dict
    risks: list[DesignBriefRiskItemResponse]
    validation_actions: list[str]


class DesignBriefRoadmapItemResponse(BaseModel):
    id: str
    phase: Literal["discovery", "prototype", "validation", "beta", "launch"]
    title: str
    rationale: str
    owner_role: str
    dependency_ids: list[str]
    exit_criteria: str
    source_idea_ids: list[str]
    source_fields: list[str]


class DesignBriefRoadmapPhaseResponse(BaseModel):
    id: Literal["discovery", "prototype", "validation", "beta", "launch"]
    title: str
    goal: str
    items: list[DesignBriefRoadmapItemResponse]


class DesignBriefRoadmapResponse(BaseModel):
    schema_version: str
    source: dict
    design_brief: dict
    summary: dict
    phases: list[DesignBriefRoadmapPhaseResponse]
    items: list[DesignBriefRoadmapItemResponse]
    source_ideas: list[dict]


class DesignBriefPrdSectionResponse(BaseModel):
    heading: str
    content: str | list[str]
    source_fields: list[str]
    source_idea_ids: list[str]


class DesignBriefPrdResponse(BaseModel):
    schema_version: str
    source: dict
    design_brief: dict
    summary: dict
    sections: dict[str, DesignBriefPrdSectionResponse]
    source_ideas: list[dict]


class DesignBriefCompetitorClusterResponse(BaseModel):
    id: str
    name: str
    source: str
    competitor_count: int
    source_idea_ids: list[str]
    top_competitors: list[dict[str, Any]]
    overlap_score: float
    shared_terms: list[str]
    positioning_summary: str
    suggested_response: str


class DesignBriefDifferentiationAngleResponse(BaseModel):
    id: str
    title: str
    rationale: str
    source_idea_ids: list[str]
    evidence: list[str]


class DesignBriefCompetitiveLandscapeResponse(BaseModel):
    schema_version: str
    source: dict
    design_brief: dict
    status: Literal["ready", "insufficient_data"]
    summary: dict
    saturation: dict[str, Any]
    competitor_clusters: list[DesignBriefCompetitorClusterResponse]
    differentiation_angles: list[DesignBriefDifferentiationAngleResponse]
    recommended_positioning: str
    signals: dict[str, Any]
    source_ideas: list[dict]


class DesignBriefMarketSegmentResponse(BaseModel):
    name: str
    buyer: str
    user: str
    source_idea_ids: list[str]
    signal_counts: dict[str, Any]
    evaluation_score: float | None = None
    evidence_strength: Literal["weak", "moderate", "strong"]
    confidence: float
    gaps: list[str]


class DesignBriefMarketSizingResponse(BaseModel):
    schema_version: str
    source: dict
    design_brief: dict
    market_hypotheses: list[str]
    segments: list[DesignBriefMarketSegmentResponse]
    signal_counts: dict[str, Any]
    evaluation_summary: dict[str, Any]
    profile_context: dict[str, Any]
    confidence: dict[str, Any]
    gaps: list[str]
    recommendations: list[str]


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


class InsightTrendItemResponse(BaseModel):
    category: str
    domain: str
    time_horizon: str
    count: int
    average_confidence: float
    newest_insight_at: str
    top_evidence_signal_ids: list[str]


class InsightTrendResponse(BaseModel):
    days: int | None
    domain: str | None
    category: str | None
    total_insights: int
    trend_count: int
    trends: list[InsightTrendItemResponse]


class PipelineTrendWindowResponse(BaseModel):
    window_start: str
    window_end: str
    run_count: int
    completed_count: int
    failed_count: int
    signals_fetched: int
    signals_new: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    estimated_cost_usd: float
    avg_idea_score: float


class PipelineTrendResponse(BaseModel):
    days: int
    bucket: Literal["day", "week", "month"]
    window_count: int
    run_count: int
    completed_count: int
    failed_count: int
    signals_fetched: int
    signals_new: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    estimated_cost_usd: float
    avg_idea_score: float
    windows: list[PipelineTrendWindowResponse]


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
    architecture_constraints: ArchitectureConstraintsConfig
    sources: list[SourceConfig]
    evaluation: EvaluationConfig
    output_dir: str
    signal_limit: int
    ideation_mode: str
    quality_loop_enabled: bool
    draft_count: int


class ProfileValidationIssueResponse(BaseModel):
    severity: str
    code: str
    message: str
    path: str


class ProfileValidationResultResponse(BaseModel):
    name: str
    path: str
    ok: bool
    errors: list[ProfileValidationIssueResponse]
    warnings: list[ProfileValidationIssueResponse]


class ProfileValidationResponse(BaseModel):
    ok: bool
    profile: str | None = None
    results: list[ProfileValidationResultResponse]


class ProfileCoverageTermResponse(BaseModel):
    term: str
    term_type: str
    total_count: int
    adapter_counts: dict[str, int]
    enabled_adapters: list[str]
    suggested_source_adapters: list[str]


class ProfileCoverageGapsResponse(BaseModel):
    profile_name: str
    domain: str
    low_coverage_threshold: int
    enabled_adapters: list[str]
    terms: list[ProfileCoverageTermResponse]


class ProfileDriftDistributionResponse(BaseModel):
    metric: str
    sample_count: int
    expected: dict[str, float]
    observed: dict[str, float]
    counts: dict[str, int]
    missing_expected: list[str]
    unexpected: list[str]
    drift_score: float
    status: str


class EvaluationWeightMismatchResponse(BaseModel):
    sample_count: int
    expected_weights: dict[str, float]
    average_weights_used: dict[str, float]
    average_absolute_delta: float
    max_dimension_delta: float
    mismatched_evaluation_count: int
    missing_weights_count: int
    status: str
    dimension_deltas: dict[str, float]


class ProfileDriftResponse(BaseModel):
    generated_at: str
    profile_name: str
    domain: str
    signal_limit: int
    unit_limit: int
    insight_limit: int
    signals_analyzed: int
    insights_analyzed: int
    units_analyzed: int
    evaluations_analyzed: int
    category_drift: ProfileDriftDistributionResponse
    source_mix_drift: ProfileDriftDistributionResponse
    target_user_drift: ProfileDriftDistributionResponse
    evaluation_weight_mismatch: EvaluationWeightMismatchResponse
    overall_drift_score: float
    status: str
    warnings: list[str]


class ArchitectureFindingResponse(BaseModel):
    idea_id: str
    title: str
    severity: str
    code: str
    message: str
    field: str
    expected: list[str]
    observed: list[str]


class IdeaArchitectureAssessmentResponse(BaseModel):
    idea_id: str
    title: str
    category: str
    target_users: str
    domain: str
    suggested_stack: dict[str, Any]
    stack_decisions: dict[str, list[str]]
    deployment_assumptions: list[str]
    integration_assumptions: list[str]
    findings: list[ArchitectureFindingResponse]
    status: str


class ArchitectureEnforcementResponse(BaseModel):
    generated_at: str
    profile_name: str
    domain: str
    unit_limit: int
    units_analyzed: int
    categories_allowed: list[str]
    target_users_allowed: list[str]
    evaluation_weights: dict[str, float]
    constraints_configured: bool
    assessments: list[IdeaArchitectureAssessmentResponse]
    findings: list[ArchitectureFindingResponse]
    recommended_constraint_additions: list[str]
    status: str


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


class LLMBudgetStageUsageResponse(BaseModel):
    stage: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class LLMBudgetCurrentUsageResponse(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    stages: list[LLMBudgetStageUsageResponse] = Field(default_factory=list)


class LLMBudgetRunUsageResponse(BaseModel):
    id: str
    started_at: str
    finished_at: str | None = None
    status: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    stages: list[LLMBudgetStageUsageResponse] = Field(default_factory=list)
    token_usage: dict[str, object] = Field(default_factory=dict)


class LLMBudgetUsageResponse(BaseModel):
    limit: int
    run_count: int
    include_current: bool
    model: str
    total_input: int
    total_output: int
    total_tokens: int
    total_cost_usd: float
    token_budget: int
    cost_budget_usd: float
    remaining_tokens: int | None = None
    remaining_cost_usd: float | None = None
    stages: list[LLMBudgetStageUsageResponse] = Field(default_factory=list)
    current: LLMBudgetCurrentUsageResponse | None = None
    runs: list[LLMBudgetRunUsageResponse] = Field(default_factory=list)


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


class IdeaSimilarityResultResponse(BaseModel):
    idea_id: str
    title: str
    problem_summary: str
    similarity_score: float
    overlapping_evidence_ids: list[str] = Field(default_factory=list)
    overlapping_insight_ids: list[str] = Field(default_factory=list)


class PortfolioOverlapReasonResponse(BaseModel):
    type: str
    description: str
    score: float
    shared_terms: list[str] = Field(default_factory=list)
    shared_ids: list[str] = Field(default_factory=list)


class PortfolioOverlapClusterResponse(BaseModel):
    cluster_id: str
    idea_ids: list[str]
    representative_idea_ids: list[str]
    overlap_score: float
    overlap_reasons: list[PortfolioOverlapReasonResponse]
    suggested_action: Literal["merge", "differentiate", "keep separate"]


class OpportunityHeatmapBucketResponse(BaseModel):
    domain: str
    idea_category: str
    signal_count: int
    insight_count: int
    idea_count: int
    evaluated_count: int
    approved_count: int
    average_score: float | None = None
    evidence_density: float
    newest_fetched_at: str | None = None
    freshness_signal: float
    opportunity_score: float
    reasons: list[str] = Field(default_factory=list)


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


class FetchAllocationSimulationQualityResponse(BaseModel):
    total_signals: int
    insight_hit_rate: float
    idea_hit_rate: float


class FetchAllocationSimulationApprovalResponse(BaseModel):
    total_feedbacked: int
    approved: int
    rejected: int
    approval_rate: float | None = None


class FetchAllocationSimulationCircuitBreakerResponse(BaseModel):
    state: str
    failure_count: int
    retry_after_seconds: float | None = None


class FetchAllocationSimulationSourceResponse(BaseModel):
    adapter: str
    enabled: bool
    configured_weight: float
    params: dict[str, Any] = Field(default_factory=dict)
    quality: FetchAllocationSimulationQualityResponse
    approval: FetchAllocationSimulationApprovalResponse
    circuit_breaker: FetchAllocationSimulationCircuitBreakerResponse
    allocated_limit: int


class FetchAllocationSimulationResponse(BaseModel):
    profile: str
    domain: str
    total_budget: int
    allocation: dict[str, int]
    sources: list[FetchAllocationSimulationSourceResponse]


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
    max_execution_seconds: int
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
    max_execution_seconds: int | None = Field(default=None, ge=1)
    signal_limit: int | None = Field(default=None, ge=1, le=500)
    min_score: float | None = Field(default=None, ge=0.0, le=100.0)
    weight_profile: (
        Literal["default", "quick_wins", "moonshots", "ecosystem", "agent_first"] | None
    ) = None
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


class PipelineRunExportAdapterResponse(BaseModel):
    adapter: str
    status: str | None = None
    signal_count: int
    duration_ms: int
    error_message: str | None = None
    metrics: dict[str, object] = Field(default_factory=dict)


class PipelineRunExportBudgetStageResponse(BaseModel):
    stage: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class PipelineRunExportBudgetResponse(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    stages: list[PipelineRunExportBudgetStageResponse] = Field(default_factory=list)
    token_usage: dict[str, object] = Field(default_factory=dict)


class PipelineRunExportDomainResponse(BaseModel):
    domain: str
    signals_fetched: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    avg_score: float


class PipelineRunExportAdapterErrorResponse(BaseModel):
    adapter: str
    status: str | None = None
    error_message: str | None = None


class PipelineRunExportErrorsResponse(BaseModel):
    run: str | None = None
    adapters: list[PipelineRunExportAdapterErrorResponse] = Field(default_factory=list)


class PipelineRunExportRecordResponse(BaseModel):
    id: str
    started_at: str
    finished_at: str | None = None
    status: str
    profile: str | None = None
    domain: str | None = None
    config: dict[str, object] = Field(default_factory=dict)
    stage_counts: dict[str, int | float]
    adapter_stats: list[PipelineRunExportAdapterResponse] = Field(default_factory=list)
    budget: PipelineRunExportBudgetResponse
    domains: list[PipelineRunExportDomainResponse] = Field(default_factory=list)
    errors: PipelineRunExportErrorsResponse
    follow_up_recommendations: list[str] = Field(default_factory=list)


class PipelineRunExportResponse(BaseModel):
    limit: int
    run_count: int
    runs: list[PipelineRunExportRecordResponse]


class PipelineRunComparisonRunResponse(BaseModel):
    id: str
    started_at: str
    finished_at: str | None = None
    status: str


class PipelineRunMetricDeltaResponse(BaseModel):
    base: int | float
    target: int | float
    delta: int | float


class PipelineRunAdapterDeltaResponse(BaseModel):
    adapter: str
    base_status: str | None = None
    target_status: str | None = None
    status_changed: bool
    metrics: dict[str, PipelineRunMetricDeltaResponse] = Field(default_factory=dict)
    base_error_message: str | None = None
    target_error_message: str | None = None


class PipelineRunComparisonResponse(BaseModel):
    base_run: PipelineRunComparisonRunResponse
    target_run: PipelineRunComparisonRunResponse
    fetched_signals: dict[str, PipelineRunMetricDeltaResponse]
    insights: dict[str, PipelineRunMetricDeltaResponse]
    generated_ideas: dict[str, PipelineRunMetricDeltaResponse]
    approved_published_outputs: dict[str, PipelineRunMetricDeltaResponse]
    budget_usage: dict[str, PipelineRunMetricDeltaResponse]
    adapter_metrics: list[PipelineRunAdapterDeltaResponse]


class PipelineCostAnomalyStageResponse(BaseModel):
    stage: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class PipelineCostAnomalyResponse(BaseModel):
    run_id: str
    profile: str | None = None
    started_at: str
    total_tokens: int
    estimated_cost_usd: float
    baseline_cost_usd: float
    multiplier: float
    anomaly_reasons: list[str] = Field(default_factory=list)
    top_stage_metrics: list[PipelineCostAnomalyStageResponse] = Field(default_factory=list)


class PipelineCostAnomalyReportResponse(BaseModel):
    limit: int
    baseline_window: int
    min_cost_usd: float
    multiplier_threshold: float
    anomaly_count: int
    anomalies: list[PipelineCostAnomalyResponse] = Field(default_factory=list)


class PipelineReplayRunResponse(BaseModel):
    id: str
    started_at: str
    finished_at: str | None = None
    status: str


class PipelineReplayProfileResponse(BaseModel):
    name: str | None = None
    found: bool
    domain: str | None = None
    signal_limit: int | None = None
    min_score: float | None = None
    weight_profile: str | None = None
    ideation_mode: str | None = None
    quality_loop_enabled: bool | None = None
    draft_count: int | None = None


class PipelineReplayOriginalMetricsResponse(BaseModel):
    signals_fetched: int
    signals_new: int
    insights_generated: int
    ideas_generated: int
    ideas_evaluated: int
    clusters_found: int
    gaps_detected: int
    avg_idea_score: float
    fetch_allocation: dict[str, int] = Field(default_factory=dict)
    token_usage: dict[str, Any] = Field(default_factory=dict)


class PipelineReplayAdapterInputResponse(BaseModel):
    adapter: str
    enabled: bool
    weight: float | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    observed_status: str | None = None
    observed_signal_count: int
    recommended_limit: int | None = None


class PipelineReplayDryRunCommandResponse(BaseModel):
    cli: str
    api: dict[str, Any]


class PipelineReplayPlanResponse(BaseModel):
    run: PipelineReplayRunResponse
    profile: PipelineReplayProfileResponse
    original_config: dict[str, Any] = Field(default_factory=dict)
    original_metrics: PipelineReplayOriginalMetricsResponse
    adapter_inputs: list[PipelineReplayAdapterInputResponse]
    adapter_metrics: dict[str, dict[str, Any]] = Field(default_factory=dict)
    recommended_source_limits: dict[str, int] = Field(default_factory=dict)
    dry_run_commands: PipelineReplayDryRunCommandResponse
    warnings: list[str] = Field(default_factory=list)


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


class DryRunEffectiveConfigResponse(BaseModel):
    signal_limit: int
    min_score: float
    weight_profile: str
    ideation_mode: str
    quality_loop_enabled: bool
    draft_count: int


class DryRunReportResponse(BaseModel):
    profile_name: str | None = None
    domain: str | None = None
    enabled_adapters: list[str] = Field(default_factory=list)
    fetch_allocation: dict[str, int] = Field(default_factory=dict)
    effective_config: DryRunEffectiveConfigResponse | None = None
    stages: list[StageSummaryResponse]
    estimated_total_llm_calls: int
    estimated_token_budget: int
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cost_by_stage: dict[str, float] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Structured error response for MCP tools.

    Examples:
        Validation error:
        {
            "error": "budget must be at least 1",
            "code": 400,
            "details": {
                "field": "budget",
                "expected": "integer >= 1",
                "actual": "0"
            }
        }

        Resource not found:
        {
            "error": "Idea not found: bu-missing123",
            "code": 404,
            "details": {
                "resource_type": "buildable_unit",
                "resource_id": "bu-missing123"
            }
        }

        External service error:
        {
            "error": "LLM API request failed",
            "code": 502,
            "details": {
                "service": "anthropic",
                "retry_after": 5.0
            }
        }
    """

    error: str = Field(description="Human-readable error message")
    code: int | None = Field(
        default=None, description="HTTP-style error code (400, 404, 409, 429, 502)"
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional context about the error"
    )
