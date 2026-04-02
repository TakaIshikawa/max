"""MCP tools and resources for the max idea service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastmcp import FastMCP

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


# ── Tool functions (callable directly for testing) ──────────────────


def search_ideas(
    query: str | None = None,
    category: str | None = None,
    min_score: float | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search and filter ideas from the max idea engine.

    Returns a list of ideas with their scores and recommendations.
    Use query to filter by title/description keywords.
    Use category to filter by type (mcp_server, cli_tool, library, etc).
    Use min_score to only get ideas above a certain evaluation score.
    """
    store = _get_store()
    try:
        units = store.get_buildable_units(limit=limit * 3)
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
                "status": unit.status,
                "target_users": unit.target_users,
                "score": evaluation.overall_score if evaluation else None,
                "recommendation": evaluation.recommendation if evaluation else None,
            })
            if len(results) >= limit:
                break
        return results
    finally:
        store.close()


def get_idea(id: str) -> dict:
    """Get detailed information about a specific idea including its evaluation.

    Returns the full idea with problem/solution, evaluation scores, strengths/weaknesses.
    """
    store = _get_store()
    try:
        unit = store.get_buildable_unit(id)
        if not unit:
            return {"error": f"Idea not found: {id}"}
        evaluation = store.get_evaluation(id)
        result = {
            "id": unit.id,
            "title": unit.title,
            "one_liner": unit.one_liner,
            "category": unit.category,
            "problem": unit.problem,
            "solution": unit.solution,
            "target_users": unit.target_users,
            "value_proposition": unit.value_proposition,
            "tech_approach": unit.tech_approach,
            "status": unit.status,
        }
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
    finally:
        store.close()


def get_spec(id: str) -> dict:
    """Get the tact-compatible spec for an idea.

    Returns the full spec JSON that can be consumed by tact or similar build orchestrators.
    """
    store = _get_store()
    try:
        spec = store.get_tact_spec(id)
        if not spec:
            return {"error": f"No spec for idea: {id}"}
        return spec.model_dump(by_alias=True)
    finally:
        store.close()


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

    store = _get_store()
    try:
        signal = Signal(
            source_type=source_type,
            source_adapter="mcp",
            title=title,
            content=content,
            url=url,
            tags=tags or [],
        )
        signal = store.insert_signal(signal)
        return {"id": signal.id, "title": signal.title, "status": "created"}
    finally:
        store.close()


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

    store = _get_store()
    try:
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
    finally:
        store.close()


def evaluate_idea(id: str) -> dict:
    """Trigger evaluation of an idea using the LLM-based 7-dimension scoring.

    This calls the Anthropic API to evaluate the idea across pain_severity,
    addressable_scale, build_effort, composability, competitive_density,
    timing_fit, and compounding_value. Returns the evaluation result.
    """
    from max.evaluation.engine import evaluate

    store = _get_store()
    try:
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
    finally:
        store.close()


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

    store = _get_store()
    try:
        index = SemanticIndex(store)
        results = index.find_similar(text, entity_type, threshold=threshold, limit=limit)
        return [{"entity_id": eid, "score": score} for eid, score in results]
    finally:
        store.close()


def get_stats() -> dict:
    """Get statistics about the max idea engine.

    Returns counts of signals, insights, ideas, and average scores.
    """
    store = _get_store()
    try:
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
    finally:
        store.close()


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
    trigger_now: bool = False,
) -> dict:
    """Update the pipeline schedule or trigger an immediate run.

    Set enabled=false to pause, enabled=true to resume.
    Set interval_seconds to change how often the pipeline runs.
    Set trigger_now=true to run the pipeline immediately.
    """
    if _scheduler is None:
        return {"error": "Scheduler not available"}
    _scheduler.update(enabled=enabled, interval_seconds=interval_seconds)
    if trigger_now:
        asyncio.ensure_future(_scheduler.run_once())
    return _scheduler.status()


# ── Resource functions ──────────────────────────────────────────────


def ideas_list() -> str:
    """Browse top ideas from the max idea engine."""
    store = _get_store()
    try:
        units = store.get_buildable_units(limit=20)
        items = []
        for unit in units:
            ev = store.get_evaluation(unit.id)
            items.append({
                "id": unit.id,
                "title": unit.title,
                "one_liner": unit.one_liner,
                "category": unit.category,
                "status": unit.status,
                "score": ev.overall_score if ev else None,
                "recommendation": ev.recommendation if ev else None,
            })
        return json.dumps(items, indent=2)
    finally:
        store.close()


def idea_detail(idea_id: str) -> str:
    """Get details of a specific idea."""
    store = _get_store()
    try:
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            return json.dumps({"error": f"Not found: {idea_id}"})
        evaluation = store.get_evaluation(idea_id)
        result = {
            "id": unit.id,
            "title": unit.title,
            "one_liner": unit.one_liner,
            "category": unit.category,
            "problem": unit.problem,
            "solution": unit.solution,
            "target_users": unit.target_users,
            "value_proposition": unit.value_proposition,
            "status": unit.status,
        }
        if evaluation:
            result["score"] = evaluation.overall_score
            result["recommendation"] = evaluation.recommendation
        return json.dumps(result, indent=2)
    finally:
        store.close()


def spec_detail(idea_id: str) -> str:
    """Get the tact-compatible spec for an idea."""
    store = _get_store()
    try:
        spec = store.get_tact_spec(idea_id)
        if not spec:
            return json.dumps({"error": f"No spec: {idea_id}"})
        return spec.model_dump_json(by_alias=True, indent=2)
    finally:
        store.close()


# ── MCP server factory ─────────────────────────────────────────────


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server with tools and resources."""
    mcp = FastMCP("Max Idea Engine")

    # Register tools
    mcp.tool(search_ideas)
    mcp.tool(get_idea)
    mcp.tool(get_spec)
    mcp.tool(contribute_signal)
    mcp.tool(contribute_idea)
    mcp.tool(evaluate_idea)
    mcp.tool(find_similar)
    mcp.tool(get_stats)
    mcp.tool(get_schedule)
    mcp.tool(set_schedule)

    # Register resources
    mcp.resource("ideas://list")(ideas_list)
    mcp.resource("ideas://{idea_id}")(idea_detail)
    mcp.resource("specs://{idea_id}")(spec_detail)

    return mcp
