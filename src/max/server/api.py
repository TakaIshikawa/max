"""REST API routes for the max idea service."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from pydantic import ValidationError

from max import config
from max.analysis.blast_radius import estimate_idea_blast_radius
from max.analysis.architecture_enforcement import (
    DEFAULT_UNIT_LIMIT as DEFAULT_ARCHITECTURE_ENFORCEMENT_UNIT_LIMIT,
    build_architecture_enforcement_report,
)
from max.analysis.export import idea_export_records, render_idea_export
from max.analysis.budget_usage import build_llm_budget_usage
from max.analysis.contradictions import (
    build_idea_contradiction_report,
    build_insight_contradiction_report,
)
from max.analysis.context_budget import build_context_budget_waste_report
from max.analysis.cost_anomalies import build_cost_anomaly_report
from max.analysis.customer_discovery import generate_customer_discovery_script
from max.analysis.design_brief_competitive_landscape import (
    build_design_brief_competitive_landscape,
    render_design_brief_competitive_landscape,
)
from max.analysis.design_brief_assumption_ledger import (
    assumption_ledger_filename,
    build_design_brief_assumption_ledger,
    render_design_brief_assumption_ledger,
)
from max.analysis.design_brief_buyer_faq import (
    build_design_brief_buyer_faq,
    render_design_brief_buyer_faq,
)
from max.analysis.design_brief_compliance_checklist import (
    build_design_brief_compliance_checklist,
    compliance_checklist_filename,
    render_design_brief_compliance_checklist,
)
from max.analysis.design_brief_instrumentation_plan import (
    build_design_brief_instrumentation_plan,
    instrumentation_plan_filename,
    render_design_brief_instrumentation_plan,
)
from max.analysis.design_brief_gtm_channel_plan import (
    build_design_brief_gtm_channel_plan,
    gtm_channel_plan_filename,
    render_design_brief_gtm_channel_plan,
)
from max.analysis.design_brief_procurement_checklist import (
    build_design_brief_procurement_checklist,
    procurement_checklist_filename,
    render_design_brief_procurement_checklist,
)
from max.analysis.design_brief_bundle import (
    build_design_brief_bundle,
    render_design_brief_bundle,
)
from max.analysis.design_brief_data_room_index import (
    build_design_brief_data_room_index,
    data_room_index_filename,
    render_design_brief_data_room_index,
)
from max.analysis.design_brief_evidence_matrix import (
    build_design_brief_evidence_matrix,
    render_design_brief_evidence_matrix,
)
from max.analysis.design_brief_executive_memo import (
    build_design_brief_executive_memo,
    render_design_brief_executive_memo,
)
from max.analysis.design_brief_launch_checklist import (
    build_design_brief_launch_checklist,
    render_design_brief_launch_checklist,
)
from max.analysis.design_brief_one_pager import (
    build_design_brief_one_pager,
    render_design_brief_one_pager,
)
from max.analysis.design_brief_okrs import (
    build_design_brief_okrs,
    render_design_brief_okrs_markdown,
)
from max.analysis.design_brief_outreach_pack import (
    build_design_brief_outreach_pack,
    render_design_brief_outreach_pack,
)
from max.analysis.design_brief_pilot_rollout import (
    build_design_brief_pilot_rollout,
    render_design_brief_pilot_rollout,
)
from max.analysis.design_brief_prd import build_design_brief_prd, render_design_brief_prd
from max.analysis.design_brief_pricing_strategy import (
    build_design_brief_pricing_strategy,
    pricing_strategy_filename,
    render_design_brief_pricing_strategy,
)
from max.analysis.design_brief_raci_matrix import (
    build_design_brief_raci_matrix,
    raci_matrix_filename,
    render_design_brief_raci_matrix,
)
from max.analysis.design_brief_roadmap import build_design_brief_roadmap, render_design_brief_roadmap
from max.analysis.design_brief_retention_policy import (
    build_design_brief_retention_policy,
    render_design_brief_retention_policy,
    retention_policy_filename,
)
from max.analysis.design_brief_risk_register import (
    build_design_brief_risk_register,
    render_design_brief_risk_register,
)
from max.analysis.design_brief_sales_battlecard import (
    build_design_brief_sales_battlecard,
    render_design_brief_sales_battlecard,
)
from max.analysis.design_brief_success_metrics import (
    build_design_brief_success_metrics,
    render_design_brief_success_metrics,
    success_metrics_filename,
)
from max.analysis.design_brief_stakeholder_map import (
    build_design_brief_stakeholder_map,
    render_design_brief_stakeholder_map,
    stakeholder_map_filename,
)
from max.analysis.design_brief_support_playbook import (
    build_design_brief_support_playbook,
    render_design_brief_support_playbook,
)
from max.analysis.design_brief_technical_feasibility import (
    build_design_brief_technical_feasibility,
    render_design_brief_technical_feasibility,
    technical_feasibility_filename,
)
from max.analysis.market_sizing import (
    build_market_sizing_report,
    market_sizing_filename,
    render_market_sizing_report,
)
from max.analysis.evidence_density import build_evidence_density_report
from max.analysis.evidence_concentration import build_evidence_concentration_report
from max.analysis.evaluation_calibration import build_evaluation_calibration_report
from max.analysis.idea_similarity import find_similar_ideas
from max.analysis.idea_product_brief_export import generate_idea_product_brief
from max.analysis.mcp_capability_coverage import (
    DEFAULT_LIMIT_REPRESENTATIVES,
    DEFAULT_MIN_COUNT,
    build_mcp_capability_coverage_report,
)
from max.analysis.mcp_quality_certification import (
    MCPQualityCertificationNotFound,
    build_mcp_quality_certification_report,
)
from max.analysis.openapi_mcp_candidates import (
    DEFAULT_MIN_SCORE as DEFAULT_OPENAPI_MCP_MIN_SCORE,
    DEFAULT_SIGNAL_LIMIT as DEFAULT_OPENAPI_MCP_SIGNAL_LIMIT,
    build_openapi_mcp_candidate_report,
)
from max.analysis.opportunity_heatmap import build_opportunity_heatmap
from max.analysis.portfolio_overlap import find_portfolio_overlap_clusters
from max.analysis.prior_art import render_prior_art_report
from max.analysis.profile_drift import (
    DEFAULT_INSIGHT_LIMIT as DEFAULT_PROFILE_DRIFT_INSIGHT_LIMIT,
    DEFAULT_SIGNAL_LIMIT as DEFAULT_PROFILE_DRIFT_SIGNAL_LIMIT,
    DEFAULT_UNIT_LIMIT as DEFAULT_PROFILE_DRIFT_UNIT_LIMIT,
    build_profile_drift_report,
)
from max.analysis.profile_gap_matrix import (
    DEFAULT_MAX_RECOMMENDED_ADAPTERS as DEFAULT_PROFILE_GAP_MATRIX_MAX_RECOMMENDED_ADAPTERS,
    DEFAULT_MIN_EVALUATION_WEIGHT as DEFAULT_PROFILE_GAP_MATRIX_MIN_EVALUATION_WEIGHT,
    build_profile_gap_matrix,
    render_profile_gap_matrix_markdown,
)
from max.analysis.portfolio_synthesis import render_design_brief_markdown
from max.analysis.profile_source_recommendations import (
    DEFAULT_MAX_AGE_DAYS as DEFAULT_SOURCE_RECOMMENDATION_MAX_AGE_DAYS,
    build_profile_source_recommendations_for_profile,
)
from max.analysis.profile_source_lint import (
    build_all_profile_source_lint_report,
    build_profile_source_lint_report,
)
from max.analysis.profile_source_mix import (
    DEFAULT_CONCENTRATION_THRESHOLD,
    build_profile_source_mix_for_profile,
)
from max.analysis.run_comparison import (
    PipelineRunComparisonNotFound,
    compare_pipeline_runs,
)
from max.analysis.pipeline_run_export import (
    PipelineRunExportNotFound,
    export_pipeline_run,
    export_recent_pipeline_runs,
    render_pipeline_runs_csv,
    render_pipeline_runs_markdown,
)
from max.analysis.pipeline_replay import (
    PipelineReplayRunNotFound,
    build_pipeline_replay_plan,
)
from max.analysis.pipeline_cost_anomalies import (
    DEFAULT_BASELINE_WINDOW as DEFAULT_COST_ANOMALY_BASELINE_WINDOW,
    DEFAULT_LIMIT as DEFAULT_COST_ANOMALY_LIMIT,
    DEFAULT_MIN_COST_USD as DEFAULT_COST_ANOMALY_MIN_COST_USD,
    DEFAULT_MULTIPLIER_THRESHOLD as DEFAULT_COST_ANOMALY_MULTIPLIER_THRESHOLD,
    build_pipeline_cost_anomaly_report,
)
from max.analysis.roi_forecast import generate_roi_forecast
from max.analysis.revision_brief import build_revision_brief
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
from max.analysis.validation_signal_export import validation_experiment_signal
from max.analysis.validation_experiment_summary import build_validation_experiment_summary
from max.analysis.validation_followups import build_validation_followups
from max.publisher.discord_webhook import DiscordWebhookPublisher, DiscordWebhookPublishError
from max.publisher.asana_tasks import AsanaTaskPublisher, AsanaTaskPublishError
from max.publisher.azure_devops_work_items import (
    AzureDevOpsWorkItemPublisher,
    AzureDevOpsWorkItemPublishError,
)
from max.publisher.bitbucket_issues import BitbucketIssuePublisher, BitbucketIssuePublishError
from max.publisher.clickup_tasks import ClickUpTaskPublisher, ClickUpTaskPublishError
from max.publisher.confluence_pages import ConfluencePagePublisher, ConfluencePagePublishError
from max.publisher.github_gists import GitHubGistPublisher, GitHubGistPublishError
from max.publisher.github_issues import GitHubIssuePublisher, GitHubIssuePublishError
from max.publisher.github_milestones import (
    GitHubMilestonePublisher,
    GitHubMilestonePublishError,
)
from max.publisher.github_projects import GitHubProjectItemPublisher, GitHubProjectPublishError
from max.publisher.gitlab_issues import GitLabIssuePublisher, GitLabIssuePublishError
from max.publisher.google_sheets_rows import (
    GoogleSheetsRowPublisher,
    GoogleSheetsRowPublishError,
)
from max.publisher.hubspot_deals import HubSpotDealPublisher, HubSpotDealPublishError
from max.publisher.jira_issues import JiraIssuePublisher, JiraIssuePublishError
from max.publisher.linear_issues import LinearIssuePublisher, LinearIssuePublishError
from max.publisher.microsoft_planner_tasks import (
    MicrosoftPlannerTaskPublisher,
    MicrosoftPlannerTaskPublishError,
)
from max.publisher.monday_items import MondayItemPublisher, MondayItemPublishError
from max.publisher.notion_pages import NotionPagePublisher, NotionPagePublishError
from max.publisher.shortcut_stories import ShortcutStoryPublisher, ShortcutStoryPublishError
from max.publisher.slack_webhook import (
    SlackWebhookPublisher,
    SlackWebhookPublishError,
    redact_slack_webhook_url,
)
from max.publisher.teams_webhook import TeamsWebhookPublisher, TeamsWebhookPublishError
from max.publisher.trello_cards import TrelloCardPublisher, TrelloCardPublishError
from max.publisher.webhook import WebhookPublisher, WebhookPublishError, redact_url
from max.server.dependencies import get_store
from max.server.evidence_chain import build_evidence_chain_graph
from max.server.rate_limit import rate_limit
from max.server.schemas import (
    AdapterHealthItemResponse,
    AdapterHealthResponse,
    AdapterMetadataResponse,
    AcceptanceCriteriaResponse,
    AllProfileSourceLintReportResponse,
    AsanaTaskPublishRequest,
    AsanaTaskPublishResponse,
    ArchitectureEnforcementResponse,
    AzureDevOpsWorkItemPublishRequest,
    AzureDevOpsWorkItemPublishResponse,
    BatchPriorArtCheckItemResponse,
    BatchPriorArtCheckRequest,
    BatchPriorArtCheckResponse,
    BlastRadiusResponse,
    BlueprintSourceBriefResponse,
    ClickUpTaskPublishRequest,
    ClickUpTaskPublishResponse,
    CircuitBreakerStateResponse,
    ContradictionReportResponse,
    CostAnomalyReportResponse,
    ContextBudgetWasteResponse,
    CustomerDiscoveryScriptResponse,
    DesignBriefBundleResponse,
    DesignBriefAzureDevOpsWorkItemPublishRequest,
    DesignBriefAzureDevOpsWorkItemPublishResponse,
    DesignBriefBitbucketIssuePublishRequest,
    DesignBriefBitbucketIssuePublishResponse,
    DesignBriefClickUpTaskPublishRequest,
    DesignBriefClickUpTaskPublishResponse,
    DesignBriefConfluencePagePublishRequest,
    DesignBriefConfluencePagePublishResponse,
    DesignBriefCompetitiveLandscapeResponse,
    DesignBriefComplianceChecklistResponse,
    DesignBriefDataRoomIndexResponse,
    DesignBriefDiscordPublishResponse,
    DesignBriefEvidenceMatrixResponse,
    DesignBriefExecutiveMemoResponse,
    DesignBriefGoogleSheetsRowPublishRequest,
    DesignBriefGoogleSheetsRowPublishResponse,
    DesignBriefGitHubGistPublishRequest,
    DesignBriefGitHubGistPublishResponse,
    DesignBriefGitHubIssuePublishRequest,
    DesignBriefGitHubIssuePublishResponse,
    DesignBriefGitHubMilestonePublishRequest,
    DesignBriefGitHubMilestonePublishResponse,
    DesignBriefGtmChannelPlanResponse,
    DesignBriefHubSpotDealPublishRequest,
    DesignBriefHubSpotDealPublishResponse,
    DesignBriefAssumptionLedgerResponse,
    DesignBriefBuyerFaqResponse,
    DesignBriefInstrumentationPlanResponse,
    DesignBriefJiraIssuePublishRequest,
    DesignBriefJiraIssuePublishResponse,
    DesignBriefLaunchChecklistResponse,
    DesignBriefLinearPublishRequest,
    DesignBriefLinearPublishResponse,
    DesignBriefMarketSizingResponse,
    DesignBriefMicrosoftPlannerTaskPublishRequest,
    DesignBriefMicrosoftPlannerTaskPublishResponse,
    DesignBriefOkrsResponse,
    DesignBriefOnePagerResponse,
    DesignBriefOutreachPackResponse,
    DesignBriefPilotRolloutResponse,
    DesignBriefProcurementChecklistResponse,
    DesignBriefPrdResponse,
    DesignBriefPricingStrategyResponse,
    DesignBriefRaciMatrixResponse,
    DesignBriefRetentionPolicyResponse,
    DesignBriefRoadmapResponse,
    DesignBriefResponse,
    DesignBriefRiskRegisterResponse,
    DesignBriefSalesBattlecardResponse,
    DesignBriefSlackPublishResponse,
    DesignBriefStatusUpdate,
    DesignBriefStakeholderMapResponse,
    DesignBriefSupportPlaybookResponse,
    DesignBriefSuccessMetricsResponse,
    DesignBriefTeamsPublishResponse,
    DesignBriefTechnicalFeasibilityResponse,
    DesignBriefTrelloCardPublishRequest,
    DesignBriefTrelloCardPublishResponse,
    DesignBriefValidationPlanResponse,
    DiscordPublishRequest,
    DiscordPublishResponse,
    DomainQualityMemoryResponse,
    DomainQualityScoreResponse,
    DimensionScoreResponse,
    DryRunEffectiveConfigResponse,
    DryRunReportResponse,
    EvidenceChainResponse,
    EvidenceConcentrationResponse,
    EvidenceDensityResponse,
    ExperimentCardResponse,
    EvaluationExplanationResponse,
    EvaluationSensitivityResponse,
    EvaluationCalibrationResponse,
    EvaluationResponse,
    EvaluationSummaryResponse,
    EvaluationWeightProfileResponse,
    FeedbackBatchItemResponse,
    FeedbackBatchRequest,
    FeedbackBatchResponse,
    FeedbackCreate,
    FeedbackLogEntryResponse,
    FeedbackTrendDomainResponse,
    FeedbackTrendResponse,
    FeedbackTrendWindowResponse,
    FeedbackWebhookRequest,
    FeedbackWebhookResponse,
    FetchAllocationAdapterExplainResponse,
    FetchAllocationExplainResponse,
    FetchAllocationSimulationResponse,
    HealthResponse,
    GitHubGistPublishRequest,
    GitHubGistPublishResponse,
    GitHubIssuePublishRequest,
    GitHubIssuePublishResponse,
    GitHubProjectItemPublishRequest,
    GitHubProjectItemPublishResponse,
    GitLabIssuePublishRequest,
    GitLabIssuePublishResponse,
    GoogleSheetsRowPublishRequest,
    GoogleSheetsRowPublishResponse,
    IdeaCreate,
    IdeaCritiqueResponse,
    IdeaDetailResponse,
    IdeaEvaluateBatchItemResponse,
    IdeaEvaluateBatchRequest,
    IdeaEvaluateBatchResponse,
    IdeaMemoryResponse,
    IdeaProductBriefResponse,
    OpportunityHeatmapBucketResponse,
    IdeaSimilarityRequest,
    IdeaSimilarityResultResponse,
    IdeaScoreDistributionResponse,
    IdeaStatusSummaryResponse,
    IdeaSummaryResponse,
    SpecReadinessBatchItemResponse,
    SpecReadinessBatchRequest,
    SpecReadinessBatchResponse,
    InsightCreate,
    InsightDetailResponse,
    InsightResponse,
    InsightTrendItemResponse,
    InsightTrendResponse,
    JiraIssuePublishRequest,
    JiraIssuePublishResponse,
    LLMUsageResponse,
    LLMUsageRunResponse,
    LLMBudgetUsageResponse,
    LaunchChecklistResponse,
    LineageGraphEdgeResponse,
    LineageGraphNodeResponse,
    LineageGraphResponse,
    LinearIssuePublishRequest,
    LinearIssuePublishResponse,
    MicrosoftPlannerTaskPublishRequest,
    MicrosoftPlannerTaskPublishResponse,
    MondayItemPublishRequest,
    MondayItemPublishResponse,
    MCPSecurityFindingImportResult,
    MCPSecurityFindingsImportRequest,
    MCPSecurityFindingsImportResponse,
    PaginatedResponse,
    PaginationMeta,
    MCPCapabilityCoverageResponse,
    MCPQualityCertificationResponse,
    NotionPagePublishRequest,
    NotionPagePublishResponse,
    OpenAPIMCPCandidateReportResponse,
    PipelineAggregateResultResponse,
    PipelineCostAnomalyReportResponse,
    PipelineDryRunRequest,
    PipelinePostRunRequest,
    PipelinePostRunResponse,
    PipelineRunComparisonResponse,
    PipelineRunExportRecordResponse,
    PipelineRunExportResponse,
    PipelineReplayPlanResponse,
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
    ProfileGapMatrixResponse,
    ProfileCoverageTermResponse,
    ProfileDriftResponse,
    ProfileSourceLintReportResponse,
    ProfileSourceMixResponse,
    ProfileSourceRecommendationsResponse,
    ProfileSummaryResponse,
    ProfileValidationIssueResponse,
    ProfileValidationResponse,
    ProfileValidationResultResponse,
    ReviewQueueItemResponse,
    ReviewGateResponse,
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
    ShortcutStoryPublishRequest,
    ShortcutStoryPublishResponse,
    SlackPublishRequest,
    SlackPublishResponse,
    SourceReliabilityAdapterMetricsResponse,
    SourceReliabilityDetailResponse,
    SourceReliabilityFreshnessResponse,
    SourceReliabilityResponse,
    SpecBundleBatchItemResponse,
    SpecBundleBatchRequest,
    SpecBundleBatchResponse,
    SpecBundleResponse,
    SignalResponse,
    SimilarityRequest,
    SimilarityResult,
    StageSummaryResponse,
    StatsResponse,
    TeamsPublishRequest,
    TeamsPublishResponse,
    TrelloCardPublishRequest,
    TrelloCardPublishResponse,
    ValidationExperimentCreate,
    ValidationExperimentResponse,
    ValidationExperimentSignalExportResponse,
    ValidationExperimentSummaryResponse,
    ValidationExperimentUpdate,
    ValidationFollowUpsResponse,
    WebhookPublishRequest,
    WebhookPublishResponse,
)
from max.evaluation.explain import explain_evaluation
from max.evaluation.sensitivity import analyze_evaluation_sensitivity
from max.evaluation.weights import WEIGHT_PROFILES, get_adapted_weights, get_weights
from max.llm.client import estimate_token_cost_usd, token_counts_from_usage
from max.spec.experiment_card import generate_experiment_card
from max.spec.acceptance_criteria import generate_acceptance_criteria
from max.spec.bundle import generate_spec_bundle, render_spec_bundle_markdown
from max.spec.generator import generate_spec_preview
from max.spec.implementation_plan import generate_implementation_plan
from max.spec.launch_checklist import generate_launch_checklist, render_launch_checklist_markdown
from max.spec.readiness import evaluate_spec_readiness
from max.spec.risk_register import generate_risk_register, render_risk_register_markdown
from max.analysis.review_gate import build_review_gate_decision
from max.sources.base import snapshot_circuit_breakers
from max.sources.mcp_security_import import signal_from_mcp_security_finding
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


@router.get("/pipeline/cost-anomalies", response_model=PipelineCostAnomalyReportResponse)
def get_pipeline_cost_anomalies(
    limit: int = Query(DEFAULT_COST_ANOMALY_LIMIT, ge=1, le=500),
    baseline_window: int = Query(DEFAULT_COST_ANOMALY_BASELINE_WINDOW, ge=1, le=100),
    min_cost_usd: float = Query(DEFAULT_COST_ANOMALY_MIN_COST_USD, ge=0.0),
    multiplier_threshold: float = Query(DEFAULT_COST_ANOMALY_MULTIPLIER_THRESHOLD, gt=0.0),
    store: Store = Depends(get_store),
) -> PipelineCostAnomalyReportResponse:
    report = build_pipeline_cost_anomaly_report(
        store,
        limit=limit,
        baseline_window=baseline_window,
        min_cost_usd=min_cost_usd,
        multiplier_threshold=multiplier_threshold,
    )
    return PipelineCostAnomalyReportResponse.model_validate(report)


@router.get("/pipeline/runs", response_model=list[PipelineRunHistoryResponse])
def list_pipeline_runs(
    limit: int = 10, store: Store = Depends(get_store)
) -> list[PipelineRunHistoryResponse]:
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


@router.get("/pipeline/runs/export", response_model=None)
def export_pipeline_runs_endpoint(
    format: Literal["json", "markdown", "csv"] = Query("json"),
    limit: int = Query(10, ge=1, le=500),
    store: Store = Depends(get_store),
) -> PipelineRunExportResponse | Response:
    export = export_recent_pipeline_runs(store, limit=limit)
    if format == "markdown":
        body = render_pipeline_runs_markdown(
            export["runs"],  # type: ignore[arg-type]
            title="Pipeline Run Export",
        )
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    if format == "csv":
        body = render_pipeline_runs_csv(export["runs"])  # type: ignore[arg-type]
        return Response(content=body, media_type="text/csv; charset=utf-8")
    return PipelineRunExportResponse.model_validate(export)


@router.get("/pipeline/runs/{run_id}/export", response_model=None)
def export_pipeline_run_endpoint(
    run_id: str,
    format: Literal["json", "markdown", "csv"] = Query("json"),
    store: Store = Depends(get_store),
) -> PipelineRunExportRecordResponse | Response:
    try:
        export = export_pipeline_run(store, run_id=run_id)
    except PipelineRunExportNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Pipeline run ID not found",
                "run_id": exc.run_id,
            },
        ) from exc

    if format == "markdown":
        body = render_pipeline_runs_markdown([export], title=f"Pipeline Run {run_id} Export")
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    if format == "csv":
        body = render_pipeline_runs_csv([export])
        return Response(content=body, media_type="text/csv; charset=utf-8")
    return PipelineRunExportRecordResponse.model_validate(export)


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


@router.get("/pipeline/runs/{run_id}/replay-plan", response_model=PipelineReplayPlanResponse)
def get_pipeline_replay_plan(
    run_id: str,
    profile_name: str | None = Query(default=None, min_length=1),
    store: Store = Depends(get_store),
) -> PipelineReplayPlanResponse:
    try:
        plan = build_pipeline_replay_plan(
            store,
            run_id=run_id,
            profile_name=profile_name,
        )
    except PipelineReplayRunNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Pipeline run ID not found",
                "run_id": exc.run_id,
            },
        ) from exc
    return PipelineReplayPlanResponse.model_validate(plan)


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
                status=run.get("status") or ("completed" if run["completed_at"] else "running"),
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


@router.get("/budget/anomalies", response_model=CostAnomalyReportResponse)
def llm_cost_anomalies(
    limit: int = Query(50, ge=1, le=500),
    z_threshold: float = Query(2.0, gt=0.0),
    store: Store = Depends(get_store),
) -> CostAnomalyReportResponse:
    return CostAnomalyReportResponse.model_validate(
        build_cost_anomaly_report(store, limit=limit, z_threshold=z_threshold)
    )


@router.get("/context-budget/waste", response_model=ContextBudgetWasteResponse)
def context_budget_waste(
    days: int = Query(30, ge=1, le=3650),
    source_adapter: str | None = Query(None, min_length=1, max_length=100),
    min_reuse_count: int = Query(1, ge=0, le=100),
    store: Store = Depends(get_store),
) -> ContextBudgetWasteResponse:
    return ContextBudgetWasteResponse.model_validate(
        build_context_budget_waste_report(
            store,
            days=days,
            source_adapter=source_adapter,
            min_reuse_count=min_reuse_count,
        )
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
        fetched_at=sig.fetched_at.isoformat()
        if hasattr(sig.fetched_at, "isoformat")
        else sig.fetched_at,
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
    clean = {key: value for key, value in row.model_dump().items() if value not in (None, "")}
    missing = [
        field for field in ("title", "content", "url") if not str(clean.get(field, "")).strip()
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
        created_at=ins.created_at.isoformat()
        if hasattr(ins.created_at, "isoformat")
        else ins.created_at,
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


def _webhook_idea_payload(unit: BuildableUnit) -> dict[str, Any]:
    return {
        "id": unit.id,
        "title": unit.title,
        "one_liner": unit.one_liner,
        "category": unit.category,
        "domain": unit.domain,
        "status": unit.status,
        "problem": unit.problem,
        "solution": unit.solution,
        "target_users": unit.target_users,
        "value_proposition": unit.value_proposition,
        "workflow_context": unit.workflow_context,
        "validation_plan": unit.validation_plan,
        "evidence_rationale": unit.evidence_rationale,
        "created_at": unit.created_at.isoformat()
        if hasattr(unit.created_at, "isoformat")
        else unit.created_at,
        "updated_at": unit.updated_at.isoformat()
        if hasattr(unit.updated_at, "isoformat")
        else unit.updated_at,
    }


def _webhook_evidence_links(unit: BuildableUnit, store: Store) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for signal_id in unit.evidence_signals:
        signal = store.get_signal(signal_id)
        if signal and signal.url:
            links.append(
                {
                    "signal_id": signal.id,
                    "title": signal.title,
                    "url": signal.url,
                    "source_adapter": signal.source_adapter,
                    "source_type": signal.source_type.value
                    if hasattr(signal.source_type, "value")
                    else signal.source_type,
                }
            )
    return links


def _build_webhook_payload(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    store: Store,
    *,
    payload_template: dict[str, Any] | None,
    payload_fields: list[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "max.webhook.idea/v1",
        "payload_type": "idea",
    }
    if payload_template:
        payload.update(payload_template)

    selected = set(payload_fields)
    if "idea" in selected:
        payload["idea"] = _webhook_idea_payload(unit)
    if "evaluation" in selected:
        payload["evaluation"] = (
            _evaluation_summary_to_response(evaluation).model_dump() if evaluation else None
        )
    if "evidence_links" in selected:
        payload["evidence_links"] = _webhook_evidence_links(unit, store)
    if "spec_preview" in selected:
        payload["spec_preview"] = generate_spec_preview(unit, evaluation)
    return payload


def _spec_preview_with_evidence_links(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    store: Store,
) -> dict[str, Any]:
    payload = generate_spec_preview(unit, evaluation)
    links = [
        link["url"]
        for link in _webhook_evidence_links(unit, store)
        if isinstance(link.get("url"), str) and link["url"]
    ]
    if links:
        evidence = payload.setdefault("evidence", {})
        if isinstance(evidence, dict):
            evidence["links"] = links
    return payload


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
        ideation_mode=unit.ideation_mode.value
        if hasattr(unit.ideation_mode, "value")
        else unit.ideation_mode,
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
        created_at=unit.created_at.isoformat()
        if hasattr(unit.created_at, "isoformat")
        else unit.created_at,
        updated_at=unit.updated_at.isoformat()
        if hasattr(unit.updated_at, "isoformat")
        else unit.updated_at,
        latest_critique=_critique_to_response(latest_critique) if latest_critique else None,
        evaluation=_evaluation_to_response(evaluation) if evaluation else None,
    )


def _design_brief_to_response(brief: dict) -> DesignBriefResponse:
    return DesignBriefResponse(**brief)


def _deterministic_design_brief_markdown(brief: dict[str, Any], *, title: str) -> str:
    markdown = render_design_brief_markdown(brief, title=title)
    generated_at = brief.get("updated_at") or brief.get("created_at") or ""
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("Generated: "):
            lines[index] = f"Generated: {generated_at}"
            break
    return "\n".join(lines)


def _append_design_brief_source_ids(markdown: str, brief: dict[str, Any]) -> str:
    lead_id = str(brief.get("lead_idea_id") or "").strip()
    source_ids = [str(source_id).strip() for source_id in brief.get("source_idea_ids") or []]
    source_ids = [source_id for source_id in source_ids if source_id]
    lines = [markdown.rstrip(), "", "## Source ID Context", ""]
    lines.append(f"- Lead idea: `{lead_id}`" if lead_id else "- Lead idea: Not specified")
    lines.append(
        "- Source ideas: "
        + (", ".join(f"`{source_id}`" for source_id in source_ids) if source_ids else "None")
    )
    lines.append("")
    return "\n".join(lines)


def _design_brief_slack_payload(brief: dict[str, Any]) -> dict[str, Any]:
    title = str(brief.get("title") or brief.get("id") or "Design Brief")
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    summary = str(brief.get("merged_product_concept") or "").strip()
    brief_id = str(brief["id"])
    return {
        "source": {
            "system": "max",
            "entity_type": "design_brief",
            "id": brief_id,
            "generated_at": brief.get("updated_at") or brief.get("created_at"),
            "schema_version": "max.design_brief.slack_publish.v1",
            "links": {
                "api": f"/api/v1/design-briefs/{brief_id}",
                "markdown": f"/api/v1/design-briefs/{brief_id}.md",
                "bundle": f"/api/v1/design-briefs/{brief_id}/bundle",
                "success_metrics": f"/api/v1/design-briefs/{brief_id}/success-metrics",
            },
        },
        "design_brief": {
            "id": brief_id,
            "title": title,
            "domain": brief.get("domain", ""),
            "theme": brief.get("theme", ""),
            "readiness_score": float(brief.get("readiness_score") or 0.0),
            "design_status": brief.get("design_status", ""),
            "lead_idea_id": brief.get("lead_idea_id", ""),
            "source_idea_ids": list(brief.get("source_idea_ids") or []),
            "buyer": brief.get("buyer") or "",
            "specific_user": brief.get("specific_user") or "",
            "workflow_context": brief.get("workflow_context") or "",
            "merged_product_concept": summary,
            "why_this_now": brief.get("why_this_now", ""),
            "mvp_scope": list(brief.get("mvp_scope") or []),
            "validation_plan": brief.get("validation_plan", ""),
            "summary": summary,
            "markdown": markdown,
            "links": {
                "api": f"/api/v1/design-briefs/{brief_id}",
                "markdown": f"/api/v1/design-briefs/{brief_id}.md",
                "bundle": f"/api/v1/design-briefs/{brief_id}/bundle",
                "success_metrics": f"/api/v1/design-briefs/{brief_id}/success-metrics",
            },
        },
    }


def _design_brief_discord_payload(brief: dict[str, Any]) -> dict[str, Any]:
    title = str(brief.get("title") or brief.get("id") or "Design Brief")
    summary = str(brief.get("merged_product_concept") or "").strip()
    return {
        "source": {
            "system": "max",
            "entity_type": "design_brief",
            "id": brief["id"],
            "generated_at": brief.get("updated_at") or brief.get("created_at"),
            "schema_version": "max.design_brief.discord_publish.v1",
        },
        "design_brief": {
            "id": brief["id"],
            "title": title,
            "domain": brief.get("domain", ""),
            "theme": brief.get("theme", ""),
            "readiness_score": float(brief.get("readiness_score") or 0.0),
            "design_status": brief.get("design_status", ""),
            "lead_idea_id": brief.get("lead_idea_id", ""),
            "source_idea_ids": list(brief.get("source_idea_ids") or []),
            "merged_product_concept": summary,
            "why_this_now": brief.get("why_this_now", ""),
            "mvp_scope": list(brief.get("mvp_scope") or []),
            "validation_plan": brief.get("validation_plan", ""),
        },
    }


def _design_brief_teams_payload(brief: dict[str, Any]) -> dict[str, Any]:
    title = str(brief.get("title") or brief.get("id") or "Design Brief")
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    summary = str(brief.get("merged_product_concept") or "").strip()
    return {
        "source": {
            "system": "max",
            "entity_type": "design_brief",
            "id": brief["id"],
            "generated_at": brief.get("updated_at") or brief.get("created_at"),
            "schema_version": "max.design_brief.teams_publish.v1",
        },
        "design_brief": {
            "id": brief["id"],
            "title": title,
            "domain": brief.get("domain", ""),
            "theme": brief.get("theme", ""),
            "readiness_score": float(brief.get("readiness_score") or 0.0),
            "design_status": brief.get("design_status", ""),
            "lead_idea_id": brief.get("lead_idea_id", ""),
            "source_idea_ids": list(brief.get("source_idea_ids") or []),
            "merged_product_concept": summary,
            "why_this_now": brief.get("why_this_now", ""),
            "mvp_scope": list(brief.get("mvp_scope") or []),
            "validation_plan": brief.get("validation_plan", ""),
            "summary": summary,
            "markdown": markdown,
        },
    }


def _design_brief_trello_spec(brief: dict[str, Any]) -> dict[str, Any]:
    title = str(brief.get("title") or brief.get("id") or "Design Brief")
    source_idea_ids = [str(source_id) for source_id in brief.get("source_idea_ids") or []]
    readiness_score = float(brief.get("readiness_score") or 0.0)
    return {
        "schema_version": "max.design_brief.trello_card.v1",
        "kind": "max.design_brief",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": brief["id"],
            "lead_idea_id": brief.get("lead_idea_id"),
            "status": brief.get("design_status"),
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "readiness_score": readiness_score,
            "created_at": brief.get("created_at"),
            "updated_at": brief.get("updated_at"),
        },
        "project": {
            "title": title,
            "summary": brief.get("merged_product_concept") or brief.get("why_this_now") or "",
            "why_this_now": brief.get("why_this_now") or "",
            "buyer": brief.get("buyer") or "",
            "specific_user": brief.get("specific_user") or "",
            "workflow_context": brief.get("workflow_context") or "",
        },
        "execution": {
            "mvp_scope": list(brief.get("mvp_scope") or []),
            "first_milestones": list(brief.get("first_milestones") or []),
            "validation_plan": brief.get("validation_plan") or "",
        },
        "evidence": {
            "source_idea_ids": source_idea_ids,
            "lead_idea_id": brief.get("lead_idea_id"),
        },
        "readiness": {
            "score": readiness_score,
            "status": brief.get("design_status"),
        },
    }


def _design_brief_bitbucket_spec(brief: dict[str, Any], *, title: str) -> dict[str, Any]:
    source_idea_ids = [str(source_id) for source_id in brief.get("source_idea_ids") or []]
    readiness_score = float(brief.get("readiness_score") or 0.0)
    summary = str(
        brief.get("merged_product_concept") or brief.get("why_this_now") or ""
    ).strip()
    return {
        "schema_version": "max.design_brief.bitbucket_issue.v1",
        "kind": "max.design_brief",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": brief["id"],
            "lead_idea_id": brief.get("lead_idea_id"),
            "status": brief.get("design_status"),
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "readiness_score": readiness_score,
            "created_at": brief.get("created_at"),
            "updated_at": brief.get("updated_at"),
        },
        "project": {
            "title": title,
            "summary": summary,
            "why_this_now": brief.get("why_this_now") or "",
            "buyer": brief.get("buyer") or "",
            "specific_user": brief.get("specific_user") or "",
            "workflow_context": brief.get("workflow_context") or "",
        },
        "problem": {
            "statement": brief.get("synthesis_rationale")
            or brief.get("why_this_now")
            or "",
        },
        "solution": {"approach": brief.get("merged_product_concept") or ""},
        "execution": {
            "mvp_scope": list(brief.get("mvp_scope") or []),
            "first_milestones": list(brief.get("first_milestones") or []),
            "validation_plan": brief.get("validation_plan") or "",
            "risks": list(brief.get("risks") or []),
        },
        "evidence": {
            "rationale": brief.get("synthesis_rationale") or "",
            "insight_ids": [],
            "signal_ids": [],
            "source_idea_ids": source_idea_ids,
            "lead_idea_id": brief.get("lead_idea_id"),
        },
        "quality": {
            "quality_score": readiness_score / 10.0,
            "readiness_score": readiness_score,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": readiness_score,
            "recommendation": "publish" if readiness_score >= 80 else "review",
        },
    }


def _design_brief_evidence_links(brief: dict[str, Any], store: Store) -> list[dict[str, Any]]:
    links_by_url: dict[str, dict[str, Any]] = {}
    for idea_id in brief.get("source_idea_ids") or []:
        unit = store.get_buildable_unit(str(idea_id))
        if not unit:
            continue
        for link in _webhook_evidence_links(unit, store):
            url = link.get("url")
            if isinstance(url, str) and url:
                links_by_url[url] = link
    return list(links_by_url.values())


def _design_brief_clickup_spec(
    brief: dict[str, Any],
    *,
    title: str,
    markdown: str,
    evidence_links: list[dict[str, Any]],
) -> dict[str, Any]:
    source_idea_ids = [str(source_id) for source_id in brief.get("source_idea_ids") or []]
    readiness_score = float(brief.get("readiness_score") or 0.0)
    return {
        "schema_version": "max.design_brief.clickup_task.v1",
        "kind": "max.design_brief",
        "source": {
            "system": "max",
            "type": "design_brief",
            "idea_id": brief["id"],
            "design_brief_id": brief["id"],
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": source_idea_ids,
            "status": brief.get("design_status"),
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "readiness_score": readiness_score,
            "created_at": brief.get("created_at"),
            "updated_at": brief.get("updated_at"),
        },
        "project": {
            "title": title,
            "summary": brief.get("merged_product_concept") or brief.get("why_this_now") or "",
            "target_users": brief.get("target_users") or [],
            "specific_user": brief.get("specific_user") or "",
            "buyer": brief.get("buyer") or "",
            "workflow_context": brief.get("workflow_context") or "",
        },
        "problem": {"statement": brief.get("why_this_now") or brief.get("synthesis_rationale") or ""},
        "solution": {"approach": brief.get("merged_product_concept") or ""},
        "execution": {
            "mvp_scope": list(brief.get("mvp_scope") or []),
            "first_milestones": list(brief.get("first_milestones") or []),
            "validation_plan": brief.get("validation_plan") or "",
        },
        "evidence": {
            "rationale": brief.get("synthesis_rationale") or "",
            "source_idea_ids": source_idea_ids,
            "lead_idea_id": brief.get("lead_idea_id"),
            "links": evidence_links,
        },
        "quality": {"quality_score": readiness_score},
        "design_brief": {
            "id": brief["id"],
            "title": title,
            "summary": brief.get("merged_product_concept") or "",
            "readiness_score": readiness_score,
            "source_idea_ids": source_idea_ids,
            "evidence_links": evidence_links,
            "markdown": markdown,
        },
    }


DESIGN_BRIEF_GOOGLE_SHEETS_COLUMNS = [
    "design_brief_id",
    "title",
    "domain",
    "theme",
    "lead_idea_id",
    "source_idea_ids",
    "readiness_score",
    "evidence_count",
    "status",
    "markdown_summary",
]


def _design_brief_google_sheets_payload(
    brief: dict[str, Any],
    *,
    range: str,
    markdown_summary_url: str | None = None,
) -> dict[str, Any]:
    title = str(brief.get("title") or brief.get("id") or "Design Brief")
    source_idea_ids = [str(source_id) for source_id in brief.get("source_idea_ids") or []]
    readiness_score = float(brief.get("readiness_score") or 0.0)
    evidence_count = len(source_idea_ids)
    markdown_summary = markdown_summary_url or _deterministic_design_brief_markdown(
        brief,
        title=title,
    )
    row = [
        str(brief.get("id") or ""),
        title,
        str(brief.get("domain") or ""),
        str(brief.get("theme") or ""),
        str(brief.get("lead_idea_id") or ""),
        ", ".join(source_idea_ids),
        readiness_score,
        evidence_count,
        str(brief.get("design_status") or ""),
        markdown_summary,
    ]
    return {"range": range, "majorDimension": "ROWS", "values": [row]}


def _google_sheets_range(sheet: str | None, range_value: str | None) -> str | None:
    if not range_value:
        return f"{sheet}!A:J" if sheet else None
    if sheet and "!" not in range_value:
        return f"{sheet}!{range_value}"
    return range_value


def _google_sheets_json_response(response) -> dict[str, Any]:
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise GoogleSheetsRowPublishError(
            "Google Sheets row publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise GoogleSheetsRowPublishError(
            "Google Sheets row publish failed: response JSON was not an object",
            status_code=response.status_code,
        )
    return body


def _publish_google_sheets_payload(
    publisher: GoogleSheetsRowPublisher,
    payload: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return {
            "status_code": None,
            "updated_range": None,
            "updated_rows": None,
            "dry_run": True,
            "payload": payload,
        }

    close_client = publisher._client is None
    client = publisher._client or httpx.Client(timeout=publisher.timeout)
    try:
        response = publisher._post_with_retries(client, payload)
    finally:
        if close_client:
            client.close()

    if not 200 <= response.status_code < 300:
        raise GoogleSheetsRowPublishError(
            f"Google Sheets row publish failed with HTTP {response.status_code}: "
            f"{response.text.strip()}",
            status_code=response.status_code,
            access_token=publisher.access_token,
        )

    body = _google_sheets_json_response(response)
    updates = body.get("updates") if isinstance(body.get("updates"), dict) else {}
    updated_rows = updates.get("updatedRows")
    if isinstance(updated_rows, str) and updated_rows.strip().isdigit():
        updated_rows = int(updated_rows)
    elif not isinstance(updated_rows, int):
        updated_rows = None
    return {
        "status_code": response.status_code,
        "updated_range": updates.get("updatedRange") if updates.get("updatedRange") else None,
        "updated_rows": updated_rows,
        "dry_run": False,
        "payload": payload,
    }


def _design_brief_azure_devops_spec(
    brief: dict[str, Any],
    *,
    title: str,
    markdown: str,
) -> dict[str, Any]:
    source_idea_ids = [str(source_id) for source_id in brief.get("source_idea_ids") or []]
    readiness_score = float(brief.get("readiness_score") or 0.0)
    return {
        "schema_version": "max.design_brief.azure_devops_work_item.v1",
        "kind": "max.design_brief",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": brief["id"],
            "idea_id": brief["id"],
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": source_idea_ids,
            "status": brief.get("design_status"),
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "readiness_score": readiness_score,
            "created_at": brief.get("created_at"),
            "updated_at": brief.get("updated_at"),
        },
        "project": {
            "title": title,
            "summary": brief.get("merged_product_concept") or brief.get("why_this_now") or "",
            "target_users": brief.get("target_users") or [],
            "specific_user": brief.get("specific_user") or "",
            "buyer": brief.get("buyer") or "",
            "workflow_context": brief.get("workflow_context") or "",
        },
        "problem": {"statement": brief.get("why_this_now") or brief.get("synthesis_rationale") or ""},
        "solution": {"approach": brief.get("merged_product_concept") or ""},
        "execution": {
            "mvp_scope": list(brief.get("mvp_scope") or []),
            "first_milestones": list(brief.get("first_milestones") or []),
            "validation_plan": brief.get("validation_plan") or "",
        },
        "evidence": {
            "rationale": brief.get("synthesis_rationale") or "",
            "source_idea_ids": source_idea_ids,
            "lead_idea_id": brief.get("lead_idea_id"),
        },
        "quality": {"quality_score": readiness_score},
        "design_brief": {
            "id": brief["id"],
            "title": title,
            "markdown": markdown,
            "source_idea_ids": source_idea_ids,
        },
    }


def _markdown_preview(markdown: str, *, limit: int = 500) -> str:
    text = markdown.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _jira_credential_source(
    request: DesignBriefJiraIssuePublishRequest,
    publisher: JiraIssuePublisher,
) -> dict[str, str | None]:
    return {
        "email": "request" if request.email else ("env:JIRA_EMAIL" if publisher.email else None),
        "api_token": (
            "request" if request.api_token else ("env:JIRA_API_TOKEN" if publisher.api_token else None)
        ),
        "bearer_token": (
            "request"
            if request.bearer_token
            else ("env:JIRA_BEARER_TOKEN" if publisher.bearer_token else None)
        ),
    }


def _microsoft_planner_credential_source(
    request: DesignBriefMicrosoftPlannerTaskPublishRequest,
    publisher: MicrosoftPlannerTaskPublisher,
) -> dict[str, str | None]:
    return {
        "access_token": (
            "request"
            if request.access_token
            else ("env:MS_PLANNER_ACCESS_TOKEN" if publisher.access_token else None)
        ),
        "plan_id": "request" if request.plan_id else "env:MS_PLANNER_PLAN_ID",
        "bucket_id": "request" if request.bucket_id else "env:MS_PLANNER_BUCKET_ID",
        "assignee_user_id": (
            "request"
            if request.assignee_user_id
            else ("env:MS_PLANNER_ASSIGNEE_USER_ID" if publisher.assignee_user_id else None)
        ),
        "due_date_time": (
            "request"
            if request.due_date_time
            else ("env:MS_PLANNER_DUE_DATE_TIME" if publisher.due_date_time else None)
        ),
    }


def _redact_microsoft_planner_message(
    message: str,
    publisher: MicrosoftPlannerTaskPublisher,
) -> str:
    token = publisher.access_token
    return message.replace(token, "[redacted]") if token else message


def _confluence_credential_source(
    request: DesignBriefConfluencePagePublishRequest,
    publisher: ConfluencePagePublisher,
) -> dict[str, str | None]:
    return {
        "site_url": "request" if request.site_url else "env:CONFLUENCE_SITE_URL",
        "space_key": "request" if request.space_key else "env:CONFLUENCE_SPACE_KEY",
        "parent_page_id": (
            "request"
            if request.parent_page_id
            else ("env:CONFLUENCE_PARENT_PAGE_ID" if publisher.parent_page_id else None)
        ),
        "email": (
            "request" if request.email else ("env:CONFLUENCE_EMAIL" if publisher.email else None)
        ),
        "api_token": (
            "request"
            if request.api_token
            else ("env:CONFLUENCE_API_TOKEN" if publisher.api_token else None)
        ),
        "bearer_token": (
            "request"
            if request.bearer_token
            else ("env:CONFLUENCE_BEARER_TOKEN" if publisher.bearer_token else None)
        ),
    }


def _redact_confluence_message(message: str, publisher: ConfluencePagePublisher) -> str:
    redacted = message
    for secret in (publisher.api_token, publisher.bearer_token):
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _design_brief_confluence_packet(
    brief: dict[str, Any],
    *,
    title: str,
    include_source_ids: bool,
) -> dict[str, Any]:
    packet_brief = {
        **brief,
        "title": title,
        "source_idea_ids": list(brief.get("source_idea_ids") or [])
        if include_source_ids
        else [],
        "lead_idea_id": brief.get("lead_idea_id") if include_source_ids else None,
    }
    return {
        "schema_version": "max.design_brief.confluence_page.v1",
        "design_brief": packet_brief,
        "source_ideas": [],
    }


def _redact_azure_devops_token(message: str, token: str | None) -> str:
    if not token:
        return message
    redacted = message.replace(token, "[redacted]")
    encoded = base64.b64encode(f":{token}".encode("utf-8")).decode("ascii")
    return redacted.replace(encoded, "[redacted]")


def _redact_clickup_token(message: str, token: str | None) -> str:
    return message.replace(token, "[redacted]") if token else message


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
        architecture_constraints=profile.architecture_constraints,
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
        insight["id"]: list(insight.get("evidence", [])) for insight in chain["insights"]
    }
    insight_links = {
        insight_id: [
            signal_links[signal_id] for signal_id in signal_ids if signal_id in signal_links
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


def _has_cached_prior_art(unit: BuildableUnit, matches: list[dict]) -> bool:
    return unit.prior_art_status != "unchecked" or bool(matches)


def _persist_prior_art_result(store: Store, idea_id: str, result) -> PriorArtResponse:
    for match in result.matches:
        store.insert_prior_art_match(
            idea_id,
            {
                "source": match.source,
                "title": match.title,
                "url": match.url,
                "description": match.description,
                "relevance_score": match.relevance_score,
                "match_signals": match.match_signals,
                "search_query": match.search_query,
            },
        )

    store.update_prior_art_status(idea_id, result.status)
    refreshed = store.get_buildable_unit(idea_id)
    if refreshed is None:
        raise ValueError(f"Idea not found: {idea_id}")
    return _prior_art_response(refreshed, store.get_prior_art_matches(idea_id))


def run_prior_art_check_for_idea(
    store: Store,
    idea_id: str,
    *,
    force: bool = False,
    max_concurrency: int = 1,
    sources_override: list[str] | None = None,
) -> PriorArtResponse:
    """Check prior art for a single idea and persist the latest result."""
    from max.analysis.prior_art import PriorArtResult, check_prior_art

    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise ValueError(f"Idea not found: {idea_id}")

    matches = store.get_prior_art_matches(idea_id)
    if not force and _has_cached_prior_art(unit, matches):
        return _prior_art_response(unit, matches)

    if force:
        store.delete_prior_art_matches(idea_id)

    results = check_prior_art(
        [unit],
        dry_run=False,
        max_concurrency=max_concurrency,
        sources_override=sources_override,
    )
    result = (
        results[0]
        if results
        else PriorArtResult(
            buildable_unit_id=idea_id,
            matches=[],
            status="clear",
        )
    )

    return _persist_prior_art_result(store, idea_id, result)


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


@router.get("/profiles/source-lint", response_model=AllProfileSourceLintReportResponse)
def get_all_profile_source_lint() -> AllProfileSourceLintReportResponse:
    report = build_all_profile_source_lint_report()
    return AllProfileSourceLintReportResponse.model_validate(report.to_dict())


@router.get("/profiles/gap-matrix", response_model=ProfileGapMatrixResponse)
def get_profile_gap_matrix_endpoint(
    profile_dir: str | None = Query(default=None, min_length=1),
    min_evaluation_weight: float = Query(
        DEFAULT_PROFILE_GAP_MATRIX_MIN_EVALUATION_WEIGHT,
        ge=0.0,
        description="Evaluation dimensions below this weight are flagged as underweighted",
    ),
    max_recommended_adapters: int = Query(
        DEFAULT_PROFILE_GAP_MATRIX_MAX_RECOMMENDED_ADAPTERS,
        ge=1,
        le=100,
    ),
    max_age_days: int | None = Query(
        default=None,
        ge=1,
        description="Accepted for profile report parity; static gap matrix does not filter by age",
    ),
    min_signals: int | None = Query(
        default=None,
        ge=1,
        description="Accepted for profile report parity; static gap matrix does not count signals",
    ),
    store: Store = Depends(get_store),
) -> ProfileGapMatrixResponse:
    del max_age_days, min_signals
    try:
        matrix = build_profile_gap_matrix(
            store,
            profiles_dir=profile_dir,
            min_evaluation_weight=min_evaluation_weight,
            max_recommended_adapters=max_recommended_adapters,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProfileGapMatrixResponse.model_validate(matrix.to_dict())


@router.get("/profiles/gap-matrix.md", response_model=None)
def get_profile_gap_matrix_markdown_endpoint(
    profile_dir: str | None = Query(default=None, min_length=1),
    min_evaluation_weight: float = Query(
        DEFAULT_PROFILE_GAP_MATRIX_MIN_EVALUATION_WEIGHT,
        ge=0.0,
        description="Evaluation dimensions below this weight are flagged as underweighted",
    ),
    max_recommended_adapters: int = Query(
        DEFAULT_PROFILE_GAP_MATRIX_MAX_RECOMMENDED_ADAPTERS,
        ge=1,
        le=100,
    ),
    max_age_days: int | None = Query(
        default=None,
        ge=1,
        description="Accepted for profile report parity; static gap matrix does not filter by age",
    ),
    min_signals: int | None = Query(
        default=None,
        ge=1,
        description="Accepted for profile report parity; static gap matrix does not count signals",
    ),
    store: Store = Depends(get_store),
) -> Response:
    del max_age_days, min_signals
    try:
        matrix = build_profile_gap_matrix(
            store,
            profiles_dir=profile_dir,
            min_evaluation_weight=min_evaluation_weight,
            max_recommended_adapters=max_recommended_adapters,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=render_profile_gap_matrix_markdown(matrix),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="profile-gap-matrix.md"'},
    )


@router.get("/profiles/{profile_name}", response_model=ProfileDetailResponse)
def get_pipeline_profile(profile_name: str) -> ProfileDetailResponse:
    return _profile_detail_to_response(_load_profile_or_404(profile_name))


@router.get("/profiles/{profile_name}/validate", response_model=ProfileValidationResponse)
def validate_pipeline_profile(profile_name: str) -> ProfileValidationResponse:
    return validate_pipeline_profiles(profile=profile_name)


@router.get("/profiles/{profile_name}/source-lint", response_model=ProfileSourceLintReportResponse)
def get_profile_source_lint(profile_name: str) -> ProfileSourceLintReportResponse:
    try:
        report = build_profile_source_lint_report(profile_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")
    return ProfileSourceLintReportResponse.model_validate(report.to_dict())


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


@router.get(
    "/profiles/{profile_name}/architecture-enforcement",
    response_model=ArchitectureEnforcementResponse,
)
def get_profile_architecture_enforcement(
    profile_name: str,
    unit_limit: int = Query(DEFAULT_ARCHITECTURE_ENFORCEMENT_UNIT_LIMIT, ge=1, le=10_000),
    store: Store = Depends(get_store),
) -> ArchitectureEnforcementResponse:
    profile = _load_profile_or_404(profile_name)
    report = build_architecture_enforcement_report(
        profile,
        store,
        unit_limit=unit_limit,
    )
    return ArchitectureEnforcementResponse.model_validate(report.to_dict())


@router.get(
    "/profiles/{profile_name}/source-recommendations",
    response_model=ProfileSourceRecommendationsResponse,
)
def get_profile_source_recommendations(
    profile_name: str,
    max_age_days: int = Query(DEFAULT_SOURCE_RECOMMENDATION_MAX_AGE_DAYS, ge=1),
    store: Store = Depends(get_store),
) -> ProfileSourceRecommendationsResponse:
    profile = _load_profile_or_404(profile_name)
    report = build_profile_source_recommendations_for_profile(
        profile,
        store,
        max_age_days=max_age_days,
    )
    return ProfileSourceRecommendationsResponse.model_validate(report.to_dict())


@router.get(
    "/profiles/{profile_name}/source-mix",
    response_model=ProfileSourceMixResponse,
)
def get_profile_source_mix(
    profile_name: str,
    concentration_threshold: float = Query(
        DEFAULT_CONCENTRATION_THRESHOLD,
        gt=0.0,
        le=1.0,
        description="Flag source groups above this adapter, weight, or configured-limit share",
    ),
) -> ProfileSourceMixResponse:
    profile = _load_profile_or_404(profile_name)
    report = build_profile_source_mix_for_profile(
        profile,
        concentration_threshold=concentration_threshold,
    )
    return ProfileSourceMixResponse.model_validate(report.to_dict())


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


@router.get("/source-reliability/{adapter_name}", response_model=SourceReliabilityDetailResponse)
def get_source_reliability_detail(
    adapter_name: str,
    signal_limit: int = Query(DEFAULT_SIGNAL_LIMIT, ge=1, le=10_000),
    time_window: str | None = Query(default=None),
    min_signal_count: int = Query(1, ge=1, le=10_000),
    store: Store = Depends(get_store),
) -> SourceReliabilityDetailResponse:
    try:
        fetched_since = _parse_source_reliability_time_window(time_window)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    registered_adapters = set(list_adapters())
    observed_signals = [
        signal
        for signal in store.get_signals(limit=10_000)
        if signal.source_adapter == adapter_name
    ]
    if adapter_name not in registered_adapters and not observed_signals:
        raise HTTPException(status_code=404, detail=f"Source adapter not found: {adapter_name}")

    report = build_source_reliability_report(
        store,
        signal_limit=signal_limit,
        source_adapters={adapter_name},
        fetched_since=fetched_since,
        min_signal_count=min_signal_count,
    )
    report_payload = report.to_dict()
    source_types = report_payload["source_types"]
    approval_stats = store.get_adapter_approval_stats().get(adapter_name)
    freshness_signals = _filter_reliability_detail_signals(
        observed_signals,
        fetched_since=fetched_since,
        limit=signal_limit,
    )

    payload = {
        "generated_at": report_payload["generated_at"],
        "adapter_name": adapter_name,
        "registered": adapter_name in registered_adapters,
        "signal_limit": report_payload["signal_limit"],
        "time_window": time_window,
        "fetched_since": fetched_since.isoformat() if fetched_since else None,
        "min_signal_count": min_signal_count,
        "total_signals": report_payload["total_signals"],
        "recent_signal_count": len(freshness_signals),
        "source_types": source_types,
        "metrics": _source_reliability_detail_metrics(source_types),
        "approval_stats": approval_stats,
        "freshness": _source_reliability_freshness(freshness_signals),
        "recommendations": _source_reliability_recommendations(
            adapter_name=adapter_name,
            source_types=source_types,
            total_signals=report_payload["total_signals"],
        ),
    }
    return SourceReliabilityDetailResponse.model_validate(payload)


def _parse_source_reliability_time_window(time_window: str | None) -> datetime | None:
    if time_window is None or time_window.strip().lower() in ("", "all"):
        return None

    value = time_window.strip().lower()
    unit = value[-1]
    amount_text = value[:-1]
    if unit.isdigit():
        unit = "d"
        amount_text = value

    try:
        amount = int(amount_text)
    except ValueError as e:
        raise ValueError("time_window must be a duration like '24h', '7d', or '4w'") from e
    if amount < 1:
        raise ValueError("time_window must be at least 1 unit")

    if unit == "s":
        delta = timedelta(seconds=amount)
    elif unit == "m":
        delta = timedelta(minutes=amount)
    elif unit == "h":
        delta = timedelta(hours=amount)
    elif unit == "d":
        delta = timedelta(days=amount)
    elif unit == "w":
        delta = timedelta(weeks=amount)
    else:
        raise ValueError("time_window must use one of: s, m, h, d, w")
    return datetime.now(timezone.utc) - delta


def _filter_reliability_detail_signals(
    signals: list[Any],
    *,
    fetched_since: datetime | None,
    limit: int,
) -> list[Any]:
    filtered = signals
    if fetched_since is not None:
        filtered = [
            signal
            for signal in filtered
            if _normalize_reliability_datetime(signal.fetched_at) >= fetched_since
        ]
    return sorted(
        filtered,
        key=lambda signal: _normalize_reliability_datetime(signal.fetched_at),
        reverse=True,
    )[:limit]


def _source_reliability_detail_metrics(
    source_types: list[dict[str, Any]],
) -> SourceReliabilityAdapterMetricsResponse:
    total = sum(int(row["total_signals"]) for row in source_types)

    def weighted(field: str) -> float:
        if total == 0:
            return 0.0
        value = sum(float(row[field]) * int(row["total_signals"]) for row in source_types) / total
        return round(max(0.0, min(1.0, value)), 4)

    feedback_total = 0
    feedback_weighted = 0.0
    for row in source_types:
        rate = row.get("feedback_approval_rate")
        if rate is None:
            continue
        count = int(row["total_signals"])
        feedback_total += count
        feedback_weighted += float(rate) * count

    return SourceReliabilityAdapterMetricsResponse(
        adapter_health_score=weighted("adapter_health_score"),
        signal_usefulness_score=weighted("signal_usefulness_score"),
        corroboration_rate=weighted("corroboration_rate"),
        downstream_idea_conversion_rate=weighted("downstream_idea_conversion_rate"),
        feedback_approval_rate=(
            round(feedback_weighted / feedback_total, 4) if feedback_total else None
        ),
        reliability_score=weighted("reliability_score"),
    )


def _source_reliability_freshness(signals: list[Any]) -> SourceReliabilityFreshnessResponse:
    if not signals:
        return SourceReliabilityFreshnessResponse(signal_count=0)

    fetched_dates = [_normalize_reliability_datetime(signal.fetched_at) for signal in signals]
    newest = max(fetched_dates)
    oldest = min(fetched_dates)
    now = datetime.now(timezone.utc)
    return SourceReliabilityFreshnessResponse(
        signal_count=len(signals),
        newest_fetched_at=newest.isoformat(),
        oldest_fetched_at=oldest.isoformat(),
        newest_age_days=round((now - newest).total_seconds() / 86_400, 4),
        oldest_age_days=round((now - oldest).total_seconds() / 86_400, 4),
    )


def _source_reliability_recommendations(
    *,
    adapter_name: str,
    source_types: list[dict[str, Any]],
    total_signals: int,
) -> list[str]:
    recommendations: list[str] = []
    for row in source_types:
        recommendations.extend(str(reason) for reason in row.get("reasons", []))
    if not recommendations:
        recommendations.append(
            f"No recent signals matched adapter {adapter_name}; "
            "verify the adapter is scheduled and fetching."
        )
    if total_signals == 0:
        return recommendations
    if all(float(row["signal_usefulness_score"]) == 0.0 for row in source_types):
        recommendations.append(
            "No recent signals are cited by synthesized insights; inspect signal quality."
        )
    if all(float(row["downstream_idea_conversion_rate"]) == 0.0 for row in source_types):
        recommendations.append(
            "No recent signals are used as buildable idea evidence; review source coverage."
        )
    return list(dict.fromkeys(recommendations))


def _normalize_reliability_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/mcp/capability-coverage", response_model=MCPCapabilityCoverageResponse)
def get_mcp_capability_coverage(
    domain: str | None = Query(default=None, min_length=1),
    min_count: int = Query(DEFAULT_MIN_COUNT, ge=1, le=10_000),
    limit_representatives: int = Query(DEFAULT_LIMIT_REPRESENTATIVES, ge=0, le=100),
    source_adapter: str | None = Query(default=None, min_length=1),
    store: Store = Depends(get_store),
) -> MCPCapabilityCoverageResponse:
    report = build_mcp_capability_coverage_report(
        store,
        domain=domain,
        min_count=min_count,
        limit_representatives=limit_representatives,
        source_adapter=source_adapter,
    )
    return MCPCapabilityCoverageResponse.model_validate(report.to_dict())


@router.get("/mcp/openapi-candidates", response_model=OpenAPIMCPCandidateReportResponse)
def get_openapi_mcp_candidates(
    domain: str | None = Query(default=None, min_length=1),
    min_score: float = Query(DEFAULT_OPENAPI_MCP_MIN_SCORE, ge=0.0, le=100.0),
    signal_limit: int = Query(DEFAULT_OPENAPI_MCP_SIGNAL_LIMIT, ge=1, le=10_000),
    store: Store = Depends(get_store),
) -> OpenAPIMCPCandidateReportResponse:
    report = build_openapi_mcp_candidate_report(
        store,
        domain=domain,
        min_score=min_score,
        signal_limit=signal_limit,
    )
    return OpenAPIMCPCandidateReportResponse.model_validate(report.to_dict())


@router.get("/mcp/quality-certification", response_model=MCPQualityCertificationResponse)
def get_mcp_quality_certification(
    store: Store = Depends(get_store),
) -> MCPQualityCertificationResponse:
    report = build_mcp_quality_certification_report(store)
    return MCPQualityCertificationResponse.model_validate(report.to_dict())


@router.get(
    "/ideas/{idea_id}/mcp-quality-certification",
    response_model=MCPQualityCertificationResponse,
)
def get_idea_mcp_quality_certification(
    idea_id: str,
    store: Store = Depends(get_store),
) -> MCPQualityCertificationResponse:
    try:
        report = build_mcp_quality_certification_report(store, idea_id=idea_id)
    except MCPQualityCertificationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MCPQualityCertificationResponse.model_validate(report.to_dict())


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


@router.post("/security/mcp-findings/import", response_model=MCPSecurityFindingsImportResponse)
def import_mcp_security_findings(
    body: MCPSecurityFindingsImportRequest,
    store: Store = Depends(get_store),
) -> MCPSecurityFindingsImportResponse:
    results: list[MCPSecurityFindingImportResult] = []
    inserted_count = 0
    duplicate_count = 0
    error_count = 0

    for index, finding in enumerate(body.findings):
        try:
            signal = signal_from_mcp_security_finding(finding)
            result = store.insert_signal_result(signal)
        except (TypeError, ValueError, ValidationError) as e:
            error_count += 1
            results.append(MCPSecurityFindingImportResult(index=index, error=str(e)))
            continue

        if result.created:
            inserted_count += 1
            results.append(MCPSecurityFindingImportResult(index=index, signal_id=result.signal.id))
        else:
            duplicate_count += 1
            results.append(
                MCPSecurityFindingImportResult(index=index, duplicate_id=result.signal.id)
            )

    return MCPSecurityFindingsImportResponse(
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


@router.post("/insights/{insight_id}/restore", response_model=InsightResponse)
def restore_insight(insight_id: str, store: Store = Depends(get_store)) -> InsightResponse:
    if not store.restore_insight(insight_id):
        raise HTTPException(status_code=404, detail=f"Insight not found: {insight_id}")

    insight = store.get_insight(insight_id)
    if not insight:
        raise HTTPException(status_code=404, detail=f"Insight not found: {insight_id}")
    return _insight_to_response(insight)


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
            _critique_to_response(row["latest_critique"]) if row["latest_critique"] else None
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
            ReviewThresholdRecommendationResponse(**item.__dict__) for item in recommendations
        ],
    )


@router.get("/exports/ideas", response_class=Response)
def export_ideas(
    fmt: Literal["jsonl", "csv"] = "jsonl",
    format_: Literal["jsonl", "csv"] | None = Query(default=None, alias="format"),
    status: str | None = None,
    domain: str | None = None,
    min_score: float | None = Query(default=None, ge=0.0, le=100.0),
    include_archived: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    store: Store = Depends(get_store),
) -> Response:
    """Export filtered idea summaries as JSON Lines or CSV."""
    export_format = format_ or fmt
    units = store.get_buildable_units(limit=limit, status=status, domain=domain)
    if not include_archived and status != "archived":
        units = [unit for unit in units if unit.status != "archived"]

    records = idea_export_records(
        units,
        get_evaluation=store.get_evaluation,
        get_latest_feedback=store.get_latest_feedback,
        min_score=min_score,
    )
    media_type = "text/csv" if export_format == "csv" else "text/plain"
    filename = f"ideas-export.{export_format}"
    return Response(
        content=render_idea_export(records, fmt=export_format),
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


@router.get("/portfolio/evidence-concentration", response_model=EvidenceConcentrationResponse)
def get_portfolio_evidence_concentration(
    limit: int = Query(default=20, ge=1, le=100),
    store: Store = Depends(get_store),
) -> EvidenceConcentrationResponse:
    try:
        report = build_evidence_concentration_report(store, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EvidenceConcentrationResponse.model_validate(report)


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


@router.post(
    "/ideas/prior-art/batch",
    response_model=BatchPriorArtCheckResponse,
)
def check_ideas_prior_art_batch(
    body: BatchPriorArtCheckRequest,
    store: Store = Depends(get_store),
) -> BatchPriorArtCheckResponse:
    from max.analysis.prior_art import PriorArtResult, check_prior_art

    results: list[BatchPriorArtCheckItemResponse | None] = [None] * len(body.idea_ids)
    units_to_check: list[BuildableUnit] = []
    pending_indexes: list[int] = []

    for index, idea_id in enumerate(body.idea_ids):
        try:
            unit = store.get_buildable_unit(idea_id)
            if not unit:
                results[index] = BatchPriorArtCheckItemResponse(
                    idea_id=idea_id,
                    status="error",
                    error=f"Idea not found: {idea_id}",
                )
                continue

            matches = store.get_prior_art_matches(idea_id)
            if not body.force and _has_cached_prior_art(unit, matches):
                cached = _prior_art_response(unit, matches)
                results[index] = BatchPriorArtCheckItemResponse(
                    idea_id=idea_id,
                    status="skipped",
                    prior_art_status=cached.prior_art_status,
                    matches=cached.matches,
                    skipped=True,
                )
                continue

            if body.force:
                store.delete_prior_art_matches(idea_id)
            units_to_check.append(unit)
            pending_indexes.append(index)
        except Exception as exc:
            results[index] = BatchPriorArtCheckItemResponse(
                idea_id=idea_id,
                status="error",
                error=str(exc),
            )

    if units_to_check:
        try:
            checked_results = check_prior_art(
                units_to_check,
                dry_run=False,
                max_concurrency=body.max_concurrency,
                sources_override=list(body.sources) if body.sources is not None else None,
            )
            results_by_id = {result.buildable_unit_id: result for result in checked_results}
            for index, unit in zip(pending_indexes, units_to_check, strict=True):
                result = results_by_id.get(unit.id) or PriorArtResult(
                    buildable_unit_id=unit.id,
                    matches=[],
                    status="clear",
                )
                checked = _persist_prior_art_result(store, unit.id, result)
                results[index] = BatchPriorArtCheckItemResponse(
                    idea_id=unit.id,
                    status="checked",
                    prior_art_status=checked.prior_art_status,
                    matches=checked.matches,
                    skipped=False,
                )
        except Exception as exc:
            for index, unit in zip(pending_indexes, units_to_check, strict=True):
                results[index] = BatchPriorArtCheckItemResponse(
                    idea_id=unit.id,
                    status="error",
                    error=str(exc),
                )

    return BatchPriorArtCheckResponse(results=[result for result in results if result is not None])


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


@router.post("/ideas/{idea_id}/restore", response_model=IdeaDetailResponse)
def restore_idea(idea_id: str, store: Store = Depends(get_store)) -> IdeaDetailResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    store.restore_archived_idea(idea_id)

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
    signal_ids = list(
        dict.fromkeys(
            [
                *unit.evidence_signals,
                *(signal_id for insight in insights for signal_id in insight.evidence),
            ]
        )
    )
    signals = [signal for signal_id in signal_ids if (signal := store.get_signal(signal_id))]
    return EvaluationExplanationResponse.model_validate(
        explain_evaluation(
            unit,
            evaluation,
            insights=insights,
            signals=signals,
        )
    )


@router.get(
    "/ideas/{idea_id}/evaluation-sensitivity",
    response_model=EvaluationSensitivityResponse,
)
def get_idea_evaluation_sensitivity(
    idea_id: str,
    store: Store = Depends(get_store),
) -> EvaluationSensitivityResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    payload = analyze_evaluation_sensitivity(evaluation)
    return EvaluationSensitivityResponse.model_validate({"idea_id": idea_id, **payload})


@router.get("/ideas/{idea_id}/prior-art", response_model=PriorArtResponse)
def get_idea_prior_art(idea_id: str, store: Store = Depends(get_store)) -> PriorArtResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return _prior_art_response(unit, store.get_prior_art_matches(idea_id))


@router.get("/ideas/{idea_id}/prior-art.md", response_model=None)
def get_idea_prior_art_markdown(idea_id: str, store: Store = Depends(get_store)) -> Response:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    matches = store.get_prior_art_matches(idea_id)
    filename = f"{_download_filename_part(idea_id)}-prior-art.md"
    return Response(
        content=render_prior_art_report(unit, matches),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/ideas/{idea_id}/validation-experiments",
    response_model=ValidationExperimentResponse,
    status_code=201,
)
def create_validation_experiment(
    idea_id: str,
    body: ValidationExperimentCreate,
    store: Store = Depends(get_store),
) -> ValidationExperimentResponse:
    experiment = store.create_validation_experiment(
        idea_id,
        hypothesis=body.hypothesis,
        method=body.method,
        target_sample_size=body.target_sample_size,
        success_metric=body.success_metric,
        status=body.status,
        started_at=body.started_at,
        due_date=body.due_date,
        completed_at=body.completed_at,
        result_summary=body.result_summary,
        evidence_urls=body.evidence_urls,
        confidence_delta=body.confidence_delta,
    )
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return ValidationExperimentResponse(**experiment)


@router.get(
    "/ideas/{idea_id}/validation-experiments",
    response_model=list[ValidationExperimentResponse],
)
def list_validation_experiments(
    idea_id: str,
    store: Store = Depends(get_store),
) -> list[ValidationExperimentResponse]:
    experiments = store.list_validation_experiments(idea_id)
    if experiments is None:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return [ValidationExperimentResponse(**experiment) for experiment in experiments]


@router.get(
    "/ideas/{idea_id}/validation-followups",
    response_model=ValidationFollowUpsResponse,
)
def get_validation_followups(
    idea_id: str,
    store: Store = Depends(get_store),
) -> ValidationFollowUpsResponse:
    followups = build_validation_followups(store, idea_id)
    if followups is None:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return ValidationFollowUpsResponse.model_validate(followups)


@router.get(
    "/ideas/{idea_id}/customer-discovery-script",
    response_model=CustomerDiscoveryScriptResponse,
)
def get_customer_discovery_script(
    idea_id: str,
    store: Store = Depends(get_store),
) -> CustomerDiscoveryScriptResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    experiments = store.list_validation_experiments(idea_id) or []
    return CustomerDiscoveryScriptResponse.model_validate(
        generate_customer_discovery_script(
            unit,
            evaluation=store.get_evaluation(idea_id),
            evidence_density=build_evidence_density_report(unit, store),
            validation_experiments=experiments,
        )
    )


@router.get(
    "/validation-experiments/summary",
    response_model=ValidationExperimentSummaryResponse,
)
def get_validation_experiment_summary(
    domain: str | None = None,
    idea_id: str | None = None,
    status: str | None = None,
    overdue_only: bool = False,
    store: Store = Depends(get_store),
) -> ValidationExperimentSummaryResponse:
    return ValidationExperimentSummaryResponse.model_validate(
        build_validation_experiment_summary(
            store,
            domain=domain,
            idea_id=idea_id,
            status=status,
            overdue_only=overdue_only,
        )
    )


@router.patch(
    "/validation-experiments/{experiment_id}",
    response_model=ValidationExperimentResponse,
)
def update_validation_experiment(
    experiment_id: str,
    body: ValidationExperimentUpdate,
    store: Store = Depends(get_store),
) -> ValidationExperimentResponse:
    experiment = store.update_validation_experiment(
        experiment_id,
        **body.model_dump(exclude_unset=True),
    )
    if experiment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Validation experiment not found: {experiment_id}",
        )
    return ValidationExperimentResponse(**experiment)


@router.post(
    "/validation-experiments/{experiment_id}/export-signal",
    response_model=ValidationExperimentSignalExportResponse,
    status_code=201,
)
def export_validation_experiment_signal(
    experiment_id: str,
    response: Response,
    store: Store = Depends(get_store),
) -> ValidationExperimentSignalExportResponse:
    experiment = store.get_validation_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Validation experiment not found: {experiment_id}",
        )

    existing = store.get_signal_by_validation_experiment_id(experiment_id)
    if existing is not None:
        response.status_code = 200
        return ValidationExperimentSignalExportResponse(signal_id=existing.id, status="existing")

    if experiment["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail="Only completed validation experiments can be exported as signals.",
        )

    idea = store.get_buildable_unit(experiment["idea_id"])
    if idea is None:
        raise HTTPException(status_code=404, detail=f"Idea not found: {experiment['idea_id']}")

    signal = store.insert_signal(validation_experiment_signal(experiment, idea))
    return ValidationExperimentSignalExportResponse(signal_id=signal.id, status="created")


@router.get("/ideas/{idea_id}/revision-brief")
def get_idea_revision_brief(idea_id: str, store: Store = Depends(get_store)) -> dict:
    try:
        return build_revision_brief(store, idea_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")


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


@router.post("/ideas/{idea_id}/publish/slack", response_model=SlackPublishResponse)
def publish_idea_to_slack(
    idea_id: str,
    request: SlackPublishRequest,
    store: Store = Depends(get_store),
) -> SlackPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    try:
        publisher = SlackWebhookPublisher.from_env(
            webhook_url=request.webhook_url,
            channel=request.channel,
            timeout=request.timeout,
        )
    except SlackWebhookPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, store.get_evaluation(idea_id))
    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except SlackWebhookPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="slack_webhook",
            target_url=publisher.redacted_url,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    publication_attempt = None
    if not result.dry_run:
        publication_attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="slack_webhook",
            target_url=result.url,
            status="success",
            response_status=result.status_code,
        )

    return SlackPublishResponse(
        idea_id=idea_id,
        dry_run=result.dry_run,
        target_url=result.url,
        response_status=result.status_code,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**publication_attempt)
        if publication_attempt
        else None,
    )


@router.post("/ideas/{idea_id}/publish/discord", response_model=DiscordPublishResponse)
def publish_idea_to_discord(
    idea_id: str,
    request: DiscordPublishRequest,
    store: Store = Depends(get_store),
) -> DiscordPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    try:
        publisher = DiscordWebhookPublisher.from_env(
            webhook_url=request.webhook_url,
            username=request.username,
            timeout=request.timeout,
        )
    except DiscordWebhookPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, store.get_evaluation(idea_id))
    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except DiscordWebhookPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="discord_webhook",
            target_url=publisher.redacted_url,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    publication_attempt = None
    if not result.dry_run:
        publication_attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="discord_webhook",
            target_url=result.url,
            status="success",
            response_status=result.status_code,
        )

    return DiscordPublishResponse(
        idea_id=idea_id,
        dry_run=result.dry_run,
        target_url=result.url,
        response_status=result.status_code,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**publication_attempt)
        if publication_attempt
        else None,
    )


@router.post("/ideas/{idea_id}/publish/teams", response_model=TeamsPublishResponse)
def publish_idea_to_teams(
    idea_id: str,
    request: TeamsPublishRequest,
    store: Store = Depends(get_store),
) -> TeamsPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    try:
        publisher = TeamsWebhookPublisher.from_env(
            webhook_url=request.webhook_url,
            timeout=request.timeout,
        )
    except TeamsWebhookPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, store.get_evaluation(idea_id))
    try:
        result = publisher.publish(
            payload,
            dry_run=request.dry_run,
            title=request.title,
            include_evidence=request.include_evidence,
        )
    except TeamsWebhookPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="teams_webhook",
            target_url=publisher.redacted_url,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    publication_attempt = None
    if not result.dry_run:
        publication_attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="teams_webhook",
            target_url=result.url,
            status="success",
            response_status=result.status_code,
        )

    return TeamsPublishResponse(
        idea_id=idea_id,
        dry_run=result.dry_run,
        target_url=result.url,
        response_status=result.status_code,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**publication_attempt)
        if publication_attempt
        else None,
    )


@router.post("/ideas/{idea_id}/publish/webhook", response_model=WebhookPublishResponse)
def publish_idea_to_webhook(
    idea_id: str,
    request: WebhookPublishRequest,
    store: Store = Depends(get_store),
) -> WebhookPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    payload_type = "idea"
    payload = _build_webhook_payload(
        unit,
        evaluation,
        store,
        payload_template=request.payload_template,
        payload_fields=request.payload_fields,
    )

    if request.dry_run:
        return WebhookPublishResponse(
            idea_id=idea_id,
            dry_run=True,
            target_url=redact_url(request.webhook_url),
            status_code=None,
            attempts=0,
            payload_type=payload_type,
            payload=payload,
            publication_attempt=None,
        )

    publisher = WebhookPublisher(
        request.webhook_url,
        timeout=request.timeout,
        retries=request.max_retries,
    )
    try:
        result = publisher.publish(payload, payload_type=payload_type)
    except WebhookPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="webhook",
            target_url=publisher.redacted_url,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    publication_attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="webhook",
        target_url=result.url,
        status="success",
        response_status=result.status_code,
    )
    return WebhookPublishResponse(
        idea_id=idea_id,
        dry_run=False,
        target_url=result.url,
        status_code=result.status_code,
        attempts=result.attempts,
        payload_type=payload_type,
        payload=payload,
        publication_attempt=PublicationAttemptResponse(**publication_attempt),
    )


@router.post("/ideas/{idea_id}/publish/github-issue", response_model=GitHubIssuePublishResponse)
def publish_idea_to_github_issue(
    idea_id: str,
    request: GitHubIssuePublishRequest,
    store: Store = Depends(get_store),
) -> GitHubIssuePublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = GitHubIssuePublisher.from_env(
            repository=request.repository,
            token=request.token,
            api_url=request.api_url,
            labels=request.labels,
            timeout=request.timeout,
        )
    except GitHubIssuePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.token:
        message = (
            "GITHUB_TOKEN is required for live GitHub issue publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="github_issue",
            target_url=publisher.issue_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except GitHubIssuePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="github_issue",
            target_url=publisher.issue_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.issue_url or publisher.issue_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="github_issue",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return GitHubIssuePublishResponse(
        idea_id=idea_id,
        repository=result.repository,
        issue_url=result.issue_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/gitlab-issue", response_model=GitLabIssuePublishResponse)
def publish_idea_to_gitlab_issue(
    idea_id: str,
    request: GitLabIssuePublishRequest,
    store: Store = Depends(get_store),
) -> GitLabIssuePublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = GitLabIssuePublisher.from_env(
            project=request.project,
            project_id=request.project_id,
            project_path=request.project_path,
            token=request.token,
            base_url=request.base_url,
            labels=request.labels,
            assignee_ids=request.assignee_ids,
            confidential=request.confidential,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except GitLabIssuePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.token:
        message = (
            "GITLAB_TOKEN is required for live GitLab issue publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="gitlab_issue",
            target_url=publisher.issue_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(
            payload,
            title=request.title,
            labels=request.labels,
            assignee_ids=request.assignee_ids,
            confidential=request.confidential,
            dry_run=request.dry_run,
        )
    except GitLabIssuePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="gitlab_issue",
            target_url=publisher.issue_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.issue_url or publisher.issue_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="gitlab_issue",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return GitLabIssuePublishResponse(
        idea_id=idea_id,
        project=result.project,
        issue_id=result.issue_id,
        issue_iid=result.issue_iid,
        issue_url=result.issue_url,
        status_code=result.status_code,
        attempts=result.attempts,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/google-sheets", response_model=GoogleSheetsRowPublishResponse)
def publish_idea_to_google_sheets(
    idea_id: str,
    request: GoogleSheetsRowPublishRequest,
    store: Store = Depends(get_store),
) -> GoogleSheetsRowPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    try:
        publisher = GoogleSheetsRowPublisher.from_env(
            spreadsheet_id=request.spreadsheet_id,
            range=request.range,
            access_token=request.access_token,
            api_url=request.api_url,
            value_input_option=request.value_input_option,
            insert_data_option=request.insert_data_option,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except GoogleSheetsRowPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, store.get_evaluation(idea_id))
    if not request.dry_run and not publisher.has_auth:
        message = (
            "GOOGLE_SHEETS_ACCESS_TOKEN is required for live Google Sheets publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="google_sheets_row",
            target_url=publisher.append_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except GoogleSheetsRowPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="google_sheets_row",
            target_url=publisher.append_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=exc.status_code if exc.status_code and 400 <= exc.status_code < 500 else 502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="google_sheets_row",
        target_url=result.updated_range or publisher.append_endpoint,
        status="success",
        response_status=result.status_code,
    )

    return GoogleSheetsRowPublishResponse(
        idea_id=idea_id,
        spreadsheet_id=result.spreadsheet_id,
        range=result.range,
        updated_range=result.updated_range,
        updated_rows=result.updated_rows,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/google-sheets",
    response_model=DesignBriefGoogleSheetsRowPublishResponse,
)
def publish_design_brief_to_google_sheets(
    brief_id: str,
    request: DesignBriefGoogleSheetsRowPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefGoogleSheetsRowPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    access_token = request.access_token
    access_token_source = "request" if access_token else "none"
    if not access_token and request.access_token_env:
        access_token = os.getenv(request.access_token_env)
        access_token_source = f"env:{request.access_token_env}" if access_token else "none"
    elif not access_token and os.getenv("GOOGLE_SHEETS_ACCESS_TOKEN"):
        access_token_source = "env:GOOGLE_SHEETS_ACCESS_TOKEN"

    effective_range = _google_sheets_range(request.sheet, request.range)
    try:
        publisher = GoogleSheetsRowPublisher.from_env(
            spreadsheet_id=request.spreadsheet_id,
            range=effective_range,
            access_token=access_token,
            api_url=request.api_url,
            value_input_option=request.value_input_option,
            insert_data_option=request.insert_data_option,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except GoogleSheetsRowPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request_summary = {
        "spreadsheet_id": publisher.spreadsheet_id,
        "sheet": request.sheet,
        "range": publisher.range,
        "value_input_option": publisher.value_input_option,
        "insert_data_option": publisher.insert_data_option,
        "dry_run": request.dry_run,
        "timeout": request.timeout,
        "max_retries": request.max_retries,
        "access_token": "[redacted]" if publisher.access_token else None,
        "access_token_source": access_token_source
        if access_token_source != "none"
        else ("env:GOOGLE_SHEETS_ACCESS_TOKEN" if publisher.access_token else "none"),
        "markdown_summary_url": request.markdown_summary_url,
    }
    provider_metadata = {
        "provider": "google_sheets",
        "target_type": "google_sheets_row",
        "target_url": publisher.append_endpoint,
        "append_endpoint": publisher.append_endpoint,
        "spreadsheet_id": publisher.spreadsheet_id,
        "range": publisher.range,
        "columns": list(DESIGN_BRIEF_GOOGLE_SHEETS_COLUMNS),
        "design_brief_id": brief_id,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
    }
    payload = _design_brief_google_sheets_payload(
        brief,
        range=publisher.range,
        markdown_summary_url=request.markdown_summary_url,
    )

    if not request.dry_run and not publisher.has_auth:
        message = (
            "GOOGLE_SHEETS_ACCESS_TOKEN is required for live Google Sheets publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="google_sheets_row",
            target_url=publisher.append_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = _publish_google_sheets_payload(
            publisher,
            payload,
            dry_run=request.dry_run,
        )
    except GoogleSheetsRowPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="google_sheets_row",
            target_url=publisher.append_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=exc.status_code if exc.status_code and 400 <= exc.status_code < 500 else 502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result["updated_range"] or publisher.append_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="google_sheets_row",
        target_url=target_url,
        status="success",
        response_status=result["status_code"],
    )
    provider_metadata["target_url"] = target_url
    provider_metadata["updated_range"] = result["updated_range"]
    provider_metadata["updated_rows"] = result["updated_rows"]

    return DesignBriefGoogleSheetsRowPublishResponse(
        design_brief_id=brief_id,
        spreadsheet_id=publisher.spreadsheet_id,
        range=publisher.range,
        updated_range=result["updated_range"],
        updated_rows=result["updated_rows"],
        status_code=result["status_code"],
        dry_run=result["dry_run"],
        payload=result["payload"],
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/github-gist", response_model=GitHubGistPublishResponse)
def publish_idea_to_github_gist(
    idea_id: str,
    request: GitHubGistPublishRequest,
    store: Store = Depends(get_store),
) -> GitHubGistPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = GitHubGistPublisher.from_env(
            token=request.token,
            api_url=request.api_url,
            public=request.public,
            filename=request.filename,
            description=request.description,
            timeout=request.timeout,
        )
    except GitHubGistPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.token:
        message = (
            "GITHUB_TOKEN is required for live GitHub Gist publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="github_gist",
            target_url=publisher.gist_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(
            payload,
            dry_run=request.dry_run,
            evidence_links=request.evidence_links,
        )
    except GitHubGistPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="github_gist",
            target_url=publisher.gist_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.gist_url or publisher.gist_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="github_gist",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return GitHubGistPublishResponse(
        idea_id=idea_id,
        gist_url=result.gist_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


def _redact_github_project_error(message: str, request: GitHubProjectItemPublishRequest) -> str:
    redacted = message
    for secret in (request.token,):
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    if request.api_url:
        redacted = redacted.replace(request.api_url, redact_url(request.api_url))
    return redacted


@router.post(
    "/ideas/{idea_id}/publish/github-projects",
    response_model=GitHubProjectItemPublishResponse,
)
def publish_idea_to_github_projects(
    idea_id: str,
    request: GitHubProjectItemPublishRequest,
    store: Store = Depends(get_store),
) -> GitHubProjectItemPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = GitHubProjectItemPublisher.from_env(
            project_id=request.project_id,
            token=request.token,
            api_url=request.api_url,
            timeout=request.timeout,
        )
    except GitHubProjectPublishError as exc:
        raise HTTPException(
            status_code=400,
            detail=_redact_github_project_error(str(exc), request),
        ) from exc

    payload = generate_spec_preview(unit, evaluation)
    endpoint_url = redact_url(publisher.graphql_endpoint)
    if not request.dry_run and not publisher.token:
        message = (
            "GITHUB_TOKEN is required for live GitHub Project publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="github_project_item",
            target_url=endpoint_url,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except GitHubProjectPublishError as exc:
        message = _redact_github_project_error(str(exc), request)
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="github_project_item",
            target_url=endpoint_url,
            status="failure",
            response_status=exc.status_code,
            error=message,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.item_url or endpoint_url
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="github_project_item",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return GitHubProjectItemPublishResponse(
        idea_id=idea_id,
        project_id=result.project_id,
        item_id=result.item_id,
        item_url=result.item_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/linear", response_model=LinearIssuePublishResponse)
def publish_idea_to_linear_issue(
    idea_id: str,
    request: LinearIssuePublishRequest,
    store: Store = Depends(get_store),
) -> LinearIssuePublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = LinearIssuePublisher.from_env(
            team_id=request.team_id,
            api_key=request.api_key,
            project_id=request.project_id,
            labels=request.labels,
            priority=request.priority,
            timeout=request.timeout,
        )
    except LinearIssuePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.api_key:
        message = (
            "LINEAR_API_KEY is required for live Linear issue publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="linear_issue",
            target_url=publisher.graphql_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except LinearIssuePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="linear_issue",
            target_url=publisher.graphql_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.issue_url or publisher.graphql_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="linear_issue",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return LinearIssuePublishResponse(
        idea_id=idea_id,
        team_id=result.team_id,
        issue_url=result.issue_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/shortcut", response_model=ShortcutStoryPublishResponse)
def publish_idea_to_shortcut_story(
    idea_id: str,
    request: ShortcutStoryPublishRequest,
    store: Store = Depends(get_store),
) -> ShortcutStoryPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    try:
        publisher = ShortcutStoryPublisher.from_env(
            api_token=request.api_token,
            api_url=request.api_url,
            workflow_state_id=request.workflow_state_id,
            epic_id=request.epic_id,
            labels=request.labels,
            owner_ids=request.owner_ids,
            story_type=request.story_type,
            estimate=request.estimate,
            deadline=request.deadline,
            iteration_id=request.iteration_id,
            timeout=request.timeout,
        )
    except ShortcutStoryPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, store.get_evaluation(idea_id))
    endpoint_url = redact_url(publisher.story_endpoint)
    if not request.dry_run and not publisher.has_auth:
        message = (
            "SHORTCUT_API_TOKEN is required for live Shortcut story publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="shortcut_story",
            target_url=endpoint_url,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except ShortcutStoryPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="shortcut_story",
            target_url=endpoint_url,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.story_url or endpoint_url
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="shortcut_story",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return ShortcutStoryPublishResponse(
        idea_id=idea_id,
        story_id=result.story_id,
        story_url=result.story_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/asana", response_model=AsanaTaskPublishResponse)
def publish_idea_to_asana_task(
    idea_id: str,
    request: AsanaTaskPublishRequest,
    store: Store = Depends(get_store),
) -> AsanaTaskPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = AsanaTaskPublisher.from_env(
            workspace_gid=request.workspace_gid,
            access_token=request.access_token,
            project_gid=request.project_gid,
            section_gid=request.section_gid,
            assignee_gid=request.assignee_gid,
            tags=request.tags,
            due_on=request.due_on,
            timeout=request.timeout,
        )
    except AsanaTaskPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.access_token:
        message = (
            "ASANA_ACCESS_TOKEN is required for live Asana task publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="asana_task",
            target_url=publisher.task_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except AsanaTaskPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="asana_task",
            target_url=publisher.task_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.task_url or result.task_gid or publisher.task_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="asana_task",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return AsanaTaskPublishResponse(
        idea_id=idea_id,
        workspace_gid=result.workspace_gid,
        task_gid=result.task_gid,
        task_url=result.task_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/ideas/{idea_id}/publish/microsoft-planner",
    response_model=MicrosoftPlannerTaskPublishResponse,
)
def publish_idea_to_microsoft_planner_task(
    idea_id: str,
    request: MicrosoftPlannerTaskPublishRequest,
    store: Store = Depends(get_store),
) -> MicrosoftPlannerTaskPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = MicrosoftPlannerTaskPublisher.from_env(
            plan_id=request.plan_id,
            bucket_id=request.bucket_id,
            access_token=request.access_token,
            api_url=request.api_url,
            assignee_user_id=request.assignee_user_id,
            timeout=request.timeout,
        )
    except MicrosoftPlannerTaskPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = _spec_preview_with_evidence_links(unit, evaluation, store)
    if not request.dry_run and not publisher.has_auth:
        message = (
            "MS_PLANNER_ACCESS_TOKEN is required for live Microsoft Planner task publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="microsoft_planner_task",
            target_url=publisher.task_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except MicrosoftPlannerTaskPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="microsoft_planner_task",
            target_url=publisher.task_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.task_url or result.task_id or publisher.task_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="microsoft_planner_task",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return MicrosoftPlannerTaskPublishResponse(
        idea_id=idea_id,
        plan_id=result.plan_id,
        bucket_id=result.bucket_id,
        task_id=result.task_id,
        task_url=result.task_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/clickup", response_model=ClickUpTaskPublishResponse)
def publish_idea_to_clickup_task(
    idea_id: str,
    request: ClickUpTaskPublishRequest,
    store: Store = Depends(get_store),
) -> ClickUpTaskPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = ClickUpTaskPublisher.from_env(
            list_id=request.list_id,
            api_token=request.api_token,
            api_url=request.api_url,
            assignees=request.assignees,
            tags=request.tags,
            priority=request.priority,
            due_date=request.due_date,
            custom_fields=request.custom_fields,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except ClickUpTaskPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.has_auth:
        message = (
            "CLICKUP_API_TOKEN is required for live ClickUp task publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="clickup_task",
            target_url=publisher.task_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except ClickUpTaskPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="clickup_task",
            target_url=publisher.task_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.task_url or result.task_id or publisher.task_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="clickup_task",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return ClickUpTaskPublishResponse(
        idea_id=idea_id,
        list_id=result.list_id,
        task_id=result.task_id,
        task_url=result.task_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/monday", response_model=MondayItemPublishResponse)
def publish_idea_to_monday_item(
    idea_id: str,
    request: MondayItemPublishRequest,
    store: Store = Depends(get_store),
) -> MondayItemPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = MondayItemPublisher.from_env(
            board_id=request.board_id,
            api_token=request.api_token,
            group_id=request.group_id,
            item_name=request.item_name,
            column_values=request.column_values,
            api_url=request.api_url,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except MondayItemPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.has_auth:
        message = (
            "MONDAY_API_TOKEN is required for live Monday.com item publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="monday_item",
            target_url=publisher.item_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except MondayItemPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="monday_item",
            target_url=publisher.item_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.item_url or result.item_id or publisher.item_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="monday_item",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return MondayItemPublishResponse(
        idea_id=idea_id,
        board_id=result.board_id,
        group_id=result.group_id,
        item_id=result.item_id,
        item_url=result.item_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/jira", response_model=JiraIssuePublishResponse)
def publish_idea_to_jira_issue(
    idea_id: str,
    request: JiraIssuePublishRequest,
    store: Store = Depends(get_store),
) -> JiraIssuePublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = JiraIssuePublisher.from_env(
            site_url=request.site_url,
            project_key=request.project_key,
            email=request.email,
            api_token=request.api_token,
            bearer_token=request.bearer_token,
            issue_type=request.issue_type,
            labels=request.labels,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except JiraIssuePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher._has_auth:
        message = (
            "Jira email/api_token or bearer_token is required for live Jira issue publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="jira_issue",
            target_url=publisher.issue_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except JiraIssuePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="jira_issue",
            target_url=publisher.issue_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.issue_url or publisher.issue_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="jira_issue",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return JiraIssuePublishResponse(
        idea_id=idea_id,
        project_key=result.project_key,
        issue_key=result.issue_key,
        issue_url=result.issue_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/ideas/{idea_id}/publish/azure-devops",
    response_model=AzureDevOpsWorkItemPublishResponse,
)
def publish_idea_to_azure_devops_work_item(
    idea_id: str,
    request: AzureDevOpsWorkItemPublishRequest,
    store: Store = Depends(get_store),
) -> AzureDevOpsWorkItemPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = AzureDevOpsWorkItemPublisher.from_env(
            organization=request.organization,
            project=request.project,
            personal_access_token=request.personal_access_token,
            work_item_type=request.work_item_type,
            area_path=request.area_path,
            iteration_path=request.iteration_path,
            tags=request.tags,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except AzureDevOpsWorkItemPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.has_auth:
        message = (
            "AZURE_DEVOPS_PAT or AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN is required for live "
            "Azure DevOps work item publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="azure_devops_work_item",
            target_url=publisher.work_item_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except AzureDevOpsWorkItemPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="azure_devops_work_item",
            target_url=publisher.work_item_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.work_item_url or publisher.work_item_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="azure_devops_work_item",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return AzureDevOpsWorkItemPublishResponse(
        idea_id=idea_id,
        organization=result.organization,
        project=result.project,
        work_item_type=result.work_item_type,
        work_item_id=result.work_item_id,
        work_item_url=result.work_item_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post("/ideas/{idea_id}/publish/trello", response_model=TrelloCardPublishResponse)
def publish_idea_to_trello_card(
    idea_id: str,
    request: TrelloCardPublishRequest,
    store: Store = Depends(get_store),
) -> TrelloCardPublishResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    evaluation = store.get_evaluation(idea_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail=f"Evaluation not found: {idea_id}")

    try:
        publisher = TrelloCardPublisher.from_env(
            list_id=request.list_id,
            key=request.key,
            token=request.token,
            api_url=request.api_url,
            labels=request.labels,
            due=request.due,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except TrelloCardPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = generate_spec_preview(unit, evaluation)
    if not request.dry_run and not publisher.has_auth:
        message = (
            "TRELLO_KEY and TRELLO_TOKEN are required for live Trello card publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="trello_card",
            target_url=publisher.card_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except TrelloCardPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=idea_id,
            target_type="trello_card",
            target_url=publisher.card_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
            },
        ) from exc

    target_url = result.card_url or result.card_id or publisher.card_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=idea_id,
        target_type="trello_card",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )

    return TrelloCardPublishResponse(
        idea_id=idea_id,
        list_id=result.list_id,
        card_id=result.card_id,
        card_url=result.card_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


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


@router.post("/ideas/spec-readiness-batch", response_model=SpecReadinessBatchResponse)
def evaluate_ideas_spec_readiness_batch(
    body: SpecReadinessBatchRequest,
    store: Store = Depends(get_store),
) -> SpecReadinessBatchResponse:
    if body.idea_ids:
        units_by_id = {unit_id: store.get_buildable_unit(unit_id) for unit_id in body.idea_ids}
        units = [units_by_id[unit_id] for unit_id in body.idea_ids]
        requested_ids = body.idea_ids
    else:
        filtered_units = store.get_buildable_units(
            limit=body.limit,
            status=body.status,
            domain=body.domain,
        )
        units = filtered_units
        requested_ids = [unit.id for unit in filtered_units]

    results: list[SpecReadinessBatchItemResponse] = []
    for idea_id, unit in zip(requested_ids, units, strict=True):
        if not unit:
            results.append(
                SpecReadinessBatchItemResponse(
                    idea_id=idea_id,
                    status="not_found",
                    success=False,
                    error=f"Idea not found: {idea_id}",
                )
            )
            continue

        try:
            readiness = evaluate_spec_readiness(unit, store.get_evaluation(unit.id))
        except Exception as exc:
            results.append(
                SpecReadinessBatchItemResponse(
                    idea_id=idea_id,
                    status="error",
                    success=False,
                    error=str(exc),
                )
            )
            continue

        failed_checks = [check for check in readiness.get("checks", []) if not check.get("passed")]
        results.append(
            SpecReadinessBatchItemResponse(
                idea_id=unit.id,
                status="evaluated",
                success=True,
                score=readiness["score"],
                readiness_status=readiness["status"],
                passed=readiness["passed"],
                missing_sections=[check["label"] for check in failed_checks],
                blockers=[
                    check["remediation"] for check in failed_checks if check.get("remediation")
                ],
                failed_check_ids=readiness["failed_check_ids"],
                readiness=readiness,
            )
        )

    return SpecReadinessBatchResponse(results=results)


@router.get("/ideas/{idea_id}/review-gate", response_model=ReviewGateResponse)
def get_idea_review_gate(idea_id: str, store: Store = Depends(get_store)) -> ReviewGateResponse:
    try:
        return ReviewGateResponse.model_validate(asdict(build_review_gate_decision(store, idea_id)))
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")


@router.get("/ideas/{idea_id}/blast-radius", response_model=BlastRadiusResponse)
def get_idea_blast_radius(idea_id: str, store: Store = Depends(get_store)) -> BlastRadiusResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return BlastRadiusResponse.model_validate(
        asdict(estimate_idea_blast_radius(unit, store.get_evaluation(idea_id)))
    )


@router.get("/ideas/{idea_id}/implementation-plan")
def get_idea_implementation_plan(idea_id: str, store: Store = Depends(get_store)) -> dict:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    spec_preview = generate_spec_preview(unit, evaluation)
    return generate_implementation_plan(unit, evaluation, spec_preview)


@router.get("/ideas/{idea_id}/launch-checklist", response_model=LaunchChecklistResponse)
def get_idea_launch_checklist(
    idea_id: str, store: Store = Depends(get_store)
) -> LaunchChecklistResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    tact_spec = generate_spec_preview(unit, evaluation)
    return LaunchChecklistResponse.model_validate(
        generate_launch_checklist(unit, evaluation, tact_spec)
    )


@router.get("/ideas/{idea_id}/launch-checklist.md", response_model=None)
def get_idea_launch_checklist_markdown(
    idea_id: str, store: Store = Depends(get_store)
) -> Response:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    evaluation = store.get_evaluation(idea_id)
    tact_spec = generate_spec_preview(unit, evaluation)
    checklist = generate_launch_checklist(unit, evaluation, tact_spec)
    filename = f"{_download_filename_part(idea_id)}-launch-checklist.md"
    return Response(
        content=render_launch_checklist_markdown(checklist),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ideas/{idea_id}/acceptance-criteria", response_model=AcceptanceCriteriaResponse)
def get_idea_acceptance_criteria(
    idea_id: str, store: Store = Depends(get_store)
) -> AcceptanceCriteriaResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return AcceptanceCriteriaResponse.model_validate(
        generate_acceptance_criteria(
            unit,
            store.get_evaluation(idea_id),
            build_evidence_density_report(unit, store),
        )
    )


@router.get("/ideas/{idea_id}/experiment-card", response_model=ExperimentCardResponse)
def get_idea_experiment_card(
    idea_id: str, store: Store = Depends(get_store)
) -> ExperimentCardResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return ExperimentCardResponse.model_validate(
        generate_experiment_card(unit, store.get_evaluation(idea_id))
    )


@router.get("/ideas/{idea_id}/risk-register", response_model=None)
def get_idea_risk_register(
    idea_id: str,
    format: Literal["json", "markdown"] = Query("json"),
    store: Store = Depends(get_store),
) -> dict | Response:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    register = generate_risk_register(
        unit,
        store.get_evaluation(idea_id),
        build_evidence_density_report(unit, store),
        build_idea_contradiction_report(unit, store),
    )
    if format == "markdown":
        return _risk_register_markdown_response(idea_id, register)
    return register


@router.get("/ideas/{idea_id}/risk-register.md", response_model=None)
def get_idea_risk_register_markdown(
    idea_id: str,
    store: Store = Depends(get_store),
) -> Response:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    register = generate_risk_register(
        unit,
        store.get_evaluation(idea_id),
        build_evidence_density_report(unit, store),
        build_idea_contradiction_report(unit, store),
    )
    return _risk_register_markdown_response(idea_id, register)


def _risk_register_markdown_response(idea_id: str, register: dict[str, Any]) -> Response:
    filename = f"{_download_filename_part(idea_id)}-risk-register.md"
    return Response(
        content=render_risk_register_markdown(register),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ideas/{idea_id}/spec-bundle", response_model=SpecBundleResponse)
def get_idea_spec_bundle(
    idea_id: str,
    format: Literal["json", "markdown"] = Query("json"),
    store: Store = Depends(get_store),
) -> SpecBundleResponse | Response:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    bundle = generate_spec_bundle(unit, store.get_evaluation(idea_id), store)
    if format == "markdown":
        return _spec_bundle_markdown_response(idea_id, bundle)
    return SpecBundleResponse.model_validate(bundle)


@router.post("/ideas/spec-bundle-batch", response_model=SpecBundleBatchResponse)
def get_ideas_spec_bundle_batch(
    body: SpecBundleBatchRequest,
    store: Store = Depends(get_store),
) -> SpecBundleBatchResponse:
    results: list[SpecBundleBatchItemResponse] = []
    for idea_id in body.idea_ids:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            results.append(
                SpecBundleBatchItemResponse(
                    idea_id=idea_id,
                    status="not_found",
                    success=False,
                    status_code=404,
                    error=f"Idea not found: {idea_id}",
                )
            )
            continue

        try:
            bundle = generate_spec_bundle(unit, store.get_evaluation(idea_id), store)
            response = SpecBundleResponse.model_validate(bundle)
            results.append(
                SpecBundleBatchItemResponse(
                    idea_id=idea_id,
                    status="generated",
                    success=True,
                    status_code=200,
                    bundle=response if body.format == "json" else None,
                    markdown=render_spec_bundle_markdown(bundle)
                    if body.format == "markdown"
                    else None,
                )
            )
        except Exception as exc:
            results.append(
                SpecBundleBatchItemResponse(
                    idea_id=idea_id,
                    status="error",
                    success=False,
                    status_code=500,
                    error=str(exc),
                )
            )

    return SpecBundleBatchResponse(results=results)


@router.get("/ideas/{idea_id}/spec-bundle.md", response_model=None)
def get_idea_spec_bundle_markdown(
    idea_id: str,
    store: Store = Depends(get_store),
) -> Response:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    bundle = generate_spec_bundle(unit, store.get_evaluation(idea_id), store)
    return _spec_bundle_markdown_response(idea_id, bundle)


def _spec_bundle_markdown_response(idea_id: str, bundle: dict[str, Any]) -> Response:
    filename = f"{_download_filename_part(idea_id)}-spec-bundle.md"
    return Response(
        content=render_spec_bundle_markdown(bundle),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _download_filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    return cleaned.strip("-_") or "idea"


@router.get("/ideas/{idea_id}/product-brief.md", response_model=None)
def get_idea_product_brief_markdown(
    idea_id: str,
    include_evidence: bool = Query(True),
    include_validation: bool = Query(True),
    store: Store = Depends(get_store),
) -> Response:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    brief = generate_idea_product_brief(
        unit,
        store.get_evaluation(idea_id),
        store,
        include_evidence=include_evidence,
        include_validation=include_validation,
    )
    return Response(content=brief["markdown"], media_type="text/markdown")


@router.get("/ideas/{idea_id}/product-brief", response_model=IdeaProductBriefResponse)
def get_idea_product_brief(
    idea_id: str,
    include_evidence: bool = Query(True),
    include_validation: bool = Query(True),
    store: Store = Depends(get_store),
) -> IdeaProductBriefResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")

    return IdeaProductBriefResponse.model_validate(
        generate_idea_product_brief(
            unit,
            store.get_evaluation(idea_id),
            store,
            include_evidence=include_evidence,
            include_validation=include_validation,
        )
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
def get_idea_evidence_chain(
    idea_id: str, store: Store = Depends(get_store)
) -> EvidenceChainResponse:
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
    return EvidenceDensityResponse.model_validate(build_evidence_density_report(unit, store))


@router.get("/ideas/{idea_id}/contradictions", response_model=ContradictionReportResponse)
def get_idea_contradictions(
    idea_id: str,
    store: Store = Depends(get_store),
) -> ContradictionReportResponse:
    unit = store.get_buildable_unit(idea_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id}")
    return ContradictionReportResponse.model_validate(build_idea_contradiction_report(unit, store))


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


# ── Feedback Log ───────────────────────────────────────────────────


@router.get("/feedback/log", response_model=list[FeedbackLogEntryResponse])
def get_feedback_log(
    limit: int = Query(default=50, ge=1, le=500),
    store: Store = Depends(get_store),
) -> list[FeedbackLogEntryResponse]:
    return [
        FeedbackLogEntryResponse.model_validate(row) for row in store.get_feedback_log(limit=limit)
    ]


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


@router.get("/design-briefs/{brief_id}/bundle", response_model=DesignBriefBundleResponse)
def get_design_brief_bundle(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefBundleResponse:
    bundle = build_design_brief_bundle(store, brief_id)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefBundleResponse(**bundle)


@router.get("/design-briefs/{brief_id}/bundle.md", response_model=None)
def get_design_brief_bundle_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    bundle = build_design_brief_bundle(store, brief_id)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-bundle.md"
    return Response(
        content=render_design_brief_bundle(bundle, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/data-room-index",
    response_model=DesignBriefDataRoomIndexResponse,
)
def get_design_brief_data_room_index(
    brief_id: str,
    format: Literal["json", "markdown"] = Query("json"),
    store: Store = Depends(get_store),
) -> DesignBriefDataRoomIndexResponse | Response:
    index = build_design_brief_data_room_index(store, brief_id)
    if not index:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    if format == "markdown":
        return _design_brief_data_room_index_markdown_response(index)
    return DesignBriefDataRoomIndexResponse(**index)


@router.get("/design-briefs/{brief_id}/data-room-index.md", response_model=None)
def get_design_brief_data_room_index_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    index = build_design_brief_data_room_index(store, brief_id)
    if not index:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return _design_brief_data_room_index_markdown_response(index)


def _design_brief_data_room_index_markdown_response(index: dict[str, Any]) -> Response:
    filename = data_room_index_filename(index["design_brief"], fmt="markdown")
    return Response(
        content=render_design_brief_data_room_index(index, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@router.post(
    "/design-briefs/{brief_id}/publish/notion",
    response_model=NotionPagePublishResponse,
)
def publish_design_brief_to_notion(
    brief_id: str,
    request: NotionPagePublishRequest,
    store: Store = Depends(get_store),
) -> NotionPagePublishResponse:
    from max.analysis.blueprint_export import build_blueprint_source_brief
    from max.analysis.portfolio_synthesis import render_design_brief_markdown

    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    try:
        publisher = NotionPagePublisher.from_env(
            token=request.token,
            parent_page_id=request.parent_page_id,
            parent_database_id=request.parent_database_id,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except NotionPagePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    markdown = render_design_brief_markdown(brief, title=request.title)
    blueprint_packet = build_blueprint_source_brief(store, brief)
    try:
        result = publisher.publish(
            blueprint_packet,
            markdown=markdown,
            title=request.title,
            dry_run=request.dry_run,
        )
    except NotionPagePublishError as exc:
        status_code = exc.status_code
        if status_code in {400, 401, 403, 404, 409}:
            http_status = status_code
        else:
            http_status = 502
        raise HTTPException(status_code=http_status, detail=str(exc)) from exc

    return NotionPagePublishResponse(
        design_brief_id=brief_id,
        page_id=result.page_id,
        page_url=result.page_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
    )


@router.post(
    "/design-briefs/{brief_id}/publish/slack",
    response_model=DesignBriefSlackPublishResponse,
)
def publish_design_brief_to_slack(
    brief_id: str,
    request: SlackPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefSlackPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    resolved_webhook_url = (request.webhook_url or os.getenv("SLACK_WEBHOOK_URL") or "").strip()
    request_summary = {
        "webhook_url": redact_slack_webhook_url(resolved_webhook_url)
        if resolved_webhook_url
        else None,
        "webhook_url_source": "request"
        if request.webhook_url
        else ("env:SLACK_WEBHOOK_URL" if resolved_webhook_url else "none"),
        "channel": request.channel or os.getenv("SLACK_WEBHOOK_CHANNEL"),
        "username": request.username or os.getenv("SLACK_WEBHOOK_USERNAME"),
        "icon_emoji": request.icon_emoji or os.getenv("SLACK_WEBHOOK_ICON_EMOJI"),
        "icon_url": request.icon_url or os.getenv("SLACK_WEBHOOK_ICON_URL"),
        "dry_run": request.dry_run,
        "timeout": request.timeout,
    }

    if not request.dry_run and not resolved_webhook_url:
        message = (
            "Slack webhook URL is required for live Slack publishing; "
            "pass webhook_url, set SLACK_WEBHOOK_URL, or use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="slack_webhook",
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        publisher = SlackWebhookPublisher.from_env(
            webhook_url=resolved_webhook_url
            or "https://hooks.slack.com/services/dry-run/dry-run/redacted",
            channel=request.channel,
            username=request.username,
            icon_emoji=request.icon_emoji,
            icon_url=request.icon_url,
            timeout=request.timeout,
        )
    except SlackWebhookPublishError as exc:
        error = str(exc)
        if resolved_webhook_url:
            error = error.replace(resolved_webhook_url, redact_slack_webhook_url(resolved_webhook_url))
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="slack_webhook",
            target_url=redact_slack_webhook_url(resolved_webhook_url) if resolved_webhook_url else "",
            status="failure",
            error=error,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": error,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    payload = _design_brief_slack_payload(brief)
    provider_metadata = {
        "provider": "slack",
        "target_type": "slack_webhook",
        "target_url": publisher.redacted_url,
        "design_brief_id": brief_id,
    }
    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except SlackWebhookPublishError as exc:
        error = str(exc).replace(publisher.webhook_url, publisher.redacted_url)
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="slack_webhook",
            target_url=publisher.redacted_url,
            status="failure",
            response_status=exc.status_code,
            error=error,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": error,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    publication_attempt = None
    if not result.dry_run:
        publication_attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="slack_webhook",
            target_url=result.url,
            status="success",
            response_status=result.status_code,
        )

    return DesignBriefSlackPublishResponse(
        design_brief_id=brief_id,
        dry_run=result.dry_run,
        target_url=result.url,
        response_status=result.status_code,
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**publication_attempt)
        if publication_attempt
        else None,
    )


@router.post(
    "/design-briefs/{brief_id}/publish/discord",
    response_model=DesignBriefDiscordPublishResponse,
)
def publish_design_brief_to_discord(
    brief_id: str,
    request: DiscordPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefDiscordPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    resolved_webhook_url = (request.webhook_url or os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
    webhook_url_source = (
        "request"
        if request.webhook_url
        else ("env:DISCORD_WEBHOOK_URL" if resolved_webhook_url else "none")
    )

    if not request.dry_run and not resolved_webhook_url:
        message = (
            "Discord webhook URL is required for live Discord publishing; "
            "pass webhook_url, set DISCORD_WEBHOOK_URL, or use dry_run to preview"
        )
        request_summary = {
            "webhook_url": None,
            "webhook_url_source": webhook_url_source,
            "username": request.username or os.getenv("DISCORD_WEBHOOK_USERNAME"),
            "dry_run": request.dry_run,
            "timeout": request.timeout,
        }
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="discord_webhook",
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        publisher = DiscordWebhookPublisher.from_env(
            webhook_url=resolved_webhook_url
            or "https://discord.com/api/webhooks/dry-run/redacted",
            username=request.username,
            timeout=request.timeout,
        )
    except DiscordWebhookPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request_summary = {
        "webhook_url": publisher.redacted_url if resolved_webhook_url else None,
        "webhook_url_source": webhook_url_source,
        "username": publisher.username,
        "dry_run": request.dry_run,
        "timeout": request.timeout,
    }
    payload = _design_brief_discord_payload(brief)
    provider_metadata = {
        "provider": "discord",
        "source_type": "design_brief",
        "target_type": "discord_webhook",
        "target_url": publisher.redacted_url,
        "design_brief_id": brief_id,
    }

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except DiscordWebhookPublishError as exc:
        error = str(exc).replace(publisher.webhook_url, publisher.redacted_url)
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="discord_webhook",
            target_url=publisher.redacted_url,
            status="failure",
            response_status=exc.status_code,
            error=error,
        )
        http_status = exc.status_code if exc.status_code and 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=http_status,
            detail={
                "message": error,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    publication_attempt = None
    if not result.dry_run:
        publication_attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="discord_webhook",
            target_url=result.url,
            status="success",
            response_status=result.status_code,
        )

    return DesignBriefDiscordPublishResponse(
        design_brief_id=brief_id,
        dry_run=result.dry_run,
        target_url=result.url,
        response_status=result.status_code,
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**publication_attempt)
        if publication_attempt
        else None,
    )


@router.post(
    "/design-briefs/{brief_id}/publish/teams",
    response_model=DesignBriefTeamsPublishResponse,
)
def publish_design_brief_to_teams(
    brief_id: str,
    request: TeamsPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefTeamsPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    resolved_webhook_url = (request.webhook_url or os.getenv("TEAMS_WEBHOOK_URL") or "").strip()
    webhook_url_source = (
        "request"
        if request.webhook_url
        else ("env:TEAMS_WEBHOOK_URL" if resolved_webhook_url else "none")
    )

    if not request.dry_run and not resolved_webhook_url:
        message = (
            "Teams webhook URL is required for live Teams publishing; "
            "pass webhook_url, set TEAMS_WEBHOOK_URL, or use dry_run to preview"
        )
        request_summary = {
            "webhook_url": None,
            "webhook_url_source": webhook_url_source,
            "title": request.title,
            "dry_run": request.dry_run,
            "timeout": request.timeout,
        }
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="teams_webhook",
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        publisher = TeamsWebhookPublisher.from_env(
            webhook_url=resolved_webhook_url
            or "https://example.webhook.office.com/webhookb2/dry-run/redacted",
            timeout=request.timeout,
        )
    except TeamsWebhookPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request_summary = {
        "webhook_url": publisher.redacted_url if resolved_webhook_url else None,
        "webhook_url_source": webhook_url_source,
        "title": request.title,
        "dry_run": request.dry_run,
        "timeout": request.timeout,
    }
    payload = _design_brief_teams_payload(brief)
    provider_metadata = {
        "provider": "teams",
        "source_type": "design_brief",
        "target_type": "teams_webhook",
        "target_url": publisher.redacted_url,
        "design_brief_id": brief_id,
    }

    try:
        result = publisher.publish(
            payload,
            dry_run=request.dry_run,
            title=request.title,
            include_evidence=request.include_evidence,
        )
    except TeamsWebhookPublishError as exc:
        error = str(exc).replace(publisher.webhook_url, publisher.redacted_url)
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="teams_webhook",
            target_url=publisher.redacted_url,
            status="failure",
            response_status=exc.status_code,
            error=error,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": error,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    publication_attempt = None
    if not result.dry_run:
        publication_attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="teams_webhook",
            target_url=result.url,
            status="success",
            response_status=result.status_code,
        )

    return DesignBriefTeamsPublishResponse(
        design_brief_id=brief_id,
        dry_run=result.dry_run,
        target_url=result.url,
        response_status=result.status_code,
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**publication_attempt)
        if publication_attempt
        else None,
    )


@router.post(
    "/design-briefs/{brief_id}/publish/github-gist",
    response_model=DesignBriefGitHubGistPublishResponse,
)
def publish_design_brief_to_github_gist(
    brief_id: str,
    request: DesignBriefGitHubGistPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefGitHubGistPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    resolved_token = request.token
    token_source = "request" if request.token else "none"
    if not resolved_token and request.token_env:
        resolved_token = os.getenv(request.token_env)
        token_source = f"env:{request.token_env}" if resolved_token else "none"
    elif not resolved_token and os.getenv("GITHUB_TOKEN"):
        token_source = "env:GITHUB_TOKEN"

    filename = request.filename or f"{_download_filename_part(brief_id)}.md"
    try:
        publisher = GitHubGistPublisher.from_env(
            token=resolved_token,
            api_url=request.api_url,
            public=request.public,
            filename=filename,
            description=request.description,
            timeout=request.timeout,
        )
    except GitHubGistPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = request.title or str(brief.get("title") or brief_id)
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    if request.include_source_ids:
        markdown = _append_design_brief_source_ids(markdown, brief)

    request_summary = {
        "api_url": publisher.api_url,
        "public": publisher.public,
        "filename": publisher.filename,
        "description": publisher.description,
        "title": title,
        "include_source_ids": request.include_source_ids,
        "dry_run": request.dry_run,
        "timeout": request.timeout,
        "token": "[redacted]" if publisher.token else None,
        "token_source": token_source,
    }

    if not request.dry_run and not publisher.token:
        message = (
            "GITHUB_TOKEN is required for live GitHub Gist publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="github_gist",
            target_url=publisher.gist_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish_design_brief(
            brief,
            markdown=markdown,
            dry_run=request.dry_run,
        )
    except GitHubGistPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="github_gist",
            target_url=publisher.gist_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.gist_url or publisher.gist_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="github_gist",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    result_metadata = result.payload.get("metadata", {})
    provider_metadata = {
        "provider": "github",
        "target_type": "github_gist",
        "target_url": target_url,
        "gist_endpoint": publisher.gist_endpoint,
        "github_gist_id": result_metadata.get("github_gist_id"),
    }

    return DesignBriefGitHubGistPublishResponse(
        design_brief_id=brief_id,
        gist_url=result.gist_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        filename=publisher.filename,
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/github-issue",
    response_model=DesignBriefGitHubIssuePublishResponse,
)
def publish_design_brief_to_github_issue(
    brief_id: str,
    request: DesignBriefGitHubIssuePublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefGitHubIssuePublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    resolved_token = request.token
    token_source = "request" if request.token else "none"
    if not resolved_token and request.token_env:
        resolved_token = os.getenv(request.token_env)
        token_source = f"env:{request.token_env}" if resolved_token else "none"
    elif not resolved_token and os.getenv("GITHUB_TOKEN"):
        token_source = "env:GITHUB_TOKEN"

    try:
        publisher = GitHubIssuePublisher.from_env(
            repository=request.repository,
            token=resolved_token,
            api_url=request.api_url,
            labels=request.labels,
            timeout=request.timeout,
        )
    except GitHubIssuePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = request.title or f"[Max] {brief.get('title') or brief_id}"
    body = _deterministic_design_brief_markdown(brief, title=title)
    if request.include_source_ids:
        body = _append_design_brief_source_ids(body, brief)
    payload = {
        "title": title,
        "body": body,
        "labels": list(request.labels),
        "assignees": list(request.assignees),
        "milestone": request.milestone,
        "metadata": {
            "publisher": "max.github_issues",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": list(brief.get("source_idea_ids") or []),
            "repository": publisher.repository,
            "include_source_ids": request.include_source_ids,
        },
    }
    request_summary = {
        "repository": publisher.repository,
        "labels": list(request.labels),
        "assignees": list(request.assignees),
        "milestone": request.milestone,
        "dry_run": request.dry_run,
        "include_source_ids": request.include_source_ids,
        "token": "[redacted]" if publisher.token else None,
        "token_source": token_source,
    }

    if not request.dry_run and not publisher.token:
        message = (
            "GITHUB_TOKEN is required for live GitHub issue publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="github_issue",
            target_url=publisher.issue_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish_issue_payload(payload, dry_run=request.dry_run)
    except GitHubIssuePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="github_issue",
            target_url=publisher.issue_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.issue_url or publisher.issue_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="github_issue",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    result_metadata = result.payload.get("metadata", {})
    provider_metadata = {
        "provider": "github",
        "target_type": "github_issue",
        "target_url": target_url,
        "issue_endpoint": publisher.issue_endpoint,
        "github_issue_number": result_metadata.get("github_issue_number"),
    }

    return DesignBriefGitHubIssuePublishResponse(
        design_brief_id=brief_id,
        repository=result.repository,
        issue_url=result.issue_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        title=str(result.payload["title"]),
        body_preview=_markdown_preview(str(result.payload["body"])),
        labels=list(result.payload.get("labels") or []),
        assignees=list(result.payload.get("assignees") or []),
        milestone=result.payload.get("milestone"),
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/github-milestone",
    response_model=DesignBriefGitHubMilestonePublishResponse,
)
def publish_design_brief_to_github_milestone(
    brief_id: str,
    request: DesignBriefGitHubMilestonePublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefGitHubMilestonePublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    resolved_token = request.token
    token_source = "request" if request.token else "none"
    if not resolved_token and request.token_env:
        resolved_token = os.getenv(request.token_env)
        token_source = f"env:{request.token_env}" if resolved_token else "none"
    elif not resolved_token and os.getenv("GITHUB_TOKEN"):
        token_source = "env:GITHUB_TOKEN"

    try:
        publisher = GitHubMilestonePublisher.from_env(
            repository=request.repository,
            token=resolved_token,
            api_url=request.api_url,
            labels=request.labels,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except GitHubMilestonePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = request.title or str(brief.get("title") or brief_id)
    description = _deterministic_design_brief_markdown(brief, title=title)
    if request.include_source_ids:
        description = _append_design_brief_source_ids(description, brief)

    try:
        payload = publisher.build_design_brief_payload(
            brief,
            description=description,
            title=title,
            state=request.state,
            due_on=request.due_on,
            include_source_ids=request.include_source_ids,
        ).to_dict()
    except GitHubMilestonePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request_summary = {
        "repository": publisher.repository,
        "labels": list(request.labels),
        "state": payload["state"],
        "due_on": payload.get("due_on"),
        "dry_run": request.dry_run,
        "include_source_ids": request.include_source_ids,
        "token": "[redacted]" if publisher.token else None,
        "token_source": token_source,
        "milestone_endpoint": redact_url(publisher.milestone_endpoint),
    }

    if not request.dry_run and not publisher.token:
        message = (
            "GITHUB_TOKEN is required for live GitHub milestone publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="github_milestone",
            target_url=redact_url(publisher.milestone_endpoint),
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish_milestone_payload(payload, dry_run=request.dry_run)
    except GitHubMilestonePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="github_milestone",
            target_url=redact_url(publisher.milestone_endpoint),
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.milestone_url or redact_url(publisher.milestone_endpoint)
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="github_milestone",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    result_metadata = result.payload.get("metadata", {})
    provider_metadata = {
        "provider": "github",
        "target_type": "github_milestone",
        "target_url": target_url,
        "milestone_endpoint": redact_url(publisher.milestone_endpoint),
        "github_milestone_number": result.milestone_number
        or result_metadata.get("github_milestone_number"),
        "github_milestone_url": result.milestone_url
        or result_metadata.get("github_milestone_url"),
    }

    return DesignBriefGitHubMilestonePublishResponse(
        design_brief_id=brief_id,
        repository=result.repository,
        milestone_number=result.milestone_number,
        milestone_url=result.milestone_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        title=str(result.payload["title"]),
        description_preview=_markdown_preview(str(result.payload["description"])),
        state=str(result.payload["state"]),
        due_on=result.payload.get("due_on"),
        labels=list(result.payload.get("labels") or []),
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/jira",
    response_model=DesignBriefJiraIssuePublishResponse,
)
def publish_design_brief_to_jira_issue(
    brief_id: str,
    request: DesignBriefJiraIssuePublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefJiraIssuePublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    try:
        publisher = JiraIssuePublisher.from_env(
            site_url=request.site_url,
            project_key=request.project_key,
            email=request.email,
            api_token=request.api_token,
            bearer_token=request.bearer_token,
            issue_type=request.issue_type,
            labels=request.labels,
            assignee_account_id=request.assignee_account_id,
            priority=request.priority,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except JiraIssuePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = request.title or str(brief.get("title") or brief_id)
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    if request.include_source_ids:
        markdown = _append_design_brief_source_ids(markdown, brief)

    payload: dict[str, Any] = {
        "summary": title,
        "description": markdown,
        "project_key": publisher.project_key,
        "issue_type": publisher.issue_type,
        "labels": list(request.labels),
        "metadata": {
            "publisher": "max.jira_issues",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": list(brief.get("source_idea_ids") or []),
            "project_key": publisher.project_key,
            "issue_type": publisher.issue_type,
            "include_source_ids": request.include_source_ids,
        },
    }
    if publisher.assignee_account_id:
        payload["assignee_account_id"] = publisher.assignee_account_id
    if publisher.priority:
        payload["priority"] = publisher.priority

    request_summary = {
        "site_url": redact_url(publisher.site_url),
        "project_key": publisher.project_key,
        "issue_type": publisher.issue_type,
        "labels": list(request.labels),
        "assignee_account_id": publisher.assignee_account_id,
        "priority": publisher.priority,
        "dry_run": request.dry_run,
        "include_source_ids": request.include_source_ids,
        "email": publisher.email,
        "api_token": "[redacted]" if publisher.api_token else None,
        "bearer_token": "[redacted]" if publisher.bearer_token else None,
        "credential_source": _jira_credential_source(request, publisher),
    }

    if not request.dry_run and not publisher._has_auth:
        message = (
            "Jira email/api_token or bearer_token is required for live Jira issue publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="jira_issue",
            target_url=redact_url(publisher.issue_endpoint),
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish_issue_payload(payload, dry_run=request.dry_run)
    except JiraIssuePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="jira_issue",
            target_url=redact_url(publisher.issue_endpoint),
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.issue_url or redact_url(publisher.issue_endpoint)
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="jira_issue",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    result_metadata = result.payload.get("metadata", {})
    provider_metadata = {
        "provider": "jira",
        "target_type": "jira_issue",
        "target_url": target_url,
        "issue_endpoint": redact_url(publisher.issue_endpoint),
        "jira_issue_id": result_metadata.get("jira_issue_id"),
        "jira_issue_key": result.issue_key or result_metadata.get("jira_issue_key"),
        "jira_issue_url": result.issue_url or result_metadata.get("jira_issue_url"),
    }

    return DesignBriefJiraIssuePublishResponse(
        design_brief_id=brief_id,
        project_key=result.project_key,
        issue_key=result.issue_key,
        issue_url=result.issue_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        summary=str(result.payload["summary"]),
        description_preview=_markdown_preview(str(result.payload["description"])),
        issue_type=str(result.payload["issue_type"]),
        labels=list(result.payload.get("labels") or []),
        assignee_account_id=result.payload.get("assignee_account_id"),
        priority=result.payload.get("priority"),
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/bitbucket",
    response_model=DesignBriefBitbucketIssuePublishResponse,
)
def publish_design_brief_to_bitbucket_issue(
    brief_id: str,
    request: DesignBriefBitbucketIssuePublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefBitbucketIssuePublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    try:
        publisher = BitbucketIssuePublisher.from_env(
            workspace=request.workspace,
            repository=request.repository,
            username=request.username,
            app_password=request.app_password,
            api_url=request.api_url,
            issue_kind=request.issue_kind,
            priority=request.priority,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except BitbucketIssuePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = request.title or str(brief.get("title") or brief_id)
    spec = _design_brief_bitbucket_spec(brief, title=title)
    if not request.include_source_ids:
        spec["evidence"]["source_idea_ids"] = []
        spec["evidence"]["lead_idea_id"] = None
    request_summary = {
        "api_url": redact_url(publisher.api_url),
        "issue_endpoint": redact_url(publisher.issue_endpoint),
        "workspace": publisher.workspace,
        "repository": publisher.repository,
        "issue_kind": request.issue_kind,
        "priority": request.priority,
        "dry_run": request.dry_run,
        "include_source_ids": request.include_source_ids,
        "timeout": request.timeout,
        "max_retries": request.max_retries,
        "username": publisher.username,
        "username_source": "request"
        if request.username
        else ("env:BITBUCKET_USERNAME" if os.getenv("BITBUCKET_USERNAME") else "none"),
        "app_password": "[redacted]" if publisher.app_password else None,
        "app_password_source": "request"
        if request.app_password
        else (
            "env:BITBUCKET_APP_PASSWORD"
            if os.getenv("BITBUCKET_APP_PASSWORD")
            else "none"
        ),
    }

    if not request.dry_run and not publisher._has_auth:
        message = (
            "BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD are required for live "
            "Bitbucket issue publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="bitbucket_issue",
            target_url=redact_url(publisher.issue_endpoint),
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish(
            spec,
            title=title,
            issue_kind=request.issue_kind,
            priority=request.priority,
            dry_run=request.dry_run,
        )
    except BitbucketIssuePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="bitbucket_issue",
            target_url=redact_url(publisher.issue_endpoint),
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.issue_url or redact_url(publisher.issue_endpoint)
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="bitbucket_issue",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    result_metadata = result.payload.get("metadata", {})
    provider_metadata = {
        "provider": "bitbucket",
        "target_type": "bitbucket_issue",
        "target_url": target_url,
        "issue_endpoint": redact_url(publisher.issue_endpoint),
        "design_brief_id": brief_id,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
        "readiness_score": float(brief.get("readiness_score") or 0.0),
        "bitbucket_issue_id": result.issue_id
        or result_metadata.get("bitbucket_issue_id"),
        "bitbucket_issue_url": result.issue_url
        or result_metadata.get("bitbucket_issue_url"),
        "bitbucket_attempts": result.attempts
        or result_metadata.get("bitbucket_attempts"),
    }

    return DesignBriefBitbucketIssuePublishResponse(
        design_brief_id=brief_id,
        workspace=result.workspace,
        repository=result.repository,
        issue_id=result.issue_id,
        issue_url=result.issue_url,
        status_code=result.status_code,
        attempts=result.attempts,
        dry_run=result.dry_run,
        title=str(result.payload["title"]),
        content_preview=_markdown_preview(str(result.payload["content"])),
        kind=str(result.payload["kind"]),
        priority=str(result.payload["priority"]),
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/confluence",
    response_model=DesignBriefConfluencePagePublishResponse,
)
def publish_design_brief_to_confluence_page(
    brief_id: str,
    request: DesignBriefConfluencePagePublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefConfluencePagePublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    try:
        publisher = ConfluencePagePublisher.from_env(
            site_url=request.site_url,
            space_key=request.space_key,
            parent_page_id=request.parent_page_id,
            email=request.email,
            api_token=request.api_token,
            bearer_token=request.bearer_token,
            timeout=request.timeout,
        )
    except ConfluencePagePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = request.title or str(brief.get("title") or brief_id)
    packet = _design_brief_confluence_packet(
        brief,
        title=title,
        include_source_ids=request.include_source_ids,
    )
    page_payload = publisher.build_page_payload(packet, title=title).to_dict()
    request_summary = {
        "site_url": redact_url(publisher.site_url),
        "page_endpoint": redact_url(publisher.page_endpoint),
        "space_key": publisher.space_key,
        "parent_page_id": publisher.parent_page_id,
        "title": title,
        "dry_run": request.dry_run,
        "include_source_ids": request.include_source_ids,
        "timeout": request.timeout,
        "email": publisher.email,
        "api_token": "[redacted]" if publisher.api_token else None,
        "bearer_token": "[redacted]" if publisher.bearer_token else None,
        "credential_source": _confluence_credential_source(request, publisher),
    }
    provider_metadata = {
        "provider": "confluence",
        "target_type": "confluence_page",
        "target_url": redact_url(publisher.page_endpoint),
        "page_endpoint": redact_url(publisher.page_endpoint),
        "design_brief_id": brief_id,
        "space_key": publisher.space_key,
        "parent_page_id": publisher.parent_page_id,
        "source_idea_ids": list(packet["design_brief"].get("source_idea_ids") or []),
        "readiness_score": float(brief.get("readiness_score") or 0.0),
    }

    if not request.dry_run and not publisher._has_auth:
        message = (
            "Confluence email/api_token or bearer_token is required for live page publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="confluence_page",
            target_url=redact_url(publisher.page_endpoint),
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = asyncio.run(publisher.publish_page_payload(page_payload, dry_run=request.dry_run))
    except ConfluencePagePublishError as exc:
        message = _redact_confluence_message(str(exc), publisher)
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="confluence_page",
            target_url=redact_url(publisher.page_endpoint),
            status="failure",
            response_status=exc.status_code,
            error=message,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.page_url or redact_url(publisher.page_endpoint)
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="confluence_page",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    result_metadata = result.payload.get("metadata", {})
    provider_metadata.update(
        {
            "target_url": target_url,
            "confluence_page_id": result.page_id
            or result_metadata.get("confluence_page_id"),
            "confluence_page_url": result.page_url
            or result_metadata.get("confluence_page_url"),
        }
    )
    body = str(result.payload["body"]["storage"]["value"])

    return DesignBriefConfluencePagePublishResponse(
        design_brief_id=brief_id,
        space_key=result.space_key,
        page_id=result.page_id,
        page_url=result.page_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        title=str(result.payload["title"]),
        body_preview=_markdown_preview(body),
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/microsoft-planner",
    response_model=DesignBriefMicrosoftPlannerTaskPublishResponse,
)
def publish_design_brief_to_microsoft_planner_task(
    brief_id: str,
    request: DesignBriefMicrosoftPlannerTaskPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefMicrosoftPlannerTaskPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    try:
        publisher = MicrosoftPlannerTaskPublisher.from_env(
            plan_id=request.plan_id,
            bucket_id=request.bucket_id,
            access_token=request.access_token,
            api_url=request.api_url,
            assignee_user_id=request.assignee_user_id,
            due_date_time=request.due_date_time,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except MicrosoftPlannerTaskPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = request.title or str(brief.get("title") or brief_id)
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    if request.include_source_ids:
        markdown = _append_design_brief_source_ids(markdown, brief)

    payload: dict[str, Any] = {
        "planId": publisher.plan_id,
        "bucketId": publisher.bucket_id,
        "title": title,
        "details": markdown,
        "metadata": {
            "publisher": "max.microsoft_planner_tasks",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": list(brief.get("source_idea_ids") or []),
            "plan_id": publisher.plan_id,
            "bucket_id": publisher.bucket_id,
            "include_source_ids": request.include_source_ids,
        },
    }
    if publisher.assignee_user_id:
        payload["assignments"] = {
            publisher.assignee_user_id: {"@odata.type": "microsoft.graph.plannerAssignment"}
        }
    if publisher.due_date_time:
        payload["dueDateTime"] = publisher.due_date_time

    request_summary = {
        "api_url": redact_url(publisher.api_url),
        "task_endpoint": redact_url(publisher.task_endpoint),
        "plan_id": publisher.plan_id,
        "bucket_id": publisher.bucket_id,
        "assignee_user_id": publisher.assignee_user_id,
        "due_date_time": publisher.due_date_time,
        "dry_run": request.dry_run,
        "include_source_ids": request.include_source_ids,
        "timeout": request.timeout,
        "max_retries": request.max_retries,
        "access_token": "[redacted]" if publisher.access_token else None,
        "credential_source": _microsoft_planner_credential_source(request, publisher),
    }

    if not request.dry_run and not publisher.has_auth:
        message = (
            "MS_PLANNER_ACCESS_TOKEN is required for live Microsoft Planner task publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="microsoft_planner_task",
            target_url=redact_url(publisher.task_endpoint),
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish_task_payload(payload, dry_run=request.dry_run)
    except MicrosoftPlannerTaskPublishError as exc:
        message = _redact_microsoft_planner_message(str(exc), publisher)
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="microsoft_planner_task",
            target_url=redact_url(publisher.task_endpoint),
            status="failure",
            response_status=exc.status_code,
            error=message,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.task_url or result.task_id or redact_url(publisher.task_endpoint)
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="microsoft_planner_task",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    result_metadata = result.payload.get("metadata", {})
    provider_metadata = {
        "provider": "microsoft_planner",
        "target_type": "microsoft_planner_task",
        "target_url": target_url,
        "task_endpoint": redact_url(publisher.task_endpoint),
        "task_id": result.task_id,
        "task_url": result.task_url,
        "source_type": result_metadata.get("source_type"),
        "design_brief_id": result_metadata.get("design_brief_id"),
    }

    return DesignBriefMicrosoftPlannerTaskPublishResponse(
        design_brief_id=brief_id,
        plan_id=result.plan_id,
        bucket_id=result.bucket_id,
        task_id=result.task_id,
        task_url=result.task_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        title=str(result.payload["title"]),
        details_preview=_markdown_preview(str(result.payload["details"])),
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/linear",
    response_model=DesignBriefLinearPublishResponse,
)
def publish_design_brief_to_linear_issue(
    brief_id: str,
    request: DesignBriefLinearPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefLinearPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    resolved_api_key = request.api_key
    api_key_source = "request" if request.api_key else "none"
    if not resolved_api_key and request.api_key_env:
        resolved_api_key = os.getenv(request.api_key_env)
        api_key_source = f"env:{request.api_key_env}" if resolved_api_key else "none"
    elif not resolved_api_key and os.getenv("LINEAR_API_KEY"):
        api_key_source = "env:LINEAR_API_KEY"

    try:
        publisher = LinearIssuePublisher.from_env(
            team_id=request.team_id,
            api_key=resolved_api_key,
            project_id=request.project_id,
            labels=request.labels,
            priority=request.priority,
            assignee_id=request.assignee_id,
            timeout=request.timeout,
        )
    except LinearIssuePublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = request.title or f"[Max] {brief.get('title') or brief_id}"
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    payload = {
        "title": title,
        "description": markdown,
        "team_id": publisher.team_id,
        "label_ids": list(request.labels),
        "metadata": {
            "publisher": "max.linear_issues",
            "source_type": "design_brief",
            "design_brief_id": brief_id,
            "domain": brief.get("domain"),
            "theme": brief.get("theme"),
            "lead_idea_id": brief.get("lead_idea_id"),
            "source_idea_ids": list(brief.get("source_idea_ids") or []),
            "project_id": publisher.project_id,
        },
    }
    if publisher.project_id:
        payload["project_id"] = publisher.project_id
    if publisher.priority is not None:
        payload["priority"] = publisher.priority
    if publisher.assignee_id:
        payload["assignee_id"] = publisher.assignee_id

    request_summary = {
        "team_id": publisher.team_id,
        "project_id": publisher.project_id,
        "labels": list(request.labels),
        "priority": publisher.priority,
        "assignee_id": publisher.assignee_id,
        "dry_run": request.dry_run,
        "api_key": "[redacted]" if publisher.api_key else None,
        "api_key_source": api_key_source,
    }

    if not request.dry_run and not publisher.api_key:
        message = (
            "LINEAR_API_KEY is required for live Linear issue publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="linear_issue",
            target_url=publisher.graphql_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish_payload(payload, dry_run=request.dry_run)
    except LinearIssuePublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="linear_issue",
            target_url=publisher.graphql_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.issue_url or publisher.graphql_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="linear_issue",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    result_metadata = result.payload.get("metadata", {})
    provider_metadata = {
        "provider": "linear",
        "target_type": "linear_issue",
        "target_url": target_url,
        "graphql_endpoint": publisher.graphql_endpoint,
        "linear_issue_identifier": result_metadata.get("linear_issue_identifier"),
    }

    return DesignBriefLinearPublishResponse(
        design_brief_id=brief_id,
        team_id=result.team_id,
        issue_url=result.issue_url,
        issue_id=result_metadata.get("linear_issue_id"),
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/clickup",
    response_model=DesignBriefClickUpTaskPublishResponse,
)
def publish_design_brief_to_clickup_task(
    brief_id: str,
    request: DesignBriefClickUpTaskPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefClickUpTaskPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    try:
        publisher = ClickUpTaskPublisher.from_env(
            list_id=request.list_id,
            api_token=request.api_token,
            api_url=request.api_url,
            assignees=request.assignees,
            tags=request.tags,
            priority=request.priority,
            due_date=request.due_date,
            custom_fields=request.custom_fields,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except ClickUpTaskPublishError as exc:
        message = _redact_clickup_token(str(exc), request.api_token)
        raise HTTPException(status_code=400, detail=message) from exc

    title = request.title or str(brief.get("title") or brief_id)
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    evidence_links = _design_brief_evidence_links(brief, store)
    payload = _design_brief_clickup_spec(
        brief,
        title=title,
        markdown=markdown,
        evidence_links=evidence_links,
    )
    request_summary = {
        "api_url": redact_url(publisher.api_url),
        "task_endpoint": redact_url(publisher.task_endpoint),
        "list_id": publisher.list_id,
        "assignees": list(publisher.assignees),
        "tags": list(request.tags),
        "priority": publisher.priority,
        "due_date": publisher.due_date,
        "custom_fields": list(request.custom_fields),
        "dry_run": request.dry_run,
        "timeout": request.timeout,
        "max_retries": request.max_retries,
        "api_token": "[redacted]" if publisher.api_token else None,
        "api_token_source": "request"
        if request.api_token
        else ("env:CLICKUP_API_TOKEN" if os.getenv("CLICKUP_API_TOKEN") else "none"),
    }
    provider_metadata = {
        "provider": "clickup",
        "target_type": "clickup_task",
        "target_url": redact_url(publisher.task_endpoint),
        "task_endpoint": redact_url(publisher.task_endpoint),
        "design_brief_id": brief_id,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
        "readiness_score": float(brief.get("readiness_score") or 0.0),
    }

    if not request.dry_run and not publisher.has_auth:
        message = (
            "CLICKUP_API_TOKEN is required for live ClickUp task publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="clickup_task",
            target_url=redact_url(publisher.task_endpoint),
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except ClickUpTaskPublishError as exc:
        message = _redact_clickup_token(str(exc), publisher.api_token)
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="clickup_task",
            target_url=redact_url(publisher.task_endpoint),
            status="failure",
            response_status=exc.status_code,
            error=message,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    result.payload["design_brief"] = {
        "id": brief_id,
        "title": title,
        "summary": payload["project"]["summary"],
        "readiness_score": payload["quality"]["quality_score"],
        "source_idea_ids": list(payload["evidence"]["source_idea_ids"]),
        "evidence_links": evidence_links,
        "markdown": markdown,
    }
    result.payload["metadata"] = {
        **result.payload.get("metadata", {}),
        "design_brief_id": brief_id,
        "source_idea_ids": list(payload["evidence"]["source_idea_ids"]),
        "readiness_score": payload["quality"]["quality_score"],
    }

    target_url = result.task_url or result.task_id or redact_url(publisher.task_endpoint)
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="clickup_task",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    provider_metadata.update(
        {
            "target_url": target_url,
            "task_id": result.task_id,
            "task_url": result.task_url,
        }
    )

    return DesignBriefClickUpTaskPublishResponse(
        design_brief_id=brief_id,
        list_id=result.list_id,
        task_id=result.task_id,
        task_url=result.task_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/hubspot-deal",
    response_model=DesignBriefHubSpotDealPublishResponse,
)
def publish_design_brief_to_hubspot_deal(
    brief_id: str,
    request: DesignBriefHubSpotDealPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefHubSpotDealPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    try:
        publisher = HubSpotDealPublisher.from_env(
            access_token=request.access_token,
            api_url=request.api_url,
            pipeline_id=request.pipeline_id,
            deal_stage_id=request.deal_stage_id,
            portal_id=request.portal_id,
            deal_owner_id=request.deal_owner_id,
            amount=request.amount,
            close_date=request.close_date,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except HubSpotDealPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    access_token_source = "request" if request.access_token else "none"
    if not request.access_token:
        if os.getenv("HUBSPOT_ACCESS_TOKEN"):
            access_token_source = "env:HUBSPOT_ACCESS_TOKEN"
        elif os.getenv("HUBSPOT_TOKEN"):
            access_token_source = "env:HUBSPOT_TOKEN"

    title = request.deal_name or str(brief.get("title") or brief_id)
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    request_summary = {
        "api_url": redact_url(publisher.api_url),
        "deal_endpoint": redact_url(publisher.deal_endpoint),
        "pipeline_id": publisher.pipeline_id,
        "deal_stage_id": publisher.deal_stage_id,
        "portal_id": publisher.portal_id,
        "deal_owner_id": publisher.deal_owner_id,
        "deal_name": title,
        "amount": publisher.amount,
        "close_date": publisher.close_date,
        "dry_run": request.dry_run,
        "timeout": request.timeout,
        "max_retries": request.max_retries,
        "access_token": "[redacted]" if publisher.access_token else None,
        "access_token_source": access_token_source,
    }
    provider_metadata = {
        "provider": "hubspot",
        "source_type": "design_brief",
        "target_type": "hubspot_deal",
        "target_url": redact_url(publisher.deal_endpoint),
        "deal_endpoint": redact_url(publisher.deal_endpoint),
        "design_brief_id": brief_id,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
        "readiness_score": float(brief.get("readiness_score") or 0.0),
    }

    if not request.dry_run and not publisher.has_auth:
        message = (
            "HUBSPOT_ACCESS_TOKEN is required for live HubSpot deal publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="hubspot_deal",
            target_url=redact_url(publisher.deal_endpoint),
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish_design_brief(
            brief,
            markdown=markdown,
            deal_name=title,
            amount=request.amount,
            close_date=request.close_date,
            dry_run=request.dry_run,
        )
    except HubSpotDealPublishError as exc:
        target_url = redact_url(publisher.deal_endpoint)
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="hubspot_deal",
            target_url=target_url,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "attempts": exc.attempts,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    result.payload["design_brief"] = {
        "id": brief_id,
        "title": title,
        "markdown": markdown,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
    }
    result.payload["metadata"] = {
        **result.payload.get("metadata", {}),
        "design_brief_id": brief_id,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
        "readiness_score": float(brief.get("readiness_score") or 0.0),
    }

    target_url = result.deal_url or result.deal_id or redact_url(publisher.deal_endpoint)
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="hubspot_deal",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    provider_metadata.update(
        {
            "target_url": target_url,
            "deal_id": result.deal_id,
            "deal_url": result.deal_url,
            "pipeline_id": publisher.pipeline_id,
            "deal_stage_id": publisher.deal_stage_id,
        }
    )

    return DesignBriefHubSpotDealPublishResponse(
        design_brief_id=brief_id,
        deal_id=result.deal_id,
        deal_url=result.deal_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        attempts=result.attempts,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/trello",
    response_model=DesignBriefTrelloCardPublishResponse,
)
def publish_design_brief_to_trello_card(
    brief_id: str,
    request: DesignBriefTrelloCardPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefTrelloCardPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    try:
        publisher = TrelloCardPublisher.from_env(
            list_id=request.list_id,
            key=request.key,
            token=request.token,
            api_url=request.api_url,
            labels=request.labels,
            member_ids=request.member_ids,
            due=request.due,
            position=request.position,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except TrelloCardPublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request_summary = {
        "list_id": publisher.list_id,
        "labels": list(request.labels),
        "member_ids": list(request.member_ids),
        "due": request.due,
        "position": request.position,
        "dry_run": request.dry_run,
        "timeout": request.timeout,
        "max_retries": request.max_retries,
        "key": "[redacted]" if publisher.key else None,
        "key_source": "request"
        if request.key
        else ("env:TRELLO_KEY" if os.getenv("TRELLO_KEY") else "none"),
        "token": "[redacted]" if publisher.token else None,
        "token_source": "request"
        if request.token
        else ("env:TRELLO_TOKEN" if os.getenv("TRELLO_TOKEN") else "none"),
    }
    provider_metadata = {
        "provider": "trello",
        "target_type": "trello_card",
        "target_url": publisher.card_endpoint,
        "card_endpoint": publisher.card_endpoint,
        "design_brief_id": brief_id,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
        "readiness_score": float(brief.get("readiness_score") or 0.0),
    }

    payload = _design_brief_trello_spec(brief)
    if not request.dry_run and not publisher.has_auth:
        message = (
            "TRELLO_KEY and TRELLO_TOKEN are required for live Trello card publishing; "
            "use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="trello_card",
            target_url=publisher.card_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except TrelloCardPublishError as exc:
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="trello_card",
            target_url=publisher.card_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    target_url = result.card_url or result.card_id or publisher.card_endpoint
    attempt = store.insert_publication_attempt(
        idea_id=brief_id,
        target_type="trello_card",
        target_url=target_url,
        status="success",
        response_status=result.status_code,
    )
    provider_metadata["target_url"] = target_url
    result_metadata = result.payload.get("metadata", {})
    provider_metadata["trello_card_id"] = result_metadata.get("trello_card_id")
    provider_metadata["trello_card_url"] = result_metadata.get("trello_card_url")

    return DesignBriefTrelloCardPublishResponse(
        design_brief_id=brief_id,
        list_id=result.list_id,
        card_id=result.card_id,
        card_url=result.card_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**attempt),
    )


@router.post(
    "/design-briefs/{brief_id}/publish/azure-devops",
    response_model=DesignBriefAzureDevOpsWorkItemPublishResponse,
)
def publish_design_brief_to_azure_devops_work_item(
    brief_id: str,
    request: DesignBriefAzureDevOpsWorkItemPublishRequest,
    store: Store = Depends(get_store),
) -> DesignBriefAzureDevOpsWorkItemPublishResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    token_source = "request" if request.personal_access_token else "none"
    if not request.personal_access_token:
        if os.getenv("AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN"):
            token_source = "env:AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN"
        elif os.getenv("AZURE_DEVOPS_PAT"):
            token_source = "env:AZURE_DEVOPS_PAT"

    request_summary: dict[str, Any] = {
        "organization": request.organization or os.getenv("AZURE_DEVOPS_ORGANIZATION"),
        "project": request.project or os.getenv("AZURE_DEVOPS_PROJECT"),
        "work_item_type": request.work_item_type
        or os.getenv("AZURE_DEVOPS_WORK_ITEM_TYPE", "User Story"),
        "area_path": request.area_path or os.getenv("AZURE_DEVOPS_AREA_PATH"),
        "iteration_path": request.iteration_path or os.getenv("AZURE_DEVOPS_ITERATION_PATH"),
        "tags": list(request.tags),
        "title": request.title,
        "include_source_ids": request.include_source_ids,
        "dry_run": request.dry_run,
        "timeout": request.timeout,
        "max_retries": request.max_retries,
        "personal_access_token": "[redacted]" if request.personal_access_token else None,
        "personal_access_token_source": token_source,
    }

    try:
        publisher = AzureDevOpsWorkItemPublisher.from_env(
            organization=request.organization,
            project=request.project,
            personal_access_token=request.personal_access_token,
            work_item_type=request.work_item_type,
            area_path=request.area_path,
            iteration_path=request.iteration_path,
            tags=request.tags,
            timeout=request.timeout,
            max_retries=request.max_retries,
        )
    except AzureDevOpsWorkItemPublishError as exc:
        message = _redact_azure_devops_token(str(exc), request.personal_access_token)
        if not request.dry_run:
            attempt = store.insert_publication_attempt(
                idea_id=brief_id,
                target_type="azure_devops_work_item",
                status="failure",
                error=message,
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "message": message,
                    "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                    "request_summary": request_summary,
                },
            ) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    request_summary.update(
        {
            "organization": publisher.organization,
            "project": publisher.project,
            "work_item_type": publisher.work_item_type,
            "area_path": publisher.area_path,
            "iteration_path": publisher.iteration_path,
            "tags": list(publisher.tags),
            "personal_access_token": "[redacted]" if publisher.personal_access_token else None,
        }
    )

    title = request.title or str(brief.get("title") or brief_id)
    markdown = _deterministic_design_brief_markdown(brief, title=title)
    if request.include_source_ids:
        markdown = _append_design_brief_source_ids(markdown, brief)
    payload = _design_brief_azure_devops_spec(brief, title=title, markdown=markdown)
    provider_metadata = {
        "provider": "azure_devops",
        "source_type": "design_brief",
        "target_type": "azure_devops_work_item",
        "target_url": publisher.work_item_endpoint,
        "work_item_endpoint": publisher.work_item_endpoint,
        "design_brief_id": brief_id,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
    }

    if not request.dry_run and not publisher.has_auth:
        message = (
            "AZURE_DEVOPS_PAT or AZURE_DEVOPS_PERSONAL_ACCESS_TOKEN is required for live "
            "Azure DevOps work item publishing; use dry_run to preview"
        )
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="azure_devops_work_item",
            target_url=publisher.work_item_endpoint,
            status="failure",
            error=message,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        )

    try:
        result = publisher.publish(payload, dry_run=request.dry_run)
    except AzureDevOpsWorkItemPublishError as exc:
        message = _redact_azure_devops_token(str(exc), publisher.personal_access_token)
        attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="azure_devops_work_item",
            target_url=publisher.work_item_endpoint,
            status="failure",
            response_status=exc.status_code,
            error=message,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": message,
                "publication_attempt": PublicationAttemptResponse(**attempt).model_dump(),
                "request_summary": request_summary,
            },
        ) from exc

    result.payload["design_brief"] = {
        "id": brief_id,
        "title": title,
        "markdown": markdown,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
    }
    result.payload["metadata"] = {
        **result.payload.get("metadata", {}),
        "design_brief_id": brief_id,
        "source_idea_ids": list(brief.get("source_idea_ids") or []),
    }
    publication_attempt = None
    if not result.dry_run:
        target_url = result.work_item_url or publisher.work_item_endpoint
        publication_attempt = store.insert_publication_attempt(
            idea_id=brief_id,
            target_type="azure_devops_work_item",
            target_url=target_url,
            status="success",
            response_status=result.status_code,
        )
        provider_metadata["target_url"] = target_url
    result_metadata = result.payload.get("metadata", {})
    provider_metadata["azure_devops_work_item_id"] = result_metadata.get(
        "azure_devops_work_item_id"
    )
    provider_metadata["azure_devops_work_item_url"] = result_metadata.get(
        "azure_devops_work_item_url"
    )

    return DesignBriefAzureDevOpsWorkItemPublishResponse(
        design_brief_id=brief_id,
        organization=result.organization,
        project=result.project,
        work_item_type=result.work_item_type,
        work_item_id=result.work_item_id,
        work_item_url=result.work_item_url,
        status_code=result.status_code,
        dry_run=result.dry_run,
        payload=result.payload,
        provider_metadata=provider_metadata,
        request_summary=request_summary,
        publication_attempt=PublicationAttemptResponse(**publication_attempt)
        if publication_attempt
        else None,
    )


@router.get(
    "/design-briefs/{brief_id}/validation-plan", response_model=DesignBriefValidationPlanResponse
)
def get_design_brief_validation_plan(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefValidationPlanResponse:
    from max.analysis.design_validation import build_validation_plan

    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefValidationPlanResponse(**build_validation_plan(store, brief))


@router.get("/design-briefs/{brief_id}/validation-plan.md", response_model=None)
def get_design_brief_validation_plan_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    from max.analysis.design_validation import build_validation_plan, render_validation_plan

    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    return Response(
        content=render_validation_plan(build_validation_plan(store, brief), fmt="markdown"),
        media_type="text/markdown",
    )


@router.get(
    "/design-briefs/{brief_id}/evidence-matrix",
    response_model=DesignBriefEvidenceMatrixResponse,
)
def get_design_brief_evidence_matrix(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefEvidenceMatrixResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefEvidenceMatrixResponse(**build_design_brief_evidence_matrix(store, brief))


@router.get("/design-briefs/{brief_id}/evidence-matrix.md", response_model=None)
def get_design_brief_evidence_matrix_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-evidence-matrix.md"
    return Response(
        content=render_design_brief_evidence_matrix(
            build_design_brief_evidence_matrix(store, brief),
            fmt="markdown",
        ),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/risk-register",
    response_model=DesignBriefRiskRegisterResponse,
)
def get_design_brief_risk_register(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefRiskRegisterResponse:
    register = build_design_brief_risk_register(store, brief_id)
    if not register:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefRiskRegisterResponse(**register)


@router.get("/design-briefs/{brief_id}/risk-register.md", response_model=None)
def get_design_brief_risk_register_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    register = build_design_brief_risk_register(store, brief_id)
    if not register:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = (
        f"{_download_filename_part(brief_id)}-"
        f"{_download_filename_part(register['design_brief']['title'])}-risk-register.md"
    )
    return Response(
        content=render_design_brief_risk_register(register, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/launch-checklist",
    response_model=DesignBriefLaunchChecklistResponse,
)
def get_design_brief_launch_checklist(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefLaunchChecklistResponse:
    checklist = build_design_brief_launch_checklist(store, brief_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefLaunchChecklistResponse(**checklist)


@router.get("/design-briefs/{brief_id}/launch-checklist.md", response_model=None)
def get_design_brief_launch_checklist_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    checklist = build_design_brief_launch_checklist(store, brief_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-launch-checklist.md"
    return Response(
        content=render_design_brief_launch_checklist(checklist, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/compliance-checklist",
    response_model=DesignBriefComplianceChecklistResponse,
)
def get_design_brief_compliance_checklist(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefComplianceChecklistResponse:
    checklist = build_design_brief_compliance_checklist(store, brief_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefComplianceChecklistResponse(**checklist)


@router.get("/design-briefs/{brief_id}/compliance-checklist.md", response_model=None)
def get_design_brief_compliance_checklist_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    checklist = build_design_brief_compliance_checklist(store, brief_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = compliance_checklist_filename(checklist["design_brief"], fmt="markdown")
    return Response(
        content=render_design_brief_compliance_checklist(checklist, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/procurement-checklist",
    response_model=DesignBriefProcurementChecklistResponse,
)
def get_design_brief_procurement_checklist(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefProcurementChecklistResponse:
    checklist = build_design_brief_procurement_checklist(store, brief_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefProcurementChecklistResponse(**checklist)


@router.get("/design-briefs/{brief_id}/procurement-checklist.md", response_model=None)
def get_design_brief_procurement_checklist_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    checklist = build_design_brief_procurement_checklist(store, brief_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = procurement_checklist_filename(checklist["design_brief"], fmt="markdown")
    return Response(
        content=render_design_brief_procurement_checklist(checklist, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/raci-matrix",
    response_model=DesignBriefRaciMatrixResponse,
)
def get_design_brief_raci_matrix(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefRaciMatrixResponse:
    matrix = build_design_brief_raci_matrix(store, brief_id)
    if not matrix:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefRaciMatrixResponse(**matrix)


@router.get("/design-briefs/{brief_id}/raci-matrix.md", response_model=None)
def get_design_brief_raci_matrix_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    matrix = build_design_brief_raci_matrix(store, brief_id)
    if not matrix:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = raci_matrix_filename(matrix["design_brief"], fmt="markdown")
    return Response(
        content=render_design_brief_raci_matrix(matrix, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/roadmap",
    response_model=DesignBriefRoadmapResponse,
)
def get_design_brief_roadmap(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefRoadmapResponse:
    roadmap = build_design_brief_roadmap(store, brief_id)
    if not roadmap:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefRoadmapResponse(**roadmap)


@router.get("/design-briefs/{brief_id}/roadmap.md", response_model=None)
def get_design_brief_roadmap_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    roadmap = build_design_brief_roadmap(store, brief_id)
    if not roadmap:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-roadmap.md"
    return Response(
        content=render_design_brief_roadmap(roadmap, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/pilot-rollout",
    response_model=DesignBriefPilotRolloutResponse,
)
def get_design_brief_pilot_rollout(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefPilotRolloutResponse:
    rollout = build_design_brief_pilot_rollout(store, brief_id)
    if not rollout:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefPilotRolloutResponse(**rollout)


@router.get("/design-briefs/{brief_id}/pilot-rollout.md", response_model=None)
def get_design_brief_pilot_rollout_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    rollout = build_design_brief_pilot_rollout(store, brief_id)
    if not rollout:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = (
        f"{_download_filename_part(brief_id)}-"
        f"{_download_filename_part(rollout['design_brief']['title'])}-pilot-rollout.md"
    )
    return Response(
        content=render_design_brief_pilot_rollout(rollout, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/prd",
    response_model=DesignBriefPrdResponse,
)
def get_design_brief_prd(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefPrdResponse:
    prd = build_design_brief_prd(store, brief_id)
    if not prd:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefPrdResponse(**prd)


@router.get("/design-briefs/{brief_id}/prd.md", response_model=None)
def get_design_brief_prd_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    prd = build_design_brief_prd(store, brief_id)
    if not prd:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-prd.md"
    return Response(
        content=render_design_brief_prd(prd, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/one-pager",
    response_model=DesignBriefOnePagerResponse,
)
def get_design_brief_one_pager(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefOnePagerResponse:
    one_pager = build_design_brief_one_pager(store, brief_id)
    if not one_pager:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefOnePagerResponse(**one_pager)


@router.get("/design-briefs/{brief_id}/one-pager.md", response_model=None)
def get_design_brief_one_pager_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    one_pager = build_design_brief_one_pager(store, brief_id)
    if not one_pager:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-one-pager.md"
    return Response(
        content=render_design_brief_one_pager(one_pager, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/okrs",
    response_model=DesignBriefOkrsResponse,
)
def get_design_brief_okrs(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefOkrsResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefOkrsResponse(**build_design_brief_okrs(brief))


@router.get("/design-briefs/{brief_id}/okrs.md", response_model=None)
def get_design_brief_okrs_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-okrs.md"
    return Response(
        content=render_design_brief_okrs_markdown(build_design_brief_okrs(brief)),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/success-metrics",
    response_model=DesignBriefSuccessMetricsResponse,
)
def get_design_brief_success_metrics(
    brief_id: str,
    format: Literal["json", "markdown"] = Query("json"),
    store: Store = Depends(get_store),
) -> DesignBriefSuccessMetricsResponse | Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    report = build_design_brief_success_metrics(brief)
    if format == "markdown":
        return _design_brief_success_metrics_markdown_response(brief, report)
    return DesignBriefSuccessMetricsResponse(**report)


@router.get("/design-briefs/{brief_id}/success-metrics.md", response_model=None)
def get_design_brief_success_metrics_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    report = build_design_brief_success_metrics(brief)
    return _design_brief_success_metrics_markdown_response(brief, report)


def _design_brief_success_metrics_markdown_response(
    brief: dict[str, Any],
    report: dict[str, Any],
) -> Response:
    filename = success_metrics_filename(brief, fmt="markdown")
    return Response(
        content=render_design_brief_success_metrics(report, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/instrumentation-plan",
    response_model=DesignBriefInstrumentationPlanResponse,
)
def get_design_brief_instrumentation_plan(
    brief_id: str,
    format: str = Query("json"),
    store: Store = Depends(get_store),
) -> DesignBriefInstrumentationPlanResponse | Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    plan = build_design_brief_instrumentation_plan(brief)
    if format == "json":
        return DesignBriefInstrumentationPlanResponse(**plan)
    return _design_brief_instrumentation_plan_rendered_response(plan, fmt=format)


@router.get("/design-briefs/{brief_id}/instrumentation-plan.md", response_model=None)
def get_design_brief_instrumentation_plan_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    plan = build_design_brief_instrumentation_plan(brief)
    return _design_brief_instrumentation_plan_rendered_response(plan, fmt="markdown")


def _design_brief_instrumentation_plan_rendered_response(
    plan: dict[str, Any],
    *,
    fmt: str,
) -> Response:
    try:
        content = render_design_brief_instrumentation_plan(plan, fmt=fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_type = "application/json" if fmt == "json" else "text/markdown"
    headers: dict[str, str] = {}
    if fmt == "markdown":
        filename = instrumentation_plan_filename(plan["design_brief"], fmt="markdown")
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=content, media_type=media_type, headers=headers)


@router.get(
    "/design-briefs/{brief_id}/gtm-channel-plan",
    response_model=DesignBriefGtmChannelPlanResponse,
)
def get_design_brief_gtm_channel_plan(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefGtmChannelPlanResponse:
    plan = build_design_brief_gtm_channel_plan(store, brief_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefGtmChannelPlanResponse(**plan)


@router.get("/design-briefs/{brief_id}/gtm-channel-plan.md", response_model=None)
def get_design_brief_gtm_channel_plan_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    plan = build_design_brief_gtm_channel_plan(store, brief_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = gtm_channel_plan_filename(plan["design_brief"], fmt="markdown")
    return Response(
        content=render_design_brief_gtm_channel_plan(plan, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/assumption-ledger",
    response_model=DesignBriefAssumptionLedgerResponse,
)
def get_design_brief_assumption_ledger(
    brief_id: str,
    format: str = Query("json"),
    store: Store = Depends(get_store),
) -> DesignBriefAssumptionLedgerResponse | Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    ledger = build_design_brief_assumption_ledger(brief)
    if format == "json":
        return DesignBriefAssumptionLedgerResponse(**ledger)
    return _design_brief_assumption_ledger_rendered_response(ledger, fmt=format)


@router.get("/design-briefs/{brief_id}/assumption-ledger.md", response_model=None)
def get_design_brief_assumption_ledger_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    ledger = build_design_brief_assumption_ledger(brief)
    return _design_brief_assumption_ledger_rendered_response(ledger, fmt="markdown")


def _design_brief_assumption_ledger_rendered_response(
    ledger: dict[str, Any],
    *,
    fmt: str,
) -> Response:
    try:
        content = render_design_brief_assumption_ledger(ledger, fmt=fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_type = "application/json" if fmt == "json" else "text/markdown"
    headers: dict[str, str] = {}
    if fmt == "markdown":
        filename = assumption_ledger_filename(ledger["design_brief"], fmt="markdown")
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=content, media_type=media_type, headers=headers)


@router.get(
    "/design-briefs/{brief_id}/retention-policy",
    response_model=DesignBriefRetentionPolicyResponse,
)
def get_design_brief_retention_policy(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefRetentionPolicyResponse:
    policy = build_design_brief_retention_policy(store, brief_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefRetentionPolicyResponse(**policy)


@router.get("/design-briefs/{brief_id}/retention-policy.md", response_model=None)
def get_design_brief_retention_policy_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    policy = build_design_brief_retention_policy(store, brief_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = retention_policy_filename(policy["design_brief"], fmt="markdown")
    return Response(
        content=render_design_brief_retention_policy(policy, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/stakeholder-map",
    response_model=DesignBriefStakeholderMapResponse,
)
def get_design_brief_stakeholder_map(
    brief_id: str,
    format: Literal["json", "markdown"] = Query("json"),
    store: Store = Depends(get_store),
) -> DesignBriefStakeholderMapResponse | Response:
    report = build_design_brief_stakeholder_map(store, brief_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    if format == "markdown":
        return _design_brief_stakeholder_map_markdown_response(report)
    return DesignBriefStakeholderMapResponse(**report)


@router.get("/design-briefs/{brief_id}/stakeholder-map.md", response_model=None)
def get_design_brief_stakeholder_map_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    report = build_design_brief_stakeholder_map(store, brief_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return _design_brief_stakeholder_map_markdown_response(report)


def _design_brief_stakeholder_map_markdown_response(report: dict[str, Any]) -> Response:
    filename = stakeholder_map_filename(report["design_brief"], fmt="markdown")
    return Response(
        content=render_design_brief_stakeholder_map(report, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/technical-feasibility",
    response_model=DesignBriefTechnicalFeasibilityResponse,
)
def get_design_brief_technical_feasibility(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefTechnicalFeasibilityResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    report = build_design_brief_technical_feasibility(brief)
    return DesignBriefTechnicalFeasibilityResponse(**report)


@router.get("/design-briefs/{brief_id}/technical-feasibility.md", response_model=None)
def get_design_brief_technical_feasibility_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    report = build_design_brief_technical_feasibility(brief)
    filename = technical_feasibility_filename(brief, fmt="markdown")
    return Response(
        content=render_design_brief_technical_feasibility(report, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/pricing-strategy",
    response_model=DesignBriefPricingStrategyResponse,
)
def get_design_brief_pricing_strategy(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefPricingStrategyResponse:
    report = build_design_brief_pricing_strategy(store, brief_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefPricingStrategyResponse(**report)


@router.get("/design-briefs/{brief_id}/pricing-strategy.md", response_model=None)
def get_design_brief_pricing_strategy_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    report = build_design_brief_pricing_strategy(store, brief_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = pricing_strategy_filename(report["design_brief"], fmt="markdown")
    return Response(
        content=render_design_brief_pricing_strategy(report, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/support-playbook",
    response_model=DesignBriefSupportPlaybookResponse,
)
def get_design_brief_support_playbook(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefSupportPlaybookResponse:
    playbook = build_design_brief_support_playbook(store, brief_id)
    if not playbook:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefSupportPlaybookResponse(**playbook)


@router.get("/design-briefs/{brief_id}/support-playbook.md", response_model=None)
def get_design_brief_support_playbook_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    playbook = build_design_brief_support_playbook(store, brief_id)
    if not playbook:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-support-playbook.md"
    return Response(
        content=render_design_brief_support_playbook(playbook, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/buyer-faq",
    response_model=DesignBriefBuyerFaqResponse,
)
def get_design_brief_buyer_faq(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefBuyerFaqResponse:
    faq = build_design_brief_buyer_faq(store, brief_id)
    if not faq:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefBuyerFaqResponse(**faq)


@router.get("/design-briefs/{brief_id}/buyer-faq.md", response_model=None)
def get_design_brief_buyer_faq_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    faq = build_design_brief_buyer_faq(store, brief_id)
    if not faq:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-buyer-faq.md"
    return Response(
        content=render_design_brief_buyer_faq(faq, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/sales-battlecard",
    response_model=DesignBriefSalesBattlecardResponse,
)
def get_design_brief_sales_battlecard(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefSalesBattlecardResponse:
    battlecard = build_design_brief_sales_battlecard(store, brief_id)
    if not battlecard:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefSalesBattlecardResponse(**battlecard)


@router.get("/design-briefs/{brief_id}/sales-battlecard.md", response_model=None)
def get_design_brief_sales_battlecard_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    battlecard = build_design_brief_sales_battlecard(store, brief_id)
    if not battlecard:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-sales-battlecard.md"
    return Response(
        content=render_design_brief_sales_battlecard(battlecard, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/outreach-pack",
    response_model=DesignBriefOutreachPackResponse,
)
def get_design_brief_outreach_pack(
    brief_id: str,
    format: Literal["json", "markdown"] = Query("json"),
    store: Store = Depends(get_store),
) -> DesignBriefOutreachPackResponse | Response:
    pack = build_design_brief_outreach_pack(store, brief_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    if format == "markdown":
        return _design_brief_outreach_pack_markdown_response(pack)
    return DesignBriefOutreachPackResponse(**pack)


@router.get("/design-briefs/{brief_id}/outreach-pack.md", response_model=None)
def get_design_brief_outreach_pack_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    pack = build_design_brief_outreach_pack(store, brief_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return _design_brief_outreach_pack_markdown_response(pack)


def _design_brief_outreach_pack_markdown_response(pack: dict[str, Any]) -> Response:
    filename = f"{_download_filename_part(pack['design_brief']['id'])}-outreach-pack.md"
    return Response(
        content=render_design_brief_outreach_pack(pack, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/executive-memo",
    response_model=DesignBriefExecutiveMemoResponse,
)
def get_design_brief_executive_memo(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefExecutiveMemoResponse:
    memo = build_design_brief_executive_memo(store, brief_id)
    if not memo:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefExecutiveMemoResponse(**memo)


@router.get("/design-briefs/{brief_id}/executive-memo.md", response_model=None)
def get_design_brief_executive_memo_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    memo = build_design_brief_executive_memo(store, brief_id)
    if not memo:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = f"{_download_filename_part(brief_id)}-executive-memo.md"
    return Response(
        content=render_design_brief_executive_memo(memo, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/competitive-landscape",
    response_model=DesignBriefCompetitiveLandscapeResponse,
)
def get_design_brief_competitive_landscape(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefCompetitiveLandscapeResponse:
    report = build_design_brief_competitive_landscape(store, brief_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefCompetitiveLandscapeResponse(**report)


@router.get("/design-briefs/{brief_id}/competitive-landscape.md", response_model=None)
def get_design_brief_competitive_landscape_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    report = build_design_brief_competitive_landscape(store, brief_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    filename = (
        f"{_download_filename_part(brief_id)}-"
        f"{_download_filename_part(report['design_brief']['title'])}-competitive-landscape.md"
    )
    return Response(
        content=render_design_brief_competitive_landscape(report, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/design-briefs/{brief_id}/market-sizing",
    response_model=DesignBriefMarketSizingResponse,
)
def get_design_brief_market_sizing(
    brief_id: str,
    store: Store = Depends(get_store),
) -> DesignBriefMarketSizingResponse:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")
    return DesignBriefMarketSizingResponse(**build_market_sizing_report(store, brief))


@router.get("/design-briefs/{brief_id}/market-sizing.md", response_model=None)
def get_design_brief_market_sizing_markdown(
    brief_id: str,
    store: Store = Depends(get_store),
) -> Response:
    brief = store.get_design_brief(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail=f"Design brief not found: {brief_id}")

    report = build_market_sizing_report(store, brief)
    filename = market_sizing_filename(report["design_brief"], fmt="markdown")
    return Response(
        content=render_market_sizing_report(report, fmt="markdown"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
            getattr(result, score_field) * getattr(result, weight_field) for result in results
        )
        weights = total(weight_field)
        return weighted_total / weights if weights else 0.0

    token_usage: dict[str, int] = {}
    for result in results:
        for key, value in result.token_usage.items():
            token_usage[key] = token_usage.get(key, 0) + value

    top_ideas = [idea for result in results for idea in result.top_ideas]
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
        avg_insight_confidence=weighted_average("avg_insight_confidence", "insights_generated"),
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
        )
        if profile
        else None,
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
    profile: str | None = Query(
        default=None, description="Optional profile name for enabled sources"
    ),
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


@router.get("/fetch/allocation-simulation", response_model=FetchAllocationSimulationResponse)
def get_fetch_allocation_simulation(
    profile: str | None = Query(
        default=None,
        description="Optional profile name to simulate; defaults to MAX_PROFILE or devtools",
    ),
    budget: int | None = Query(
        default=None,
        description="Optional total fetch signal budget to simulate",
    ),
    store: Store = Depends(get_store),
) -> FetchAllocationSimulationResponse:
    from max.analysis.source_simulation import simulate_source_allocation
    from max.config import MAX_PROFILE
    from max.profiles.loader import get_default_profile, load_profile

    if budget is not None and budget < 1:
        raise HTTPException(status_code=400, detail="budget must be at least 1")

    profile_name = profile or MAX_PROFILE or None
    try:
        pipeline_profile = load_profile(profile_name) if profile_name else get_default_profile()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")

    try:
        report = simulate_source_allocation(pipeline_profile, store, budget=budget)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FetchAllocationSimulationResponse.model_validate(report.to_dict())


# ── Similarity ──────────────────────────────────────────────────────


@router.post("/similar", response_model=list[SimilarityResult])
def find_similar(
    body: SimilarityRequest, store: Store = Depends(get_store)
) -> list[SimilarityResult]:
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
        max_execution_seconds=body.max_execution_seconds,
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
