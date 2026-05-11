"""Tests for TactSpec feature flag rollout plan generation."""

from __future__ import annotations

import csv
import io

from max.spec import (
    generate_feature_flag_rollout_plan,
    render_feature_flag_rollout_plan_csv,
    render_feature_flag_rollout_plan_markdown,
)
from max.spec.feature_flag_rollout_plan import FEATURE_FLAG_ROLLOUT_PLAN_CSV_COLUMNS
from max.spec.generator import generate_spec_preview


def test_feature_flag_rollout_plan_shape_and_risk_adapted_stages(sample_unit, sample_evaluation) -> None:
    plan = generate_feature_flag_rollout_plan(generate_spec_preview(sample_unit, sample_evaluation))

    assert plan["kind"] == "max.feature_flag_rollout_plan"
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "flags",
        "rollout_stages",
        "guardrail_metrics",
        "rollback_triggers",
        "owner_handoffs",
        "evidence_references",
    }
    assert [stage["name"] for stage in plan["rollout_stages"]] == ["ramp_1", "ramp_5", "ramp_25", "ramp_50"]

    low = generate_feature_flag_rollout_plan({"project": {"title": "Low Risk"}})
    assert [stage["name"] for stage in low["rollout_stages"]] == ["ramp_5", "ramp_25", "ramp_50", "ramp_100"]


def test_feature_flag_rollout_plan_renderers(sample_unit, sample_evaluation) -> None:
    plan = generate_feature_flag_rollout_plan(generate_spec_preview(sample_unit, sample_evaluation))
    markdown = render_feature_flag_rollout_plan_markdown(plan)
    csv_text = render_feature_flag_rollout_plan_csv(plan)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert "# MCP Test Framework Feature Flag Rollout Plan" in markdown
    assert "## Rollout Stages" in markdown
    assert "## Guardrail Metrics" in markdown
    assert csv_text.splitlines()[0] == ",".join(FEATURE_FLAG_ROLLOUT_PLAN_CSV_COLUMNS)
    assert any(row["section"] == "rollback_triggers" and row["severity"] == "critical" for row in rows)
