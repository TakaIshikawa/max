from __future__ import annotations

import copy
import csv
import json
from io import StringIO

from max.analysis.design_validation import (
    SCHEMA_VERSION,
    build_validation_plan,
    render_validation_plan,
    render_validation_plan_markdown,
    validation_plan_filename,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def _unit(unit_id: str = "bu-1") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="AgentAdversarialBench",
        one_liner="Adversarial workflow benchmark for tool-using agents",
        category="eval_framework",
        problem="Teams cannot test agent security and workflow capability together.",
        solution="Run workflow fixtures with embedded attack payloads.",
        value_proposition="Ship safer agents without blocking useful workflows.",
        specific_user="platform engineer deploying AI agents",
        buyer="engineering manager",
        workflow_context="CI gate before agent production deployment",
        current_workaround="manual prompt testing",
        why_now="MCP adoption makes agent tool security urgent.",
        validation_plan="Run against three agent frameworks and publish scorecards.",
        first_10_customers="Agent framework maintainers; Platform teams",
        domain_risks=["Framework adapters may change quickly"],
        tech_approach="Python package with YAML fixtures and CLI runner",
        domain="developer-tools",
        status="approved",
        quality_score=7.5,
    )


def _seed_brief(tmp_path) -> tuple[Store, dict]:
    unit = _unit()
    store = Store(str(tmp_path / "max.db"))
    store.insert_buildable_unit(unit)
    brief_id = store.insert_design_brief(
        ProjectBrief(
            title="AgentAdversarialBench",
            domain="developer-tools",
            theme="agent-security-evaluation",
            lead=Candidate(unit=unit),
            readiness_score=86.0,
            why_this_now="Agent tool use is growing.",
            merged_product_concept="Run adversarial workflow fixtures.",
            synthesis_rationale="Strong lead idea.",
            mvp_scope=["CLI runner", "Fixture library"],
            first_milestones=["Prototype CLI"],
            validation_plan="Run with three teams.",
            risks=["Framework churn"],
            source_idea_ids=[unit.id],
        )
    )
    brief = store.get_design_brief(brief_id)
    assert brief is not None
    return store, brief


def test_build_validation_plan_uses_persisted_brief_and_source_idea_fields(tmp_path) -> None:
    store, brief = _seed_brief(tmp_path)
    try:
        plan = build_validation_plan(store, brief, generated_at="2026-04-22T00:00:00+00:00")
    finally:
        store.close()

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["source"]["id"] == brief["id"]
    assert plan["design_brief"]["title"] == "AgentAdversarialBench"
    assert "target_user_hypotheses" in plan
    assert "platform engineer deploying AI agents" in plan["target_user_hypotheses"][0]["hypothesis"]
    assert "Agent framework maintainers" in plan["recruiting_criteria"]["ideal_participants"]
    assert plan["interview_script"]["duration_minutes"] == 30
    assert plan["smoke_test_landing_page_copy"]["headline"] == "AgentAdversarialBench"
    assert plan["success_metrics"]
    assert plan["failure_thresholds"]
    assert plan["two_week_timeline"][-1]["days"] == "10"
    assert "Framework adapters may change quickly" in plan["risks_to_probe"]
    assert any(idea["id"] == "bu-1" for idea in plan["source_ideas"])


def test_render_validation_plan_markdown_and_json(tmp_path) -> None:
    store, brief = _seed_brief(tmp_path)
    try:
        plan = build_validation_plan(store, brief, generated_at="2026-04-22T00:00:00+00:00")
    finally:
        store.close()

    markdown = render_validation_plan_markdown(plan)
    assert "# Validation Plan: AgentAdversarialBench" in markdown
    assert "## Target User Hypotheses" in markdown
    assert "## Smoke-Test Landing Page Copy" in markdown
    assert "## Two-Week Timeline" in markdown

    payload = json.loads(render_validation_plan(plan, fmt="json"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["design_brief"]["id"] == brief["id"]


def test_render_validation_plan_csv_includes_execution_rows(tmp_path) -> None:
    store, brief = _seed_brief(tmp_path)
    try:
        plan = build_validation_plan(store, brief, generated_at="2026-04-22T00:00:00+00:00")
    finally:
        store.close()

    payload = copy.deepcopy(plan)
    payload["validation_experiments"] = [
        {
            "id": "EXP1",
            "hypothesis": "Teams will run an adversarial workflow fixture before release.",
            "method": "concierge pilot",
            "metric": "Pilot completion",
            "target": "3 teams complete one fixture",
            "owner": "product",
            "cadence": "weekly",
            "risk": "Adapters drift",
            "evidence_refs": ["signal:pilot-1"],
            "source_fields": ["validation_plan", "first_10_customers"],
        }
    ]
    payload["missing_inputs"] = [{"field": "pricing", "reason": "No pilot price evidence yet"}]
    payload["evidence_refs"] = [{"id": "signal:pilot-1", "source_fields": ["validation_plan"]}]

    rows = list(csv.DictReader(StringIO(render_validation_plan(payload, fmt="csv"))))
    sections = [row["section"] for row in rows]

    assert sections[:4] == [
        "validation_experiment",
        "target_user_hypothesis",
        "target_user_hypothesis",
        "target_user_hypothesis",
    ]
    assert "success_metric" in sections
    assert "risk_to_probe" in sections
    assert "missing_input" in sections
    assert sections[-2:] == ["evidence_reference", "evidence_reference"]

    experiment = rows[0]
    assert experiment["design_brief_id"] == brief["id"]
    assert experiment["design_brief_title"] == "AgentAdversarialBench"
    assert experiment["item_id"] == "EXP1"
    assert experiment["method"] == "concierge pilot"
    assert experiment["metric"] == "Pilot completion"
    assert experiment["target"] == "3 teams complete one fixture"
    assert experiment["owner"] == "product"
    assert experiment["cadence"] == "weekly"
    assert experiment["risk"] == "Adapters drift"
    assert experiment["evidence_refs"] == "signal:pilot-1"
    assert experiment["source_idea_ids"] == "bu-1"
    assert experiment["source_fields"] == "validation_plan;first_10_customers"

    missing = next(row for row in rows if row["section"] == "missing_input")
    assert missing["item_id"] == "pricing"
    assert missing["target"] == "No pilot price evidence yet"


def test_render_validation_plan_csv_sparse_plan_is_header_only() -> None:
    plan = {"design_brief": {"id": "db-sparse", "title": "Sparse", "source_idea_ids": []}}

    assert render_validation_plan(plan, fmt="csv") == (
        "design_brief_id,design_brief_title,section,item_id,hypothesis,method,metric,"
        "target,owner,cadence,risk,evidence_refs,source_idea_ids,source_fields\n"
    )


def test_render_validation_plan_csv_escapes_and_is_deterministic(tmp_path) -> None:
    store, brief = _seed_brief(tmp_path)
    try:
        plan = build_validation_plan(store, brief, generated_at="2026-04-22T00:00:00+00:00")
    finally:
        store.close()

    payload = copy.deepcopy(plan)
    payload["validation_experiments"] = [
        {
            "id": "EXP,2",
            "hypothesis": "User says \"yes\"\nthen books a pilot",
            "method": "landing page, interview",
            "metric": "CTA conversion",
            "target": "8%+",
        }
    ]

    first = render_validation_plan(payload, fmt="csv")
    second = render_validation_plan(payload, fmt="csv")

    assert first == second
    assert '"EXP,2"' in first
    assert '"User says ""yes""\nthen books a pilot"' in first
    rows = list(csv.DictReader(StringIO(first)))
    assert rows[0]["item_id"] == "EXP,2"
    assert rows[0]["hypothesis"] == "User says \"yes\"\nthen books a pilot"


def test_validation_plan_filename_supports_csv_extension() -> None:
    brief = {"id": "db-123"}

    assert validation_plan_filename(brief, fmt="csv") == "db-123-validation-plan.csv"
    assert validation_plan_filename(brief, fmt="json") == "db-123-validation-plan.json"
    assert validation_plan_filename(brief, fmt="markdown") == "db-123-validation-plan.md"
