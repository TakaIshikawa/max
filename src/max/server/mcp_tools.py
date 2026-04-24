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

from max.analysis.blast_radius import estimate_idea_blast_radius
from max.analysis.evaluation_calibration import build_evaluation_calibration_report
from max.analysis.pipeline_replay import PipelineReplayRunNotFound, build_pipeline_replay_plan
from max.analysis.roi_forecast import generate_roi_forecast
from max.analysis.thresholds import (
    DEFAULT_APPROVE_THRESHOLD,
    DEFAULT_MIN_SAMPLES as DEFAULT_THRESHOLD_MIN_SAMPLES,
    DEFAULT_REJECT_THRESHOLD,
    recommend_review_thresholds,
)
from max.server.errors import (
    ExternalServiceError,
    MCPToolError,
    ResourceNotFoundError,
    ValidationError,
)
from max.server.evidence_chain import build_evidence_chain_graph
from max.server.schemas import (
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
            recommendation["target_weight"] = recommendation["suggested_weight"]
        return payload
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


def design_brief_market_sizing_detail(brief_id: str) -> str:
    """Get the market sizing report for a specific design brief."""
    return json.dumps(get_design_brief_market_sizing(brief_id), indent=2)


def design_brief_competitive_landscape_detail(brief_id: str) -> str:
    """Get the competitive landscape report for a specific design brief."""
    return json.dumps(get_design_brief_competitive_landscape(brief_id), indent=2)


def validation_experiments_for_idea_detail(idea_id: str) -> str:
    """Browse validation experiments for a specific idea."""
    return json.dumps(list_validation_experiments(idea_id), indent=2)


def validation_experiment_detail(experiment_id: str) -> str:
    """Get details of a specific validation experiment."""
    return json.dumps(get_validation_experiment(experiment_id), indent=2)


def signal_freshness_detail() -> str:
    """Browse the default signal freshness report."""
    return json.dumps(max_signal_freshness(), indent=2)


def portfolio_overlap_detail() -> str:
    """Browse the default portfolio overlap report."""
    return json.dumps(max_portfolio_overlap(), indent=2)


def source_allocation_detail() -> str:
    """Browse the default source allocation simulation report."""
    return json.dumps(simulate_source_allocation(), indent=2)


def profile_source_recommendations_detail(profile_name: str) -> str:
    """Browse profile source recommendations for a specific profile."""
    return json.dumps(get_profile_source_recommendations(profile_name), indent=2)


def roi_forecast_detail() -> str:
    """Browse the default ROI forecast report."""
    return json.dumps(get_roi_forecast(), indent=2)


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
    mcp.tool(get_design_brief_market_sizing)
    mcp.tool(get_design_brief_competitive_landscape)
    mcp.tool(list_validation_experiments)
    mcp.tool(get_validation_experiment)
    mcp.tool(create_validation_experiment)
    mcp.tool(update_validation_experiment)
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
    mcp.tool(simulate_source_allocation)
    mcp.tool(get_profile_source_recommendations)
    mcp.tool(get_schedule)
    mcp.tool(set_schedule)
    mcp.tool(dry_run_pipeline)
    mcp.tool(get_pipeline_replay_plan)

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
    mcp.resource("design-brief-market-sizing://{brief_id}")(design_brief_market_sizing_detail)
    mcp.resource("design-brief-competitive-landscapes://{brief_id}")(
        design_brief_competitive_landscape_detail
    )
    mcp.resource("ideas://{idea_id}/validation-experiments")(validation_experiments_for_idea_detail)
    mcp.resource("validation-experiments://{experiment_id}")(validation_experiment_detail)
    mcp.resource("signals://freshness")(signal_freshness_detail)
    mcp.resource("portfolio://overlap")(portfolio_overlap_detail)
    mcp.resource("sources://allocation-simulation")(source_allocation_detail)
    mcp.resource("profile-source-recommendations://{profile_name}")(
        profile_source_recommendations_detail
    )
    mcp.resource("roi://forecast")(roi_forecast_detail)

    return mcp
