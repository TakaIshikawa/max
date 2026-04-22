"""MCP tools and resources for the max idea service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fastmcp import FastMCP

from max.server.evidence_chain import build_evidence_chain_graph
from max.store.db import Store

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
    """
    with _get_store() as store:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}
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


def get_spec_preview(id: str) -> dict:
    """Generate a tact project spec preview for an evaluated idea."""
    from max.spec.generator import generate_spec_preview

    with _get_store() as store:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}

        evaluation = store.get_evaluation(id)
        if not evaluation:
            return {"error": f"Evaluation not found for idea: {id}"}

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


def get_spec_readiness(id: str) -> dict:
    """Evaluate whether an idea is ready for spec handoff."""
    from max.spec.readiness import evaluate_spec_readiness

    with _get_store() as store:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}

        evaluation = store.get_evaluation(id)
        if not evaluation:
            return {"error": f"Evaluation not found for idea: {id}"}

        return evaluate_spec_readiness(unit, evaluation)


def get_implementation_plan(id: str) -> dict:
    """Generate an implementation handoff plan for an evaluated idea."""
    from max.spec.generator import generate_spec_preview
    from max.spec.implementation_plan import generate_implementation_plan

    with _get_store() as store:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}

        evaluation = store.get_evaluation(id)
        if not evaluation:
            return {"error": f"Evaluation not found for idea: {id}"}

        spec_preview = generate_spec_preview(unit, evaluation)
        return generate_implementation_plan(unit, evaluation, spec_preview)


def get_idea_critique(id: str) -> dict:
    """Get persisted quality-loop critique details for an idea."""
    with _get_store() as store:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}
        critiques = store.get_idea_critiques(id)
        return {"id": id, "critiques": critiques}


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
    """Get a persisted design brief with its source idea relationships."""
    with _get_store() as store:
        brief = store.get_design_brief(brief_id)
        if not brief:
            return {"error": f"Design brief not found: {brief_id}"}
        return brief


def get_design_brief_markdown(brief_id: str) -> dict:
    """Render a persisted design brief as Markdown for design handoff."""
    from max.analysis.portfolio_synthesis import render_design_brief_markdown

    with _get_store() as store:
        brief = store.get_design_brief(brief_id)
        if not brief:
            return {"error": f"Design brief not found: {brief_id}"}
        return {"id": brief_id, "markdown": render_design_brief_markdown(brief)}


def get_evidence_pack(id: str) -> dict:
    """Get the evidence pack used for an idea, or reconstruct one from its evidence chain."""
    with _get_store() as store:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}
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


def get_evidence_chain(id: str) -> dict:
    """Get the idea evidence chain as a graph of idea, insights, signals, and typed edges."""
    with _get_store() as store:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}
        return build_evidence_chain_graph(unit, store)


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
    """
    from max.evaluation.engine import evaluate

    with _get_store() as store:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}
        evaluation = evaluate(unit)
        store.insert_evaluation(evaluation)
        store.update_buildable_unit_status(id, "evaluated")
        return {
            "id": id,
            "overall_score": evaluation.overall_score,
            "recommendation": evaluation.recommendation,
            "strengths": evaluation.strengths,
            "weaknesses": evaluation.weaknesses,
        }


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
    """
    from max.analysis.source_reliability import (
        DEFAULT_SIGNAL_LIMIT,
        build_source_reliability_report,
    )
    from max.profiles.loader import load_profile

    adapters: set[str] | None = None
    resolved_profile = None
    resolved_signal_limit = signal_limit or DEFAULT_SIGNAL_LIMIT
    if profile:
        try:
            resolved_profile = load_profile(profile)
        except FileNotFoundError:
            return {"error": f"Profile not found: {profile}"}
        adapters = {source.adapter for source in resolved_profile.sources if source.enabled}
        if signal_limit is None:
            resolved_signal_limit = resolved_profile.signal_limit

    try:
        fetched_since = _parse_time_window(time_window)
        with _get_store() as store:
            report = build_source_reliability_report(
                store,
                signal_limit=resolved_signal_limit,
                source_adapters=adapters,
                fetched_since=fetched_since,
                min_signal_count=min_signal_count,
            )
    except ValueError as e:
        return {"error": str(e)}

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


def max_signal_freshness(
    max_age_days: int = 30,
    source_adapter: str | list[str] | None = None,
    profile: str | None = None,
) -> dict:
    """Return signal freshness and stale-source recommendations.

    Set source_adapter to a comma-delimited string or list of adapter names.
    Set profile to restrict the report to enabled adapters from a named profile.
    """
    from max.analysis.signal_freshness import build_signal_freshness_report
    from max.profiles.loader import load_profile

    requested_adapters = _normalize_source_adapter_filter(source_adapter)
    resolved_profile = None
    adapters = requested_adapters

    if profile:
        try:
            resolved_profile = load_profile(profile)
        except FileNotFoundError:
            return {"error": f"Profile not found: {profile}"}

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
        return {"error": str(e)}

    result = report.to_dict()
    result["filters"] = {
        "profile": resolved_profile.name if resolved_profile else profile,
        "domain": resolved_profile.domain.name if resolved_profile else None,
        "source_adapters": adapters,
        "max_age_days": max_age_days,
    }
    return result


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
    """
    from pydantic import ValidationError

    from max.server.api import run_pipeline_dry_run
    from max.server.schemas import PipelineDryRunRequest

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
    except FileNotFoundError:
        return {"error": f"Profile not found: {profile or 'default'}"}
    except ValidationError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}
    return response.model_dump()


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


def design_briefs_list() -> str:
    """Browse persisted design briefs from the max portfolio synthesis pipeline."""
    return json.dumps(list_design_briefs(), indent=2)


def design_brief_detail(brief_id: str) -> str:
    """Get details of a specific design brief."""
    return json.dumps(get_design_brief(brief_id), indent=2)


def signal_freshness_detail() -> str:
    """Browse the default signal freshness report."""
    return json.dumps(max_signal_freshness(), indent=2)


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
    mcp.tool(get_idea_critique)
    mcp.tool(list_design_briefs)
    mcp.tool(get_design_brief)
    mcp.tool(get_design_brief_markdown)
    mcp.tool(get_evidence_pack)
    mcp.tool(get_evidence_chain)
    mcp.tool(contribute_signal)
    mcp.tool(contribute_idea)
    mcp.tool(evaluate_idea)
    mcp.tool(find_similar)
    mcp.tool(get_stats)
    mcp.tool(max_source_reliability)
    mcp.tool(max_signal_freshness)
    mcp.tool(get_schedule)
    mcp.tool(set_schedule)
    mcp.tool(dry_run_pipeline)

    # Register resources
    mcp.resource("ideas://list")(ideas_list)
    mcp.resource("ideas://{idea_id}")(idea_detail)
    mcp.resource("ideas://{idea_id}/evidence-pack")(evidence_pack_detail)
    mcp.resource("ideas://{idea_id}/evidence-chain")(evidence_chain_detail)
    mcp.resource("ideas://{idea_id}/spec-preview")(spec_preview_detail)
    mcp.resource("design-briefs://list")(design_briefs_list)
    mcp.resource("design-briefs://{brief_id}")(design_brief_detail)
    mcp.resource("signals://freshness")(signal_freshness_detail)

    return mcp
