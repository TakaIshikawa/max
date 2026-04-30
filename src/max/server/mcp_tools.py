"""MCP tools and resources for the max idea service."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fastapi import FastAPI

try:
    from fastmcp import FastMCP
except ModuleNotFoundError:  # pragma: no cover - fallback for offline test envs
    class FastMCP:  # type: ignore[no-redef]
        """Minimal FastMCP stand-in used when the optional dependency is absent."""

        def __init__(self, name: str):
            self.name = name
            self._tools: list[Callable] = []
            self._resources: list[tuple[str, Callable]] = []

        def tool(self, fn=None, *args, **kwargs):
            if fn is None:
                def decorator(inner_fn):
                    self._tools.append(inner_fn)
                    return inner_fn

                return decorator
            self._tools.append(fn)
            return fn

        def resource(self, path: str):
            def decorator(fn):
                self._resources.append((path, fn))
                return fn

            return decorator

        def http_app(self, path: str = "/mcp"):
            return FastAPI(title=self.name)

from max import config
from max.analysis.architecture_enforcement import (
    DEFAULT_UNIT_LIMIT as DEFAULT_ARCHITECTURE_ENFORCEMENT_UNIT_LIMIT,
    build_architecture_enforcement_report,
)
from max.analysis.blast_radius import estimate_idea_blast_radius
from max.analysis.budget_usage import build_llm_budget_usage
from max.analysis.context_budget import build_context_budget_waste_report
from max.analysis.cost_anomalies import build_cost_anomaly_report
from max.analysis.design_brief_evidence_matrix import (
    build_design_brief_evidence_matrix,
    render_design_brief_evidence_matrix,
)
from max.analysis.design_brief_bundle import (
    build_design_brief_bundle,
    render_design_brief_bundle,
)
from max.analysis.design_brief_pricing_strategy import (
    build_design_brief_pricing_strategy,
    render_design_brief_pricing_strategy,
)
from max.analysis.evaluation_calibration import build_evaluation_calibration_report
from max.analysis.mcp_capability_coverage import (
    DEFAULT_LIMIT_REPRESENTATIVES as DEFAULT_MCP_CAPABILITY_LIMIT_REPRESENTATIVES,
    DEFAULT_MIN_COUNT as DEFAULT_MCP_CAPABILITY_MIN_COUNT,
    build_mcp_capability_coverage_report,
)
from max.analysis.opportunity_heatmap import build_opportunity_heatmap
from max.analysis.pipeline_replay import PipelineReplayRunNotFound, build_pipeline_replay_plan
from max.analysis.pipeline_cost_anomalies import (
    DEFAULT_BASELINE_WINDOW as DEFAULT_COST_ANOMALY_BASELINE_WINDOW,
    DEFAULT_LIMIT as DEFAULT_COST_ANOMALY_LIMIT,
    DEFAULT_MIN_COST_USD as DEFAULT_COST_ANOMALY_MIN_COST_USD,
    DEFAULT_MULTIPLIER_THRESHOLD as DEFAULT_COST_ANOMALY_MULTIPLIER_THRESHOLD,
    build_pipeline_cost_anomaly_report,
)
from max.analysis.profile_drift import (
    DEFAULT_LOOKBACK_DAYS as DEFAULT_PROFILE_DRIFT_LOOKBACK_DAYS,
    DEFAULT_MIN_SIGNALS as DEFAULT_PROFILE_DRIFT_MIN_SIGNALS,
    build_profile_drift_report,
)
from max.analysis.run_comparison import (
    PipelineRunComparisonNotFound,
    compare_pipeline_runs as build_pipeline_run_comparison,
)
from max.analysis.roi_forecast import generate_roi_forecast
from max.analysis.thresholds import (
    DEFAULT_APPROVE_THRESHOLD,
    DEFAULT_MIN_SAMPLES as DEFAULT_THRESHOLD_MIN_SAMPLES,
    DEFAULT_REJECT_THRESHOLD,
    recommend_review_thresholds,
)
from max.analysis.validation_experiment_summary import (
    build_validation_experiment_summary,
)
from max.server.errors import (
    ExternalServiceError,
    MCPToolError,
    ResourceNotFoundError,
    ValidationError,
)
from max.server.evidence_chain import build_evidence_chain_graph
from max.server.schemas import (
    ArchitectureEnforcementResponse,
    CostAnomalyReportResponse,
    ContextBudgetWasteResponse,
    LLMBudgetUsageResponse,
    PipelineCostAnomalyReportResponse,
    PipelineRunComparisonResponse,
    PipelineReplayPlanResponse,
    ValidationExperimentCreate,
    ValidationExperimentUpdate,
)
from max.store.db import Store

try:
    from pydantic import ValidationError as PydanticValidationError
except ImportError:  # pragma: no cover - pydantic is a required runtime dependency
    PydanticValidationError = ValueError  # type: ignore[misc,assignment]

if TYPE_CHECKING:
    from max.server.scheduler import Scheduler

# Module-level store factory — overridable for testing
def _default_store_factory() -> Store:
    return Store(wal_mode=True)


_store_factory: Callable[[], Store] = _default_store_factory

# Module-level scheduler reference (set during lifespan)
_scheduler: Scheduler | None = None

_CONTEXT_BUDGET_HIGH_WASTE_RATE_THRESHOLD = 0.5
_CONTEXT_BUDGET_OVERSIZED_CONTEXT_SHARE_THRESHOLD = 0.5
_MCP_CAPABILITY_COVERAGE_SCHEMA_VERSION = "1.0"


def set_store_factory(factory: Callable[[], Store]) -> None:
    """Override the store factory (used in tests)."""
    global _store_factory
    _store_factory = factory


def set_scheduler_ref(scheduler: Scheduler | None) -> None:
    """Set the scheduler reference for MCP tools."""
    global _scheduler
    _scheduler = scheduler


def _get_store() -> Store:
    return _store_factory()


def _add_llm_budget_indicators(report: dict) -> dict:
    """Add MCP-friendly warning and exceeded flags to a budget usage report."""
    total_tokens = int(report.get("total_tokens") or 0)
    total_cost = float(report.get("total_cost_usd") or 0.0)
    token_budget = int(report.get("token_budget") or config.MAX_TOKEN_BUDGET)
    cost_budget = float(report.get("cost_budget_usd") or config.MAX_COST_BUDGET)

    token_warning = token_budget > 0 and total_tokens >= token_budget * 0.8
    cost_warning = cost_budget > 0 and total_cost >= cost_budget * 0.8
    token_exceeded = token_budget > 0 and total_tokens > token_budget
    cost_exceeded = cost_budget > 0 and total_cost > cost_budget

    report["token_budget_warning"] = token_warning
    report["cost_budget_warning"] = cost_warning
    report["budget_warning"] = token_warning or cost_warning
    report["token_budget_exceeded"] = token_exceeded
    report["cost_budget_exceeded"] = cost_exceeded
    report["budget_exceeded"] = token_exceeded or cost_exceeded
    return report


def _add_pipeline_cost_anomaly_warnings(report: dict) -> dict:
    """Add explicit MCP warning fields to anomalous run rows."""
    for anomaly in report.get("anomalies", []):
        if not isinstance(anomaly, dict):
            continue
        reasons = list(anomaly.get("anomaly_reasons") or [])
        anomaly["cost_anomaly_warning"] = True
        anomaly["warning_reasons"] = reasons
        anomaly["warning"] = "; ".join(str(reason) for reason in reasons)
    report["has_cost_anomaly_warnings"] = bool(report.get("anomaly_count"))
    return report


def _add_context_budget_waste_warnings(report: dict, *, adapter_limit: int) -> dict:
    """Add MCP-friendly warning booleans to context budget waste rows."""
    total_tokens = int(report.get("total_estimated_tokens") or 0)
    report_high_waste = (
        float(report.get("low_utility_signal_rate") or 0.0)
        >= _CONTEXT_BUDGET_HIGH_WASTE_RATE_THRESHOLD
        or float(report.get("stale_signal_rate") or 0.0)
        >= _CONTEXT_BUDGET_HIGH_WASTE_RATE_THRESHOLD
    )

    has_adapter_high_waste = False
    has_oversized_contributor = False
    for adapter in report.get("adapters", []):
        if not isinstance(adapter, dict):
            continue
        low_utility_rate = float(adapter.get("low_utility_rate") or 0.0)
        stale_rate = float(adapter.get("stale_rate") or 0.0)
        estimated_tokens = int(adapter.get("estimated_tokens") or 0)
        token_share = round(estimated_tokens / total_tokens, 3) if total_tokens else 0.0
        high_waste_warning = (
            low_utility_rate >= _CONTEXT_BUDGET_HIGH_WASTE_RATE_THRESHOLD
            or stale_rate >= _CONTEXT_BUDGET_HIGH_WASTE_RATE_THRESHOLD
        )
        oversized_warning = (
            total_tokens > 0
            and token_share >= _CONTEXT_BUDGET_OVERSIZED_CONTEXT_SHARE_THRESHOLD
        )
        warning_reasons = list(adapter.get("reasons") or [])
        if oversized_warning:
            warning_reasons.append(
                "adapter contributes at least 50% of estimated context tokens"
            )

        adapter["context_token_share"] = token_share
        adapter["high_waste_warning"] = high_waste_warning
        adapter["oversized_context_contributor_warning"] = oversized_warning
        adapter["warning_reasons"] = warning_reasons
        adapter["warning"] = high_waste_warning or oversized_warning
        has_adapter_high_waste = has_adapter_high_waste or high_waste_warning
        has_oversized_contributor = has_oversized_contributor or oversized_warning

    report["adapter_limit"] = adapter_limit
    report["high_waste_warning"] = report_high_waste or has_adapter_high_waste
    report["oversized_context_contributor_warning"] = has_oversized_contributor
    report["has_context_budget_waste_warnings"] = (
        report["high_waste_warning"] or report["oversized_context_contributor_warning"]
    )
    report["adapters"] = list(report.get("adapters", []))[:adapter_limit]
    return report


def _mcp_capability_gap_severity(total_count: int, min_count: int) -> str:
    if total_count >= min_count:
        return "none"
    if total_count == 0:
        return "critical"
    if total_count < max(1, min_count // 2):
        return "high"
    return "medium"


def _signal_reference(signal) -> dict:
    return {
        "id": signal.id,
        "title": signal.title,
        "source_adapter": signal.source_adapter,
        "source_type": str(signal.source_type),
        "url": signal.url,
        "tags": signal.tags,
    }


def _mcp_capability_report_payload(report, store: Store) -> dict:
    payload = report.to_dict()
    representative_ids = {
        signal_id
        for category in payload["categories"]
        for signal_id in category["representative_signal_ids"]
    }
    signals_by_id = {
        signal_id: _signal_reference(signal)
        for signal_id in representative_ids
        if (signal := store.get_signal(signal_id)) is not None
    }

    capability_buckets = []
    gap_counts = {}
    for category in payload["categories"]:
        total_count = int(category["total_count"])
        gap_count = max(0, int(report.min_count) - total_count)
        severity = _mcp_capability_gap_severity(total_count, int(report.min_count))
        representative_signals = [
            signals_by_id[signal_id]
            for signal_id in category["representative_signal_ids"]
            if signal_id in signals_by_id
        ]
        gap_counts[category["category"]] = gap_count
        capability_buckets.append(
            {
                **category,
                "representative_signals": representative_signals,
                "gap_count": gap_count,
                "gap_severity": severity,
                "undercovered": gap_count > 0,
            }
        )

    payload["schema_version"] = _MCP_CAPABILITY_COVERAGE_SCHEMA_VERSION
    payload["capability_buckets"] = capability_buckets
    payload["categories"] = capability_buckets
    payload["gap_counts"] = gap_counts
    payload["gap_summary"] = {
        "critical": sum(
            1 for bucket in capability_buckets if bucket["gap_severity"] == "critical"
        ),
        "high": sum(
            1 for bucket in capability_buckets if bucket["gap_severity"] == "high"
        ),
        "medium": sum(
            1 for bucket in capability_buckets if bucket["gap_severity"] == "medium"
        ),
        "none": sum(
            1 for bucket in capability_buckets if bucket["gap_severity"] == "none"
        ),
    }
    return payload


def _review_metadata(unit, latest_feedback: dict | None = None) -> dict:
    """Return explicit review fields for graph/MCP consumers."""
    outcome = latest_feedback["outcome"] if latest_feedback else None
    state = outcome or unit.status or "pending"
    if state == "evaluated":
        state = "pending_review"
    graph_state = "".join(part.capitalize() for part in state.replace("-", "_").split("_"))
    return {
        "review_state": state,
        "feedback_outcome": outcome,
        "feedback_reason": latest_feedback["reason"] if latest_feedback else "",
        "reviewed_at": latest_feedback["created_at"] if latest_feedback else None,
        "graph_labels": ["Idea", f"Review{graph_state}"],
        "is_approved": state in ("approved", "published"),
    }


# ── Tool functions (callable directly for testing) ──────────────────


def search_ideas(
    query: str | None = None,
    category: str | None = None,
    domain: str | None = None,
    min_score: float | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search and filter ideas from the max idea engine.

    Returns a list of ideas with their scores and recommendations.
    Use query to filter by title/description keywords.
    Use category to filter by type (mcp_server, cli_tool, library, etc).
    Use domain to filter by pipeline profile domain (e.g. 'healthcare', 'fintech').
    Use min_score to only get ideas above a certain evaluation score.
    """
    with _get_store() as store:
        units = store.get_buildable_units(limit=limit * 3, domain=domain)
        results = []
        for unit in units:
            if category and unit.category != category:
                continue
            if query and query.lower() not in (unit.title + " " + unit.one_liner).lower():
                continue
            evaluation = store.get_evaluation(unit.id)
            if min_score is not None and (evaluation is None or evaluation.overall_score < min_score):
                continue
            results.append({
                "id": unit.id,
                "title": unit.title,
                "one_liner": unit.one_liner,
                "category": unit.category,
                "domain": unit.domain,
                "status": unit.status,
                **_review_metadata(unit, store.get_latest_feedback(unit.id)),
                "target_users": unit.target_users,
                "specific_user": unit.specific_user,
                "buyer": unit.buyer,
                "workflow_context": unit.workflow_context,
                "quality_score": unit.quality_score,
                "novelty_score": unit.novelty_score,
                "usefulness_score": unit.usefulness_score,
                "rejection_tags": unit.rejection_tags,
                "score": evaluation.overall_score if evaluation else None,
                "recommendation": evaluation.recommendation if evaluation else None,
            })
            if len(results) >= limit:
                break
        return results


def get_idea(id: str) -> dict:
    """Get detailed information about a specific idea including its evaluation.

    Returns the full idea with problem/solution, evaluation scores, strengths/weaknesses.

    Raises:
        ResourceNotFoundError: If the idea does not exist.
    """
    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )
            evaluation = store.get_evaluation(id)
            result = {
                "id": unit.id,
                "title": unit.title,
                "one_liner": unit.one_liner,
                "category": unit.category,
                "domain": unit.domain,
                "problem": unit.problem,
                "solution": unit.solution,
                "target_users": unit.target_users,
                "value_proposition": unit.value_proposition,
                "specific_user": unit.specific_user,
                "buyer": unit.buyer,
                "workflow_context": unit.workflow_context,
                "current_workaround": unit.current_workaround,
                "why_now": unit.why_now,
                "validation_plan": unit.validation_plan,
                "first_10_customers": unit.first_10_customers,
                "domain_risks": unit.domain_risks,
                "evidence_rationale": unit.evidence_rationale,
                "quality_score": unit.quality_score,
                "novelty_score": unit.novelty_score,
                "usefulness_score": unit.usefulness_score,
                "rejection_tags": unit.rejection_tags,
                "tech_approach": unit.tech_approach,
                "status": unit.status,
                **_review_metadata(unit, store.get_latest_feedback(id)),
            }
            critiques = store.get_idea_critiques(id)
            if critiques:
                result["latest_critique"] = critiques[0]
            if evaluation:
                result["evaluation"] = {
                    "overall_score": evaluation.overall_score,
                    "recommendation": evaluation.recommendation,
                    "strengths": evaluation.strengths,
                    "weaknesses": evaluation.weaknesses,
                    "dimensions": {
                        name: {"value": getattr(evaluation, name).value, "reasoning": getattr(evaluation, name).reasoning}
                        for name in [
                            "pain_severity", "addressable_scale", "build_effort",
                            "composability", "competitive_density", "timing_fit", "compounding_value",
                        ]
                    },
                }
            return result
    except (ResourceNotFoundError, ValidationError, ExternalServiceError) as e:
        return e.to_dict()


def get_spec_preview(id: str) -> dict:
    """Generate a tact project spec preview for an evaluated idea.

    Raises:
        ResourceNotFoundError: If the idea or evaluation does not exist.
    """
    from max.spec.generator import generate_spec_preview

    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )

            evaluation = store.get_evaluation(id)
            if not evaluation:
                raise ResourceNotFoundError(
                    f"Evaluation not found for idea: {id}",
                    resource_type="evaluation",
                    resource_id=id,
                    details={"suggestion": "Run evaluate_idea first"},
                )

            return {
                "id": unit.id,
                "title": unit.title,
                "one_liner": unit.one_liner,
                "category": unit.category,
                "domain": unit.domain,
                "status": unit.status,
                "score": evaluation.overall_score,
                "recommendation": evaluation.recommendation,
                "preview": generate_spec_preview(unit, evaluation),
            }
    except MCPToolError as e:
        return e.to_dict()


def get_spec_readiness(id: str) -> dict:
    """Evaluate whether an idea is ready for spec handoff.

    Raises:
        ResourceNotFoundError: If the idea or evaluation does not exist.
    """
    from max.spec.readiness import evaluate_spec_readiness

    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )

            evaluation = store.get_evaluation(id)
            if not evaluation:
                raise ResourceNotFoundError(
                    f"Evaluation not found for idea: {id}",
                    resource_type="evaluation",
                    resource_id=id,
                    details={"suggestion": "Run evaluate_idea first"},
                )

            return evaluate_spec_readiness(unit, evaluation)
    except MCPToolError as e:
        return e.to_dict()


def get_implementation_plan(id: str) -> dict:
    """Generate an implementation handoff plan for an evaluated idea.

    Raises:
        ResourceNotFoundError: If the idea or evaluation does not exist.
    """
    from max.spec.generator import generate_spec_preview
    from max.spec.implementation_plan import generate_implementation_plan

    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )

            evaluation = store.get_evaluation(id)
            if not evaluation:
                raise ResourceNotFoundError(
                    f"Evaluation not found for idea: {id}",
                    resource_type="evaluation",
                    resource_id=id,
                    details={"suggestion": "Run evaluate_idea first"},
                )

            spec_preview = generate_spec_preview(unit, evaluation)
            return generate_implementation_plan(unit, evaluation, spec_preview)
    except MCPToolError as e:
        return e.to_dict()


def get_acceptance_criteria(id: str) -> dict:
    """Generate implementation-ready acceptance criteria for an evaluated idea.

    Raises:
        ResourceNotFoundError: If the idea or evaluation does not exist.
    """
    from max.analysis.evidence_density import build_evidence_density_report
    from max.spec.acceptance_criteria import generate_acceptance_criteria

    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )

            evaluation = store.get_evaluation(id)
            if not evaluation:
                raise ResourceNotFoundError(
                    f"Evaluation not found for idea: {id}",
                    resource_type="evaluation",
                    resource_id=id,
                    details={"suggestion": "Run evaluate_idea first"},
                )

            return generate_acceptance_criteria(
                unit,
                evaluation,
                build_evidence_density_report(unit, store),
            )
    except MCPToolError as e:
        return e.to_dict()


def get_blast_radius(id: str) -> dict:
    """Estimate deterministic implementation blast radius for an idea.

    Uses the latest persisted utility evaluation when available, but can still
    estimate blast radius from the idea itself.

    Raises:
        ResourceNotFoundError: If the idea does not exist.
    """
    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )

            evaluation = store.get_evaluation(id)
            estimate = estimate_idea_blast_radius(unit, evaluation)
            return asdict(estimate)
    except MCPToolError as e:
        return e.to_dict()


def get_review_gate_decision(
    idea_id: str,
    approve_threshold: float | None = None,
    reject_threshold: float | None = None,
    min_readiness: float | None = None,
    approve_readiness: float | None = None,
    high_blast_radius: float | None = None,
    medium_blast_radius: float | None = None,
) -> dict:
    """Return the deterministic review gate decision for an idea.

    Optional numeric overrides tune the fallback gate thresholds used when
    historical review thresholds are unavailable.

    Raises:
        ResourceNotFoundError: If the idea does not exist.
    """
    from max.analysis.review_gate import build_review_gate_decision

    profile = {
        key: value
        for key, value in {
            "approve_threshold": approve_threshold,
            "reject_threshold": reject_threshold,
            "min_readiness": min_readiness,
            "approve_readiness": approve_readiness,
            "high_blast_radius": high_blast_radius,
            "medium_blast_radius": medium_blast_radius,
        }.items()
        if value is not None
    }
    try:
        with _get_store() as store:
            return asdict(build_review_gate_decision(store, idea_id, profile=profile))
    except ValueError:
        return ResourceNotFoundError(
            f"Idea not found: {idea_id}",
            resource_type="buildable_unit",
            resource_id=idea_id,
        ).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def get_idea_critique(id: str) -> dict:
    """Get persisted quality-loop critique details for an idea.

    Raises:
        ResourceNotFoundError: If the idea does not exist.
    """
    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )
            critiques = store.get_idea_critiques(id)
            return {"id": id, "critiques": critiques}
    except MCPToolError as e:
        return e.to_dict()


def list_design_briefs(
    domain: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List persisted design briefs from the max portfolio synthesis pipeline.

    Use domain to filter by pipeline profile domain.
    Use status to filter by design workflow status (candidate, designing, etc).
    """
    with _get_store() as store:
        return store.get_design_briefs(domain=domain, status=status, limit=limit)


def get_design_brief(brief_id: str) -> dict:
    """Get a persisted design brief with its source idea relationships.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
    """
    try:
        with _get_store() as store:
            brief = store.get_design_brief(brief_id)
            if not brief:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )
            return brief
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_markdown(brief_id: str) -> dict:
    """Render a persisted design brief as Markdown for design handoff.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
    """
    from max.analysis.portfolio_synthesis import render_design_brief_markdown

    try:
        with _get_store() as store:
            brief = store.get_design_brief(brief_id)
            if not brief:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )
            return {"id": brief_id, "markdown": render_design_brief_markdown(brief)}
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_validation_plan(brief_id: str, format: str = "json") -> dict:
    """Get a deterministic validation plan for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    from max.analysis.design_validation import build_validation_plan, render_validation_plan

    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported validation plan format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            brief = store.get_design_brief(brief_id)
            if not brief:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )
            plan = build_validation_plan(store, brief)

        rendered = render_validation_plan(plan, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_risk_register(brief_id: str, format: str = "json") -> dict:
    """Get a consolidated risk register for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    from max.analysis.design_brief_risk_register import (
        build_design_brief_risk_register,
        render_design_brief_risk_register,
    )

    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported risk register format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            register = build_design_brief_risk_register(store, brief_id)
            if not register:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )

        rendered = render_design_brief_risk_register(register, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_roadmap(brief_id: str, format: str = "json") -> dict:
    """Get a phased roadmap for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    from max.analysis.design_brief_roadmap import (
        build_design_brief_roadmap,
        render_design_brief_roadmap,
    )

    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported roadmap format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            roadmap = build_design_brief_roadmap(store, brief_id)
            if not roadmap:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )

        rendered = render_design_brief_roadmap(roadmap, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_prd(brief_id: str, format: str = "json") -> dict:
    """Get a concise PRD export for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    from max.analysis.design_brief_prd import (
        build_design_brief_prd,
        render_design_brief_prd,
    )

    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported PRD format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            prd = build_design_brief_prd(store, brief_id)
            if not prd:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )

        rendered = render_design_brief_prd(prd, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_executive_memo(brief_id: str, format: str = "json") -> dict:
    """Get an executive memo export for a persisted design brief.

    Set format to "json" for a structured payload with rendered JSON text or
    "markdown" for rendered approval handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    from max.analysis.design_brief_executive_memo import (
        build_design_brief_executive_memo,
        render_design_brief_executive_memo,
    )

    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported executive memo format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            memo = build_design_brief_executive_memo(store, brief_id)
            if not memo:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )

        rendered = render_design_brief_executive_memo(memo, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return {**json.loads(rendered), "format": "json", "rendered": rendered}
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_market_sizing(brief_id: str, format: str = "json") -> dict:
    """Get deterministic market sizing for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    from max.analysis.market_sizing import (
        build_market_sizing_report,
        render_market_sizing_report,
    )

    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported market sizing format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            brief = store.get_design_brief(brief_id)
            if not brief:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )
            report = build_market_sizing_report(store, brief)
            report["evidence_references"] = _design_brief_market_sizing_evidence_references(
                store,
                brief,
            )

        rendered = render_market_sizing_report(report, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_competitive_landscape(brief_id: str, format: str = "json") -> dict:
    """Get competitive landscape analysis for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    from max.analysis.design_brief_competitive_landscape import (
        build_design_brief_competitive_landscape,
        render_design_brief_competitive_landscape,
    )

    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported competitive landscape format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            report = build_design_brief_competitive_landscape(store, brief_id)
            if not report:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )

        rendered = render_design_brief_competitive_landscape(report, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_evidence_matrix(brief_id: str, format: str = "json") -> dict:
    """Get the evidence matrix for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    claim-by-claim handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported evidence matrix format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            brief = store.get_design_brief(brief_id)
            if not brief:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )
            matrix = build_design_brief_evidence_matrix(store, brief)

        rendered = render_design_brief_evidence_matrix(matrix, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_launch_checklist(brief_id: str, format: str = "json") -> dict:
    """Get the launch readiness checklist for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    launch handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    from max.analysis.design_brief_launch_checklist import (
        build_design_brief_launch_checklist,
        render_design_brief_launch_checklist,
    )

    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported launch checklist format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            checklist = build_design_brief_launch_checklist(store, brief_id)
            if not checklist:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )

        rendered = render_design_brief_launch_checklist(checklist, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_pricing_strategy(brief_id: str, format: str = "json") -> dict:
    """Get the pricing strategy for a persisted design brief.

    Set format to "json" for a structured payload or "markdown" for rendered
    pricing handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported pricing strategy format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            strategy = build_design_brief_pricing_strategy(store, brief_id)
            if not strategy:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )

        rendered = render_design_brief_pricing_strategy(strategy, fmt=fmt)
        if fmt == "markdown":
            return {"id": brief_id, "format": "markdown", "markdown": rendered}
        return json.loads(rendered)
    except MCPToolError as e:
        return e.to_dict()


def get_design_brief_bundle(brief_id: str, format: str = "json") -> dict:
    """Get the consolidated handoff bundle for a persisted design brief.

    Set format to "json" for a structured payload with rendered JSON text or
    "markdown" for rendered handoff text.

    Raises:
        ResourceNotFoundError: If the design brief does not exist.
        ValidationError: If the requested format is unsupported.
    """
    try:
        fmt = format.strip().lower()
        if fmt not in {"json", "markdown"}:
            raise ValidationError(
                f"Unsupported design brief bundle format: {format}",
                field="format",
                expected="json or markdown",
                actual=format,
            )

        with _get_store() as store:
            bundle = build_design_brief_bundle(store, brief_id)
            if not bundle:
                raise ResourceNotFoundError(
                    f"Design brief not found: {brief_id}",
                    resource_type="design_brief",
                    resource_id=brief_id,
                )

        rendered = render_design_brief_bundle(bundle, fmt=fmt)
        if fmt == "markdown":
            return {
                "id": brief_id,
                "format": "markdown",
                "markdown": rendered,
                "bundle": bundle,
                "artifact_status": bundle["artifact_status"],
            }
        return {
            **json.loads(rendered),
            "id": brief_id,
            "format": "json",
            "rendered": rendered,
        }
    except MCPToolError as e:
        return e.to_dict()


def _design_brief_market_sizing_evidence_references(store: Store, brief: dict) -> list[dict]:
    """Return source signal references for MCP market-sizing consumers."""
    signal_ids: set[str] = set()
    source_ids = list(
        dict.fromkeys(
            [
                brief.get("lead_idea_id"),
                *list(brief.get("source_idea_ids") or []),
                *[
                    source.get("idea_id")
                    for source in brief.get("sources", [])
                    if source.get("idea_id")
                ],
            ]
        )
    )
    for idea_id in source_ids:
        if not idea_id:
            continue
        idea = store.get_buildable_unit(str(idea_id))
        if not idea:
            continue
        signal_ids.update(str(signal_id) for signal_id in idea.evidence_signals if signal_id)
        for insight_id in idea.inspiring_insights:
            insight = store.get_insight(str(insight_id))
            if insight:
                signal_ids.update(str(signal_id) for signal_id in insight.evidence if signal_id)

    references = []
    for signal_id in sorted(signal_ids):
        signal = store.get_signal(signal_id)
        if not signal:
            continue
        references.append(
            {
                "id": signal.id,
                "title": signal.title,
                "source_type": str(signal.source_type),
                "source_adapter": signal.source_adapter,
                "url": signal.url,
                "signal_role": signal.signal_role,
            }
        )
    return references


def list_validation_experiments(idea_id: str) -> dict:
    """List validation experiments for an idea.

    Raises:
        ResourceNotFoundError: If the idea does not exist.
    """
    try:
        with _get_store() as store:
            experiments = store.list_validation_experiments(idea_id)
            if experiments is None:
                raise ResourceNotFoundError(
                    f"Idea not found: {idea_id}",
                    resource_type="buildable_unit",
                    resource_id=idea_id,
                )
            return {"idea_id": idea_id, "experiments": experiments}
    except MCPToolError as e:
        return e.to_dict()


def get_validation_experiment(experiment_id: str) -> dict:
    """Get one validation experiment by ID.

    Raises:
        ResourceNotFoundError: If the validation experiment does not exist.
    """
    try:
        with _get_store() as store:
            experiment = store.get_validation_experiment(experiment_id)
            if experiment is None:
                raise ResourceNotFoundError(
                    f"Validation experiment not found: {experiment_id}",
                    resource_type="validation_experiment",
                    resource_id=experiment_id,
                )
            return experiment
    except MCPToolError as e:
        return e.to_dict()


def create_validation_experiment(idea_id: str, payload: dict) -> dict:
    """Create a validation experiment for an idea from a structured payload.

    Payload fields mirror the REST validation experiment create body.

    Raises:
        ValidationError: If the payload is invalid.
        ResourceNotFoundError: If the idea does not exist.
    """
    try:
        try:
            body = ValidationExperimentCreate(**payload)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid validation experiment payload",
                details={"errors": e.errors()},
            ) from e

        with _get_store() as store:
            experiment = store.create_validation_experiment(
                idea_id,
                **body.model_dump(),
            )
            if experiment is None:
                raise ResourceNotFoundError(
                    f"Idea not found: {idea_id}",
                    resource_type="buildable_unit",
                    resource_id=idea_id,
                )
            return experiment
    except MCPToolError as e:
        return e.to_dict()


def update_validation_experiment(experiment_id: str, payload: dict) -> dict:
    """Update a validation experiment from a structured payload.

    Payload fields mirror the REST validation experiment update body.

    Raises:
        ValidationError: If the payload is invalid.
        ResourceNotFoundError: If the validation experiment does not exist.
    """
    try:
        try:
            body = ValidationExperimentUpdate(**payload)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid validation experiment payload",
                details={"errors": e.errors()},
            ) from e

        with _get_store() as store:
            experiment = store.update_validation_experiment(
                experiment_id,
                **body.model_dump(exclude_unset=True),
            )
            if experiment is None:
                raise ResourceNotFoundError(
                    f"Validation experiment not found: {experiment_id}",
                    resource_type="validation_experiment",
                    resource_id=experiment_id,
                )
            return experiment
    except MCPToolError as e:
        return e.to_dict()


def max_validation_experiment_summary(
    domain: str | None = None,
    idea_id: str | None = None,
    status: str | None = None,
    overdue_only: bool = False,
) -> dict:
    """Return portfolio-level validation experiment health.

    Optional filters match the REST validation experiment summary endpoint.
    """
    with _get_store() as store:
        return build_validation_experiment_summary(
            store,
            domain=domain,
            idea_id=idea_id,
            status=status,
            overdue_only=overdue_only,
        )


def max_portfolio_overlap(
    limit: int = 20,
    min_overlap_score: float = 0.35,
    include_archived: bool = False,
) -> list[dict] | dict:
    """Return portfolio overlap clusters for idea deduplication and positioning.

    Set limit to cap the number of clusters.
    Set min_overlap_score between 0 and 1 to tune sensitivity.
    Set include_archived=true to include archived ideas in the analysis.

    Raises:
        ValidationError: If parameters are out of valid ranges.
    """
    from max.analysis.portfolio_overlap import find_portfolio_overlap_clusters

    try:
        with _get_store() as store:
            clusters = find_portfolio_overlap_clusters(
                store,
                limit=limit,
                min_overlap_score=min_overlap_score,
                include_archived=include_archived,
            )
        return [_portfolio_overlap_cluster_to_dict(cluster) for cluster in clusters]
    except ValueError as e:
        # Map ValueError from analysis code to ValidationError
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def max_opportunity_heatmap(
    domain: str | None = None,
    min_signals: int = 1,
    limit: int = 1000,
) -> list[dict[str, object]] | dict:
    """Return opportunity buckets ranked by domain and idea category.

    Set domain to filter by pipeline profile domain.
    Set min_signals to require a minimum number of resolved supporting signals.
    Set limit to cap the number of buildable units analyzed.

    Raises:
        ValidationError: If min_signals or limit are out of valid ranges.
    """
    try:
        if min_signals < 0:
            raise ValidationError(
                "min_signals must be non-negative",
                field="min_signals",
                expected="integer >= 0",
                actual=str(min_signals),
            )
        if limit < 1:
            raise ValidationError(
                "limit must be at least 1",
                field="limit",
                expected="integer >= 1",
                actual=str(limit),
            )

        with _get_store() as store:
            return build_opportunity_heatmap(
                store,
                domain=domain,
                min_signals=min_signals,
                limit=limit,
            )
    except ValueError as e:
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def max_llm_budget_usage(run_limit: int = 20) -> dict:
    """Return recent LLM token and cost usage against configured budgets.

    Set run_limit to control how many recent pipeline runs are included.

    Raises:
        ValidationError: If run_limit is outside the REST endpoint range.
    """
    try:
        if isinstance(run_limit, bool) or not isinstance(run_limit, int):
            raise ValidationError(
                "run_limit must be an integer between 1 and 500",
                field="run_limit",
                expected="integer between 1 and 500",
                actual=str(run_limit),
            )
        if run_limit < 1 or run_limit > 500:
            raise ValidationError(
                "run_limit must be between 1 and 500",
                field="run_limit",
                expected="integer between 1 and 500",
                actual=str(run_limit),
            )

        with _get_store() as store:
            report = build_llm_budget_usage(store, limit=run_limit, include_current=True)
        return _add_llm_budget_indicators(report)
    except MCPToolError as e:
        return e.to_dict()


def get_llm_budget_usage(limit: int = 20, include_current: bool = True) -> dict:
    """Return LLM budget totals, stage breakdowns, and recent run history.

    Parameters mirror the REST budget usage endpoint. Set include_current=false
    to omit the in-process token tracker from totals.

    Raises:
        ValidationError: If parameters are outside the REST endpoint range.
        ExternalServiceError: If the configured store cannot provide usage data.
    """
    try:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValidationError(
                "limit must be an integer between 1 and 500",
                field="limit",
                expected="integer between 1 and 500",
                actual=str(limit),
            )
        if limit < 1 or limit > 500:
            raise ValidationError(
                "limit must be between 1 and 500",
                field="limit",
                expected="integer between 1 and 500",
                actual=str(limit),
            )
        if not isinstance(include_current, bool):
            raise ValidationError(
                "include_current must be a boolean",
                field="include_current",
                expected="boolean",
                actual=str(include_current),
            )

        with _get_store() as store:
            report = build_llm_budget_usage(
                store,
                limit=limit,
                include_current=include_current,
            )
        return LLMBudgetUsageResponse.model_validate(report).model_dump()
    except MCPToolError as e:
        return e.to_dict()
    except Exception as e:
        return ExternalServiceError(
            "Failed to load LLM budget usage",
            service="store",
            details={"reason": str(e)},
        ).to_dict()


def get_cost_anomalies(limit: int = 50, z_threshold: float = 2.0) -> dict:
    """Return anomalous LLM cost or token usage in recent pipeline runs.

    Parameters mirror the REST budget anomalies endpoint.

    Raises:
        ValidationError: If parameters are outside the REST endpoint range.
        ExternalServiceError: If the configured store cannot provide anomaly data.
    """
    try:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValidationError(
                "limit must be an integer between 1 and 500",
                field="limit",
                expected="integer between 1 and 500",
                actual=str(limit),
            )
        if limit < 1 or limit > 500:
            raise ValidationError(
                "limit must be between 1 and 500",
                field="limit",
                expected="integer between 1 and 500",
                actual=str(limit),
            )
        if isinstance(z_threshold, bool) or not isinstance(z_threshold, (int, float)):
            raise ValidationError(
                "z_threshold must be a positive number",
                field="z_threshold",
                expected="float > 0.0",
                actual=str(z_threshold),
            )
        if z_threshold <= 0:
            raise ValidationError(
                "z_threshold must be positive",
                field="z_threshold",
                expected="float > 0.0",
                actual=str(z_threshold),
            )

        with _get_store() as store:
            report = build_cost_anomaly_report(
                store,
                limit=limit,
                z_threshold=float(z_threshold),
            )
        return CostAnomalyReportResponse.model_validate(report).model_dump()
    except ValueError as e:
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()
    except Exception as e:
        return ExternalServiceError(
            "Failed to load cost anomalies",
            service="store",
            details={"reason": str(e)},
        ).to_dict()


def max_context_budget_waste(
    days: int = 30,
    source_adapter: str | None = None,
    min_reuse_count: int = 1,
    adapter_limit: int = 20,
) -> dict:
    """Return estimated wasted context from persisted evidence links.

    Parameters mirror the REST context-budget waste endpoint where practical.
    Set source_adapter to scope the report to one adapter, min_reuse_count to
    define low-utility signals, and adapter_limit to cap returned adapter rows.

    Raises:
        ValidationError: If parameters are outside the REST endpoint range.
    """
    try:
        if isinstance(days, bool) or not isinstance(days, int):
            raise ValidationError(
                "days must be an integer between 1 and 3650",
                field="days",
                expected="integer between 1 and 3650",
                actual=str(days),
            )
        if days < 1 or days > 3650:
            raise ValidationError(
                "days must be between 1 and 3650",
                field="days",
                expected="integer between 1 and 3650",
                actual=str(days),
            )
        if source_adapter is not None:
            if not isinstance(source_adapter, str):
                raise ValidationError(
                    "source_adapter must be a non-empty string",
                    field="source_adapter",
                    expected="string length 1 to 100",
                    actual=str(source_adapter),
                )
            if len(source_adapter) < 1 or len(source_adapter) > 100:
                raise ValidationError(
                    "source_adapter must be between 1 and 100 characters",
                    field="source_adapter",
                    expected="string length 1 to 100",
                    actual=str(source_adapter),
                )
        if isinstance(min_reuse_count, bool) or not isinstance(min_reuse_count, int):
            raise ValidationError(
                "min_reuse_count must be an integer between 0 and 100",
                field="min_reuse_count",
                expected="integer between 0 and 100",
                actual=str(min_reuse_count),
            )
        if min_reuse_count < 0 or min_reuse_count > 100:
            raise ValidationError(
                "min_reuse_count must be between 0 and 100",
                field="min_reuse_count",
                expected="integer between 0 and 100",
                actual=str(min_reuse_count),
            )
        if isinstance(adapter_limit, bool) or not isinstance(adapter_limit, int):
            raise ValidationError(
                "adapter_limit must be an integer between 1 and 500",
                field="adapter_limit",
                expected="integer between 1 and 500",
                actual=str(adapter_limit),
            )
        if adapter_limit < 1 or adapter_limit > 500:
            raise ValidationError(
                "adapter_limit must be between 1 and 500",
                field="adapter_limit",
                expected="integer between 1 and 500",
                actual=str(adapter_limit),
            )

        with _get_store() as store:
            report = build_context_budget_waste_report(
                store,
                days=days,
                source_adapter=source_adapter,
                min_reuse_count=min_reuse_count,
            )
        payload = ContextBudgetWasteResponse.model_validate(report).model_dump()
        return _add_context_budget_waste_warnings(payload, adapter_limit=adapter_limit)
    except ValueError as e:
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def max_pipeline_cost_anomalies(
    limit: int = DEFAULT_COST_ANOMALY_LIMIT,
    baseline_window: int = DEFAULT_COST_ANOMALY_BASELINE_WINDOW,
    multiplier_threshold: float = DEFAULT_COST_ANOMALY_MULTIPLIER_THRESHOLD,
    min_cost_usd: float = DEFAULT_COST_ANOMALY_MIN_COST_USD,
) -> dict:
    """Return recent pipeline runs with anomalous estimated cost.

    Parameters match the REST endpoint defaults. Set baseline_window to control
    the same-profile rolling baseline, multiplier_threshold to tune relative
    spikes, min_cost_usd to require an absolute minimum cost, and limit to cap
    recent runs considered for the returned report.

    Raises:
        ValidationError: If parameters are outside the REST endpoint range.
    """
    try:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValidationError(
                "limit must be an integer between 1 and 500",
                field="limit",
                expected="integer between 1 and 500",
                actual=str(limit),
            )
        if limit < 1 or limit > 500:
            raise ValidationError(
                "limit must be between 1 and 500",
                field="limit",
                expected="integer between 1 and 500",
                actual=str(limit),
            )
        if isinstance(baseline_window, bool) or not isinstance(baseline_window, int):
            raise ValidationError(
                "baseline_window must be an integer between 1 and 100",
                field="baseline_window",
                expected="integer between 1 and 100",
                actual=str(baseline_window),
            )
        if baseline_window < 1 or baseline_window > 100:
            raise ValidationError(
                "baseline_window must be between 1 and 100",
                field="baseline_window",
                expected="integer between 1 and 100",
                actual=str(baseline_window),
            )
        if min_cost_usd < 0:
            raise ValidationError(
                "min_cost_usd must be non-negative",
                field="min_cost_usd",
                expected="float >= 0.0",
                actual=str(min_cost_usd),
            )
        if multiplier_threshold <= 0:
            raise ValidationError(
                "multiplier_threshold must be positive",
                field="multiplier_threshold",
                expected="float > 0.0",
                actual=str(multiplier_threshold),
            )

        with _get_store() as store:
            report = build_pipeline_cost_anomaly_report(
                store,
                limit=limit,
                baseline_window=baseline_window,
                min_cost_usd=min_cost_usd,
                multiplier_threshold=multiplier_threshold,
            )
        payload = PipelineCostAnomalyReportResponse.model_validate(report).model_dump()
        return _add_pipeline_cost_anomaly_warnings(payload)
    except ValueError as e:
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def simulate_source_allocation(
    profile: str | None = None,
    budget: int | None = None,
) -> dict:
    """Simulate fetch allocation for a profile before a run.

    Set profile to use a named pipeline profile. Set budget to override the
    profile's signal limit when exploring allocation changes.

    Raises:
        ValidationError: If budget is invalid.
        ResourceNotFoundError: If the profile is not found.
    """
    from max.analysis.source_simulation import (
        simulate_source_allocation as build_source_allocation,
    )
    from max.config import MAX_PROFILE
    from max.profiles.loader import get_default_profile, load_profile

    try:
        if budget is not None and budget < 1:
            raise ValidationError(
                "budget must be at least 1",
                field="budget",
                expected="integer >= 1",
                actual=str(budget),
            )

        profile_name = profile or MAX_PROFILE or None
        try:
            pipeline_profile = (
                load_profile(profile_name) if profile_name else get_default_profile()
            )
        except FileNotFoundError as e:
            raise ResourceNotFoundError(
                str(e),
                resource_type="profile",
                resource_id=profile_name or "default",
            ) from e

        with _get_store() as store:
            report = build_source_allocation(pipeline_profile, store, budget=budget)

        return report.to_dict()
    except ValueError as e:
        # Map ValueError from analysis code to ValidationError
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def get_profile_source_recommendations(
    profile_name: str,
    max_age_days: int = 30,
    format: str = "json",
) -> dict:
    """Return source configuration recommendations for a named pipeline profile.

    Set max_age_days to control the stale-signal threshold. Only JSON output is
    supported because MCP tools must return serializable structured data.

    Raises:
        ValidationError: If max_age_days or format is invalid.
        ResourceNotFoundError: If the profile is not found.
    """
    from max.analysis.profile_source_recommendations import (
        build_profile_source_recommendations_for_profile,
    )
    from max.profiles.loader import load_profile

    try:
        if format != "json":
            raise ValidationError(
                "format must be json",
                field="format",
                expected="json",
                actual=str(format),
            )
        if max_age_days < 1:
            raise ValidationError(
                "max_age_days must be at least 1",
                field="max_age_days",
                expected="integer >= 1",
                actual=str(max_age_days),
            )

        try:
            profile = load_profile(profile_name)
        except FileNotFoundError as e:
            raise ResourceNotFoundError(
                f"Profile not found: {profile_name}",
                resource_type="profile",
                resource_id=profile_name,
            ) from e

        with _get_store() as store:
            report = build_profile_source_recommendations_for_profile(
                profile,
                store,
                max_age_days=max_age_days,
            )

        payload = report.to_dict()
        for recommendation in payload["recommendations"]:
            evidence = recommendation.get("evidence") or {}
            quality = evidence.get("quality") or {}
            approval = evidence.get("approval") or {}
            freshness = evidence.get("freshness") or {}
            recommendation["target_weight"] = recommendation["suggested_weight"]
            recommendation["reason"] = (
                recommendation["reasons"][0] if recommendation.get("reasons") else ""
            )
            recommendation["evidence_counts"] = {
                "total_signals": int(quality.get("total_signals") or 0),
                "total_feedbacked": int(approval.get("total_feedbacked") or 0),
                "approved": int(approval.get("approved") or 0),
                "rejected": int(approval.get("rejected") or 0),
                "freshness_total": int(freshness.get("total_count") or 0),
                "stale": int(freshness.get("stale_count") or 0),
            }
        return payload
    except ValueError as e:
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def get_profile_drift(
    profile_name: str,
    lookback_days: int = DEFAULT_PROFILE_DRIFT_LOOKBACK_DAYS,
    min_signals: int = DEFAULT_PROFILE_DRIFT_MIN_SIGNALS,
) -> dict:
    """Return a profile drift report for a named pipeline profile.

    Set lookback_days to limit recent signals, insights, and generated units.
    Set min_signals to add an explicit warning when the report is under-sampled.

    Raises:
        ValidationError: If lookback_days or min_signals are invalid.
        ResourceNotFoundError: If the profile is not found.
    """
    from max.profiles.loader import load_profile
    from max.server.schemas import ProfileDriftResponse

    try:
        if lookback_days < 1:
            raise ValidationError(
                "lookback_days must be at least 1",
                field="lookback_days",
                expected="integer >= 1",
                actual=str(lookback_days),
            )
        if min_signals < 0:
            raise ValidationError(
                "min_signals must be non-negative",
                field="min_signals",
                expected="integer >= 0",
                actual=str(min_signals),
            )

        try:
            profile = load_profile(profile_name)
        except FileNotFoundError as e:
            raise ResourceNotFoundError(
                f"Profile not found: {profile_name}",
                resource_type="profile",
                resource_id=profile_name,
            ) from e

        with _get_store() as store:
            report = build_profile_drift_report(
                profile,
                store,
                lookback_days=lookback_days,
                min_signals=min_signals,
            )

        payload = ProfileDriftResponse.model_validate(report.to_dict()).model_dump()
        payload["lookback_days"] = lookback_days
        payload["min_signals"] = min_signals
        return payload
    except ValueError as e:
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def get_architecture_enforcement_report(
    domain: str | None = None,
    limit: int = DEFAULT_ARCHITECTURE_ENFORCEMENT_UNIT_LIMIT,
    profile_name: str | None = None,
) -> dict:
    """Return architecture enforcement findings for a pipeline profile.

    Set domain to select a profile/domain and limit to cap recent buildable
    units analyzed. profile_name is accepted as an explicit alias for clients
    that already model the REST endpoint by profile name.

    Raises:
        ResourceNotFoundError: If the profile/domain is not found.
        ValidationError: If limit or selector inputs are invalid.
    """
    from max.profiles.loader import get_default_profile, list_profiles, load_profile

    try:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValidationError(
                "limit must be an integer between 1 and 10000",
                field="limit",
                expected="integer between 1 and 10000",
                actual=str(limit),
            )
        if limit < 1 or limit > 10_000:
            raise ValidationError(
                "limit must be between 1 and 10000",
                field="limit",
                expected="integer between 1 and 10000",
                actual=str(limit),
            )
        if domain is not None and not str(domain).strip():
            raise ValidationError(
                "domain must be a non-empty string",
                field="domain",
                expected="non-empty string",
                actual=str(domain),
            )
        if profile_name is not None and not str(profile_name).strip():
            raise ValidationError(
                "profile_name must be a non-empty string",
                field="profile_name",
                expected="non-empty string",
                actual=str(profile_name),
            )

        selector = profile_name or domain
        try:
            if selector:
                try:
                    profile = load_profile(selector)
                except FileNotFoundError:
                    profile = None
                    for candidate_name in list_profiles():
                        candidate = load_profile(candidate_name)
                        if candidate.domain.name == selector:
                            profile = candidate
                            break
                    if profile is None:
                        raise
            else:
                profile = get_default_profile()
        except FileNotFoundError as e:
            raise ResourceNotFoundError(
                f"Profile not found: {selector or 'default'}",
                resource_type="profile",
                resource_id=selector or "default",
            ) from e

        with _get_store() as store:
            report = build_architecture_enforcement_report(
                profile,
                store,
                unit_limit=limit,
            )

        return ArchitectureEnforcementResponse.model_validate(
            report.to_dict()
        ).model_dump()
    except ValueError as e:
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def _portfolio_overlap_cluster_to_dict(cluster) -> dict:
    return {
        "cluster_id": cluster.cluster_id,
        "idea_ids": cluster.idea_ids,
        "representative_idea_ids": cluster.representative_idea_ids,
        "overlap_score": cluster.overlap_score,
        "reasons": [
            {
                "type": reason.type,
                "description": reason.description,
                "score": reason.score,
                "shared_terms": reason.shared_terms,
                "shared_ids": reason.shared_ids,
            }
            for reason in cluster.overlap_reasons
        ],
        "suggested_action": cluster.suggested_action,
    }


def get_evidence_pack(id: str) -> dict:
    """Get the evidence pack used for an idea, or reconstruct one from its evidence chain.

    Raises:
        ResourceNotFoundError: If the idea does not exist.
    """
    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )
            critiques = store.get_idea_critiques(id)
            if critiques and critiques[0].get("evidence_pack"):
                return critiques[0]["evidence_pack"]

            from max.ideation.evidence import build_evidence_pack

            insights = [
                insight
                for insight_id in unit.inspiring_insights
                if (insight := store.get_insight(insight_id))
            ]
            return json.loads(build_evidence_pack(insights=insights, store=store).to_json())
    except MCPToolError as e:
        return e.to_dict()


def get_evidence_chain(id: str) -> dict:
    """Get the idea evidence chain as a graph of idea, insights, signals, and typed edges.

    Raises:
        ResourceNotFoundError: If the idea does not exist.
    """
    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )
            return build_evidence_chain_graph(unit, store)
    except MCPToolError as e:
        return e.to_dict()


def contribute_signal(
    title: str,
    content: str,
    url: str,
    source_type: str = "forum",
    tags: list[str] | None = None,
) -> dict:
    """Contribute a signal (data point) to the max idea engine.

    Signals are raw inputs from the ecosystem — articles, discussions, trends,
    tool launches, etc. They feed into synthesis and ideation.
    """
    from max.types.signal import Signal

    with _get_store() as store:
        signal = Signal(
            source_type=source_type,
            source_adapter="mcp",
            title=title,
            content=content,
            url=url,
            tags=tags or [],
        )
        result = store.insert_signal_result(signal)
        return {
            "id": result.signal.id,
            "title": result.signal.title,
            "status": result.status,
        }


def contribute_idea(
    title: str,
    problem: str,
    solution: str,
    category: str = "application",
    one_liner: str = "",
    value_proposition: str = "",
) -> dict:
    """Submit a new idea to the max idea engine.

    The idea will be stored and can be evaluated later.
    Categories: mcp_server, cli_tool, library, integration, automation, application, feature.
    """
    from max.types.buildable_unit import BuildableUnit

    with _get_store() as store:
        unit = BuildableUnit(
            title=title,
            one_liner=one_liner or title,
            category=category,
            problem=problem,
            solution=solution,
            value_proposition=value_proposition or solution,
        )
        unit = store.insert_buildable_unit(unit)
        return {"id": unit.id, "title": unit.title, "status": "draft"}


def evaluate_idea(id: str) -> dict:
    """Trigger evaluation of an idea using the LLM-based 7-dimension scoring.

    This calls the Anthropic API to evaluate the idea across pain_severity,
    addressable_scale, build_effort, composability, competitive_density,
    timing_fit, and compounding_value. Returns the evaluation result.

    Raises:
        ResourceNotFoundError: If the idea does not exist.
        ExternalServiceError: If the LLM API call fails.
    """
    from max.evaluation.engine import evaluate

    try:
        with _get_store() as store:
            unit = store.get_buildable_unit(id)
            if not unit:
                raise ResourceNotFoundError(
                    f"Idea not found: {id}",
                    resource_type="buildable_unit",
                    resource_id=id,
                )
            try:
                evaluation = evaluate(unit)
            except Exception as e:
                # Wrap evaluation errors as external service errors
                raise ExternalServiceError(
                    f"LLM evaluation failed: {str(e)}",
                    service="anthropic",
                    details={"original_error": str(e)},
                ) from e
            store.insert_evaluation(evaluation)
            store.update_buildable_unit_status(id, "evaluated")
            return {
                "id": id,
                "overall_score": evaluation.overall_score,
                "recommendation": evaluation.recommendation,
                "strengths": evaluation.strengths,
                "weaknesses": evaluation.weaknesses,
            }
    except MCPToolError as e:
        return e.to_dict()


def find_similar(
    text: str,
    entity_type: str,
    threshold: float = 0.8,
    limit: int = 5,
) -> list[dict]:
    """Find entities semantically similar to the given text.

    entity_type: 'signal', 'insight', or 'buildable_unit'.
    Returns similar entities sorted by similarity score.
    """
    from max.embeddings.engine import SemanticIndex

    with _get_store() as store:
        index = SemanticIndex(store)
        results = index.find_similar(text, entity_type, threshold=threshold, limit=limit)
        return [{"entity_id": eid, "score": score} for eid, score in results]


def get_stats() -> dict:
    """Get statistics about the max idea engine.

    Returns counts of signals, insights, ideas, and average scores.
    """
    with _get_store() as store:
        signals_count = store.count_signals()
        insights = store.get_insights(limit=10000)
        all_units = store.get_buildable_units(limit=10000)
        evaluated_count = sum(1 for u in all_units if u.status in ("evaluated", "approved", "published"))
        published_count = sum(1 for u in all_units if u.status == "published")

        scores = []
        for unit in all_units:
            ev = store.get_evaluation(unit.id)
            if ev:
                scores.append(ev.overall_score)

        return {
            "signals_count": signals_count,
            "insights_count": len(insights),
            "ideas_count": len(all_units),
            "evaluated_count": evaluated_count,
            "published_count": published_count,
            "avg_score": sum(scores) / len(scores) if scores else None,
        }


def get_evaluation_calibration(
    domain: str | None = None,
    min_samples: int = 1,
    limit: int = 50,
) -> dict:
    """Return score-vs-feedback calibration grouped by domain and recommendation."""
    with _get_store() as store:
        report = build_evaluation_calibration_report(
            store,
            domain=domain,
            min_samples=min_samples,
            limit=limit,
        )
        return asdict(report)


def get_review_thresholds(
    domain: str | None = None,
    min_samples: int = DEFAULT_THRESHOLD_MIN_SAMPLES,
) -> dict:
    """Return review threshold recommendations grouped by domain."""
    with _get_store() as store:
        recommendations = recommend_review_thresholds(
            store,
            domain=domain,
            min_samples=min_samples,
        )
        return {
            "domain": domain,
            "min_samples": min_samples,
            "default_approve_threshold": DEFAULT_APPROVE_THRESHOLD,
            "default_reject_threshold": DEFAULT_REJECT_THRESHOLD,
            "recommendations": [asdict(item) for item in recommendations],
        }


def get_roi_forecast(
    domain: str | None = None,
    status: str | None = None,
    profile: str | None = None,
    weight_profile: str | None = None,
    limit: int = 100,
) -> dict:
    """Return a ranked ROI forecast for buildable ideas.

    Set domain and status to filter ideas. Set profile to use a pipeline
    profile's evaluation weights, or weight_profile to use a named evaluation
    weight profile. Limit is bounded to match the REST ROI forecast endpoint.

    Raises:
        ValidationError: If request parameters are invalid.
        ResourceNotFoundError: If profile or weight_profile is not found.
    """
    from max.evaluation.weights import WEIGHT_PROFILES
    from max.profiles.loader import load_profile

    try:
        if limit < 1 or limit > 500:
            raise ValidationError(
                "limit must be between 1 and 500",
                field="limit",
                expected="integer between 1 and 500",
                actual=str(limit),
            )
        if profile and weight_profile:
            raise ValidationError(
                "Use either profile or weight_profile, not both.",
                details={"fields": ["profile", "weight_profile"]},
            )

        profile_input = None
        if profile:
            try:
                profile_input = load_profile(profile)
            except FileNotFoundError as e:
                raise ResourceNotFoundError(
                    f"Profile not found: {profile}",
                    resource_type="profile",
                    resource_id=profile,
                ) from e
        elif weight_profile:
            if weight_profile not in WEIGHT_PROFILES:
                raise ResourceNotFoundError(
                    f"Evaluation weight profile not found: {weight_profile}",
                    resource_type="evaluation_weight_profile",
                    resource_id=weight_profile,
                )
            profile_input = weight_profile

        with _get_store() as store:
            units = store.get_buildable_units(limit=limit, status=status, domain=domain)
            evaluations = {unit.id: store.get_evaluation(unit.id) for unit in units}
            report = generate_roi_forecast(units, evaluations, profile=profile_input)
        return asdict(report)
    except MCPToolError as e:
        return e.to_dict()


def max_mcp_capability_coverage(
    min_count: int = DEFAULT_MCP_CAPABILITY_MIN_COUNT,
    limit_representatives: int = DEFAULT_MCP_CAPABILITY_LIMIT_REPRESENTATIVES,
    source_adapter: str | None = None,
    domain: str | None = None,
) -> dict:
    """Return MCP capability coverage and gaps across MCP ecosystem signals.

    Set min_count to define the coverage floor for each capability bucket.
    Set limit_representatives to cap representative signals per bucket.
    Set source_adapter or domain to inspect a narrower slice of MCP signals.

    Raises:
        ValidationError: If request parameters are invalid.
    """
    try:
        if isinstance(min_count, bool) or not isinstance(min_count, int):
            raise ValidationError(
                "min_count must be an integer between 1 and 10000",
                field="min_count",
                expected="integer between 1 and 10000",
                actual=str(min_count),
            )
        if min_count < 1 or min_count > 10_000:
            raise ValidationError(
                "min_count must be between 1 and 10000",
                field="min_count",
                expected="integer between 1 and 10000",
                actual=str(min_count),
            )
        if isinstance(limit_representatives, bool) or not isinstance(
            limit_representatives, int
        ):
            raise ValidationError(
                "limit_representatives must be an integer between 0 and 100",
                field="limit_representatives",
                expected="integer between 0 and 100",
                actual=str(limit_representatives),
            )
        if limit_representatives < 0 or limit_representatives > 100:
            raise ValidationError(
                "limit_representatives must be between 0 and 100",
                field="limit_representatives",
                expected="integer between 0 and 100",
                actual=str(limit_representatives),
            )
        if source_adapter is not None and not str(source_adapter).strip():
            raise ValidationError(
                "source_adapter must be a non-empty string",
                field="source_adapter",
                expected="non-empty string",
                actual=str(source_adapter),
            )
        if domain is not None and not str(domain).strip():
            raise ValidationError(
                "domain must be a non-empty string",
                field="domain",
                expected="non-empty string",
                actual=str(domain),
            )

        with _get_store() as store:
            report = build_mcp_capability_coverage_report(
                store,
                domain=domain,
                min_count=min_count,
                limit_representatives=limit_representatives,
                source_adapter=source_adapter,
            )
            return _mcp_capability_report_payload(report, store)
    except ValueError as e:
        return ValidationError(str(e)).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def max_source_reliability(
    profile: str | None = None,
    time_window: str | None = None,
    min_signal_count: int = 1,
    signal_limit: int | None = None,
) -> dict:
    """Return source reliability metrics grouped by signal source type.

    Set profile to filter to enabled adapters from a named pipeline profile.
    Set time_window to a compact duration such as "24h", "7d", or "4w".
    Set min_signal_count to hide source types with fewer active signals.

    Raises:
        ResourceNotFoundError: If the profile is not found.
        ValidationError: If time_window format is invalid.
    """
    from max.analysis.source_reliability import (
        DEFAULT_SIGNAL_LIMIT,
        build_source_reliability_report,
    )
    from max.profiles.loader import load_profile

    try:
        adapters: set[str] | None = None
        resolved_profile = None
        resolved_signal_limit = signal_limit or DEFAULT_SIGNAL_LIMIT
        if profile:
            try:
                resolved_profile = load_profile(profile)
            except FileNotFoundError as e:
                raise ResourceNotFoundError(
                    f"Profile not found: {profile}",
                    resource_type="profile",
                    resource_id=profile,
                ) from e
            adapters = {source.adapter for source in resolved_profile.sources if source.enabled}
            if signal_limit is None:
                resolved_signal_limit = resolved_profile.signal_limit

        try:
            fetched_since = _parse_time_window(time_window)
        except ValueError as e:
            raise ValidationError(
                str(e),
                field="time_window",
                expected="duration like '24h', '7d', or '4w'",
                actual=time_window or "",
            ) from e

        with _get_store() as store:
            report = build_source_reliability_report(
                store,
                signal_limit=resolved_signal_limit,
                source_adapters=adapters,
                fetched_since=fetched_since,
                min_signal_count=min_signal_count,
            )

        result = report.to_dict()
        result["filters"] = {
            "profile": resolved_profile.name if resolved_profile else profile,
            "domain": resolved_profile.domain.name if resolved_profile else None,
            "source_adapters": sorted(adapters) if adapters is not None else None,
            "time_window": time_window,
            "fetched_since": fetched_since.isoformat() if fetched_since else None,
            "min_signal_count": min_signal_count,
        }
        return result
    except MCPToolError as e:
        return e.to_dict()


def max_signal_freshness(
    max_age_days: int = 30,
    source_adapter: str | list[str] | None = None,
    profile: str | None = None,
) -> dict:
    """Return signal freshness and stale-source recommendations.

    Set source_adapter to a comma-delimited string or list of adapter names.
    Set profile to restrict the report to enabled adapters from a named profile.

    Raises:
        ResourceNotFoundError: If the profile is not found.
        ValidationError: If max_age_days is invalid.
    """
    from max.analysis.signal_freshness import build_signal_freshness_report
    from max.profiles.loader import load_profile

    try:
        requested_adapters = _normalize_source_adapter_filter(source_adapter)
        resolved_profile = None
        adapters = requested_adapters

        if profile:
            try:
                resolved_profile = load_profile(profile)
            except FileNotFoundError as e:
                raise ResourceNotFoundError(
                    f"Profile not found: {profile}",
                    resource_type="profile",
                    resource_id=profile,
                ) from e

            enabled_adapters = {source.adapter for source in resolved_profile.sources if source.enabled}
            if requested_adapters is None:
                adapters = sorted(enabled_adapters)
            else:
                adapters = sorted(set(requested_adapters) & enabled_adapters)

        try:
            with _get_store() as store:
                report = build_signal_freshness_report(
                    store,
                    max_age_days=max_age_days,
                    source_adapters=adapters,
                )
        except ValueError as e:
            raise ValidationError(
                str(e),
                field="max_age_days",
                expected="integer >= 1",
                actual=str(max_age_days),
            ) from e

        result = report.to_dict()
        result["filters"] = {
            "profile": resolved_profile.name if resolved_profile else profile,
            "domain": resolved_profile.domain.name if resolved_profile else None,
            "source_adapters": adapters,
            "max_age_days": max_age_days,
        }
        return result
    except MCPToolError as e:
        return e.to_dict()


def _normalize_source_adapter_filter(source_adapter: str | list[str] | None) -> list[str] | None:
    if source_adapter is None:
        return None
    values = [source_adapter] if isinstance(source_adapter, str) else source_adapter
    adapters: set[str] = set()
    for value in values:
        if not value:
            continue
        adapters.update(part.strip() for part in value.split(",") if part.strip())
    return sorted(adapters)


def _parse_time_window(time_window: str | None) -> datetime | None:
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


# ── Schedule tools ──────────────────────────────────────────────────


def get_schedule() -> dict:
    """Get the current pipeline schedule status.

    Returns whether the scheduler is enabled, the interval, last run time,
    next run time, and last run results.
    """
    if _scheduler is None:
        return {"error": "Scheduler not available"}
    return _scheduler.status()


def set_schedule(
    enabled: bool | None = None,
    interval_seconds: int | None = None,
    profile: str | None = None,
    include_all: bool | None = None,
    signal_limit: int | None = None,
    min_score: float | None = None,
    weight_profile: str | None = None,
    ideation_mode: str | None = None,
    quality_loop_enabled: bool | None = None,
    trigger_now: bool = False,
) -> dict:
    """Update the pipeline schedule or trigger an immediate run.

    Set enabled=false to pause, enabled=true to resume.
    Set interval_seconds to change how often the pipeline runs.
    Set profile to run a named pipeline profile, or "all" for all focused profiles.
    Set include_all=true to bypass focus when profile="all".
    Set pipeline options to override scheduled run defaults.
    Set trigger_now=true to run the pipeline immediately.
    """
    if _scheduler is None:
        return {"error": "Scheduler not available"}
    _scheduler.update(
        enabled=enabled,
        interval_seconds=interval_seconds,
        profile=profile,
        include_all=include_all,
        signal_limit=signal_limit,
        min_score=min_score,
        weight_profile=weight_profile,
        ideation_mode=ideation_mode,
        quality_loop_enabled=quality_loop_enabled,
    )
    if trigger_now:
        asyncio.ensure_future(_scheduler.run_once())
    return _scheduler.status()


def dry_run_pipeline(
    profile: str | None = None,
    signal_limit: int | None = None,
    min_score: float | None = None,
    weight_profile: str | None = None,
    ideation_mode: str | None = None,
    quality_loop_enabled: bool | None = None,
    draft_count: int | None = None,
    stages: list[str] | None = None,
) -> dict:
    """Estimate a pipeline run without fetching, writing, or calling LLMs.

    Set profile to use a named pipeline profile. Optional overrides mirror the
    REST dry-run request where applicable and are applied before estimating
    enabled adapters, fetch allocation, stage budgets, and token cost.

    Raises:
        ResourceNotFoundError: If the profile is not found.
        ValidationError: If request parameters are invalid.
    """
    from pydantic import ValidationError as PydanticValidationError

    from max.server.api import run_pipeline_dry_run
    from max.server.schemas import PipelineDryRunRequest

    try:
        payload = {}
        if profile is not None:
            payload["profile"] = profile
        if signal_limit is not None:
            payload["signal_limit"] = signal_limit
        if min_score is not None:
            payload["min_score"] = min_score
        if weight_profile is not None:
            payload["weight_profile"] = weight_profile
        if ideation_mode is not None:
            payload["ideation_mode"] = ideation_mode
        if quality_loop_enabled is not None:
            payload["quality_loop_enabled"] = quality_loop_enabled
        if draft_count is not None:
            payload["draft_count"] = draft_count
        if stages is not None:
            payload["stages"] = stages

        try:
            response = run_pipeline_dry_run(PipelineDryRunRequest(**payload))
            return response.model_dump()
        except FileNotFoundError as e:
            raise ResourceNotFoundError(
                f"Profile not found: {profile or 'default'}",
                resource_type="profile",
                resource_id=profile or "default",
            ) from e
        except PydanticValidationError as e:
            # Map pydantic validation errors to our ValidationError
            raise ValidationError(str(e)) from e
        except ValueError as e:
            # Map value errors (e.g., unknown stages) to ValidationError
            raise ValidationError(str(e)) from e
    except MCPToolError as e:
        return e.to_dict()


def get_pipeline_replay_plan(run_id: str, include_commands: bool = True) -> dict:
    """Build a replay plan for a stored pipeline run.

    Set include_commands=false to omit CLI/API dry-run command details while
    keeping the original run summary, profile, metrics, adapter inputs, and
    reproducibility warnings.

    Raises:
        ResourceNotFoundError: If the pipeline run does not exist.
    """
    try:
        with _get_store() as store:
            plan = build_pipeline_replay_plan(store, run_id=run_id)
            payload = PipelineReplayPlanResponse.model_validate(plan).model_dump()
            if not include_commands:
                payload.pop("dry_run_commands", None)
            return payload
    except PipelineReplayRunNotFound as e:
        return ResourceNotFoundError(
            "Pipeline run ID not found",
            resource_type="pipeline_run",
            resource_id=e.run_id,
        ).to_dict()
    except MCPToolError as e:
        return e.to_dict()


def compare_pipeline_runs(
    baseline_run_id: str,
    candidate_run_id: str,
    include_adapter_metrics: bool = True,
) -> dict:
    """Compare persisted metric deltas between two pipeline runs.

    Set include_adapter_metrics=false to omit per-adapter status and metric
    deltas while keeping the same core report as the REST comparison endpoint.

    Raises:
        ResourceNotFoundError: If either pipeline run does not exist.
    """
    try:
        with _get_store() as store:
            comparison = build_pipeline_run_comparison(
                store,
                base_run_id=baseline_run_id,
                target_run_id=candidate_run_id,
                include_adapter_metrics=include_adapter_metrics,
            )
            if include_adapter_metrics:
                return PipelineRunComparisonResponse.model_validate(comparison).model_dump()
            return comparison
    except PipelineRunComparisonNotFound as e:
        return ResourceNotFoundError(
            "Pipeline run ID not found",
            resource_type="pipeline_run",
            resource_id=",".join(e.missing_run_ids),
            details={"missing_run_ids": e.missing_run_ids},
        ).to_dict()
    except MCPToolError as e:
        return e.to_dict()


# ── Resource functions ──────────────────────────────────────────────


def ideas_list() -> str:
    """Browse top ideas from the max idea engine."""
    with _get_store() as store:
        units = store.get_buildable_units(limit=20)
        items = []
        for unit in units:
            ev = store.get_evaluation(unit.id)
            items.append({
                "id": unit.id,
                "title": unit.title,
                "one_liner": unit.one_liner,
                "category": unit.category,
                "domain": unit.domain,
                "status": unit.status,
                **_review_metadata(unit, store.get_latest_feedback(unit.id)),
                "quality_score": unit.quality_score,
                "novelty_score": unit.novelty_score,
                "usefulness_score": unit.usefulness_score,
                "rejection_tags": unit.rejection_tags,
                "score": ev.overall_score if ev else None,
                "recommendation": ev.recommendation if ev else None,
            })
        return json.dumps(items, indent=2)


def idea_detail(idea_id: str) -> str:
    """Get details of a specific idea."""
    with _get_store() as store:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            return json.dumps({"error": f"Not found: {idea_id}"})
        evaluation = store.get_evaluation(idea_id)
        result = {
            "id": unit.id,
            "title": unit.title,
            "one_liner": unit.one_liner,
            "category": unit.category,
            "domain": unit.domain,
            "problem": unit.problem,
            "solution": unit.solution,
            "target_users": unit.target_users,
            "value_proposition": unit.value_proposition,
            "specific_user": unit.specific_user,
            "buyer": unit.buyer,
            "workflow_context": unit.workflow_context,
            "current_workaround": unit.current_workaround,
            "why_now": unit.why_now,
            "validation_plan": unit.validation_plan,
            "first_10_customers": unit.first_10_customers,
            "domain_risks": unit.domain_risks,
            "evidence_rationale": unit.evidence_rationale,
            "quality_score": unit.quality_score,
            "novelty_score": unit.novelty_score,
            "usefulness_score": unit.usefulness_score,
            "rejection_tags": unit.rejection_tags,
            "status": unit.status,
            **_review_metadata(unit, store.get_latest_feedback(idea_id)),
        }
        critiques = store.get_idea_critiques(idea_id)
        if critiques:
            result["latest_critique"] = critiques[0]
        if evaluation:
            result["score"] = evaluation.overall_score
            result["recommendation"] = evaluation.recommendation
        return json.dumps(result, indent=2)


def evidence_pack_detail(idea_id: str) -> str:
    """Get evidence pack details for a specific idea."""
    return json.dumps(get_evidence_pack(idea_id), indent=2)


def evidence_chain_detail(idea_id: str) -> str:
    """Get evidence-chain graph details for a specific idea."""
    return json.dumps(get_evidence_chain(idea_id), indent=2)


def spec_preview_detail(idea_id: str) -> str:
    """Get tact spec preview details for a specific idea."""
    return json.dumps(get_spec_preview(idea_id), indent=2)


def acceptance_criteria_detail(idea_id: str) -> str:
    """Get acceptance criteria details for a specific idea."""
    return json.dumps(get_acceptance_criteria(idea_id), indent=2)


def blast_radius_detail(idea_id: str) -> str:
    """Get implementation blast-radius details for a specific idea."""
    return json.dumps(get_blast_radius(idea_id), indent=2)


def review_gate_detail(idea_id: str) -> str:
    """Get review gate decision details for a specific idea."""
    return json.dumps(get_review_gate_decision(idea_id), indent=2)


def design_briefs_list() -> str:
    """Browse persisted design briefs from the max portfolio synthesis pipeline."""
    return json.dumps(list_design_briefs(), indent=2)


def design_brief_detail(brief_id: str) -> str:
    """Get details of a specific design brief."""
    return json.dumps(get_design_brief(brief_id), indent=2)


def design_brief_validation_plan_detail(brief_id: str) -> str:
    """Get the validation plan for a specific design brief."""
    return json.dumps(get_design_brief_validation_plan(brief_id), indent=2)


def design_brief_risk_register_detail(brief_id: str) -> str:
    """Get the risk register for a specific design brief."""
    return json.dumps(get_design_brief_risk_register(brief_id), indent=2)


def design_brief_roadmap_detail(brief_id: str) -> str:
    """Get the roadmap for a specific design brief."""
    return json.dumps(get_design_brief_roadmap(brief_id), indent=2)


def design_brief_prd_detail(brief_id: str) -> str:
    """Get the PRD export for a specific design brief."""
    return json.dumps(get_design_brief_prd(brief_id), indent=2)


def design_brief_executive_memo_detail(brief_id: str) -> str:
    """Get the executive memo export for a specific design brief."""
    return json.dumps(get_design_brief_executive_memo(brief_id), indent=2)


def design_brief_market_sizing_detail(brief_id: str) -> str:
    """Get the market sizing report for a specific design brief."""
    return json.dumps(get_design_brief_market_sizing(brief_id), indent=2)


def design_brief_competitive_landscape_detail(brief_id: str) -> str:
    """Get the competitive landscape report for a specific design brief."""
    return json.dumps(get_design_brief_competitive_landscape(brief_id), indent=2)


def design_brief_evidence_matrix_detail(brief_id: str) -> str:
    """Get the evidence matrix for a specific design brief."""
    return json.dumps(get_design_brief_evidence_matrix(brief_id), indent=2)


def design_brief_launch_checklist_detail(brief_id: str) -> str:
    """Get the launch checklist for a specific design brief."""
    return json.dumps(get_design_brief_launch_checklist(brief_id), indent=2)


def design_brief_pricing_strategy_detail(brief_id: str) -> str:
    """Get the pricing strategy for a specific design brief."""
    return json.dumps(get_design_brief_pricing_strategy(brief_id), indent=2)


def design_brief_bundle_detail(brief_id: str) -> str:
    """Get the consolidated bundle for a specific design brief."""
    return json.dumps(get_design_brief_bundle(brief_id), indent=2)


def validation_experiments_for_idea_detail(idea_id: str) -> str:
    """Browse validation experiments for a specific idea."""
    return json.dumps(list_validation_experiments(idea_id), indent=2)


def validation_experiment_detail(experiment_id: str) -> str:
    """Get details of a specific validation experiment."""
    return json.dumps(get_validation_experiment(experiment_id), indent=2)


def validation_experiment_summary_detail() -> str:
    """Browse the default validation experiment portfolio summary."""
    return json.dumps(max_validation_experiment_summary(), indent=2)


def validation_experiment_summary_for_domain_detail(domain: str) -> str:
    """Browse validation experiment portfolio summary for a domain."""
    return json.dumps(max_validation_experiment_summary(domain=domain), indent=2)


def signal_freshness_detail() -> str:
    """Browse the default signal freshness report."""
    return json.dumps(max_signal_freshness(), indent=2)


def portfolio_overlap_detail() -> str:
    """Browse the default portfolio overlap report."""
    return json.dumps(max_portfolio_overlap(), indent=2)


def opportunity_heatmap_detail() -> str:
    """Browse the default opportunity heatmap report."""
    return json.dumps(max_opportunity_heatmap(), indent=2)


def llm_budget_usage_detail() -> str:
    """Browse the default LLM budget usage report."""
    return json.dumps(max_llm_budget_usage(), indent=2)


def budget_usage_detail() -> str:
    """Browse the default REST-compatible LLM budget usage report."""
    return json.dumps(get_llm_budget_usage(), indent=2)


def budget_anomalies_detail() -> str:
    """Browse the default REST-compatible cost anomaly report."""
    return json.dumps(get_cost_anomalies(), indent=2)


def context_budget_waste_detail() -> str:
    """Browse the default context budget waste report."""
    return json.dumps(max_context_budget_waste(), indent=2)


def pipeline_cost_anomalies_detail() -> str:
    """Browse the default pipeline cost anomaly report."""
    return json.dumps(max_pipeline_cost_anomalies(), indent=2)


def source_allocation_detail() -> str:
    """Browse the default source allocation simulation report."""
    return json.dumps(simulate_source_allocation(), indent=2)


def profile_source_recommendations_detail(profile_name: str) -> str:
    """Browse profile source recommendations for a specific profile."""
    return json.dumps(get_profile_source_recommendations(profile_name), indent=2)


def profile_drift_detail(profile_name: str) -> str:
    """Browse the default drift report for a specific profile."""
    return json.dumps(get_profile_drift(profile_name), indent=2)


def roi_forecast_detail() -> str:
    """Browse the default ROI forecast report."""
    return json.dumps(get_roi_forecast(), indent=2)


def mcp_capability_coverage_detail() -> str:
    """Browse the default MCP capability coverage report."""
    return json.dumps(max_mcp_capability_coverage(), indent=2)


def pipeline_run_comparison_detail(baseline_run_id: str, candidate_run_id: str) -> str:
    """Browse the default comparison between two pipeline runs."""
    return json.dumps(
        compare_pipeline_runs(
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
        ),
        indent=2,
    )


# ── MCP server factory ─────────────────────────────────────────────


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server with tools and resources."""
    mcp = FastMCP("Max Idea Engine")

    # Register tools
    mcp.tool(search_ideas)
    mcp.tool(get_idea)
    mcp.tool(get_spec_preview)
    mcp.tool(get_spec_readiness)
    mcp.tool(get_implementation_plan)
    mcp.tool(get_acceptance_criteria)
    mcp.tool(get_blast_radius)
    mcp.tool(get_review_gate_decision)
    mcp.tool(get_idea_critique)
    mcp.tool(list_design_briefs)
    mcp.tool(get_design_brief)
    mcp.tool(get_design_brief_markdown)
    mcp.tool(get_design_brief_validation_plan)
    mcp.tool(get_design_brief_risk_register)
    mcp.tool(get_design_brief_roadmap)
    mcp.tool(get_design_brief_prd)
    mcp.tool(get_design_brief_executive_memo)
    mcp.tool(get_design_brief_market_sizing)
    mcp.tool(get_design_brief_competitive_landscape)
    mcp.tool(get_design_brief_evidence_matrix)
    mcp.tool(get_design_brief_launch_checklist)
    mcp.tool(get_design_brief_pricing_strategy)
    mcp.tool(get_design_brief_bundle)
    mcp.tool(list_validation_experiments)
    mcp.tool(get_validation_experiment)
    mcp.tool(create_validation_experiment)
    mcp.tool(update_validation_experiment)
    mcp.tool(max_validation_experiment_summary)
    mcp.tool(get_evidence_pack)
    mcp.tool(get_evidence_chain)
    mcp.tool(contribute_signal)
    mcp.tool(contribute_idea)
    mcp.tool(evaluate_idea)
    mcp.tool(find_similar)
    mcp.tool(get_stats)
    mcp.tool(get_evaluation_calibration)
    mcp.tool(get_review_thresholds)
    mcp.tool(get_roi_forecast)
    mcp.tool(max_source_reliability)
    mcp.tool(max_signal_freshness)
    mcp.tool(max_portfolio_overlap)
    mcp.tool(max_opportunity_heatmap)
    mcp.tool(max_llm_budget_usage)
    mcp.tool(get_llm_budget_usage)
    mcp.tool(get_cost_anomalies)
    mcp.tool(max_context_budget_waste)
    mcp.tool(max_pipeline_cost_anomalies)
    mcp.tool(simulate_source_allocation)
    mcp.tool(get_profile_source_recommendations)
    mcp.tool(get_profile_drift)
    mcp.tool(get_architecture_enforcement_report)
    mcp.tool(max_mcp_capability_coverage)
    mcp.tool(get_schedule)
    mcp.tool(set_schedule)
    mcp.tool(dry_run_pipeline)
    mcp.tool(get_pipeline_replay_plan)
    mcp.tool(compare_pipeline_runs)

    # Register resources
    mcp.resource("ideas://list")(ideas_list)
    mcp.resource("ideas://{idea_id}")(idea_detail)
    mcp.resource("ideas://{idea_id}/evidence-pack")(evidence_pack_detail)
    mcp.resource("ideas://{idea_id}/evidence-chain")(evidence_chain_detail)
    mcp.resource("ideas://{idea_id}/spec-preview")(spec_preview_detail)
    mcp.resource("ideas://{idea_id}/acceptance-criteria")(acceptance_criteria_detail)
    mcp.resource("ideas://{idea_id}/blast-radius")(blast_radius_detail)
    mcp.resource("ideas://{idea_id}/review-gate")(review_gate_detail)
    mcp.resource("design-briefs://list")(design_briefs_list)
    mcp.resource("design-briefs://{brief_id}")(design_brief_detail)
    mcp.resource("design-brief-validation-plans://{brief_id}")(design_brief_validation_plan_detail)
    mcp.resource("design-brief-risk-registers://{brief_id}")(design_brief_risk_register_detail)
    mcp.resource("design-brief-roadmaps://{brief_id}")(design_brief_roadmap_detail)
    mcp.resource("design-brief-prd://{brief_id}")(design_brief_prd_detail)
    mcp.resource("design-brief-executive-memos://{brief_id}")(
        design_brief_executive_memo_detail
    )
    mcp.resource("design-brief-market-sizing://{brief_id}")(design_brief_market_sizing_detail)
    mcp.resource("design-brief-competitive-landscapes://{brief_id}")(
        design_brief_competitive_landscape_detail
    )
    mcp.resource("design-brief-evidence-matrices://{brief_id}")(
        design_brief_evidence_matrix_detail
    )
    mcp.resource("design-brief-launch-checklist://{brief_id}")(
        design_brief_launch_checklist_detail
    )
    mcp.resource("design-brief-pricing-strategies://{brief_id}")(
        design_brief_pricing_strategy_detail
    )
    mcp.resource("design-brief-bundles://{brief_id}")(design_brief_bundle_detail)
    mcp.resource("ideas://{idea_id}/validation-experiments")(validation_experiments_for_idea_detail)
    mcp.resource("validation-experiments://summary")(validation_experiment_summary_detail)
    mcp.resource("validation-experiments://summary/{domain}")(
        validation_experiment_summary_for_domain_detail
    )
    mcp.resource("validation-experiments://{experiment_id}")(validation_experiment_detail)
    mcp.resource("signals://freshness")(signal_freshness_detail)
    mcp.resource("portfolio://overlap")(portfolio_overlap_detail)
    mcp.resource("opportunities://heatmap")(opportunity_heatmap_detail)
    mcp.resource("budget://llm-usage")(llm_budget_usage_detail)
    mcp.resource("budget://usage")(budget_usage_detail)
    mcp.resource("budget://anomalies")(budget_anomalies_detail)
    mcp.resource("context-budget://waste")(context_budget_waste_detail)
    mcp.resource("pipeline://cost-anomalies")(pipeline_cost_anomalies_detail)
    mcp.resource("sources://allocation-simulation")(source_allocation_detail)
    mcp.resource("profile-source-recommendations://{profile_name}")(
        profile_source_recommendations_detail
    )
    mcp.resource("profile-drift://{profile_name}")(profile_drift_detail)
    mcp.resource("roi://forecast")(roi_forecast_detail)
    mcp.resource("mcp-capabilities://coverage")(mcp_capability_coverage_detail)
    mcp.resource("pipeline-run-comparisons://{baseline_run_id}/{candidate_run_id}")(
        pipeline_run_comparison_detail
    )

    return mcp
