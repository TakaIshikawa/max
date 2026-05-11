from __future__ import annotations

import csv
from io import StringIO

from max.spec.feature_flag_rollout_plan import (
    FEATURE_FLAG_ROLLOUT_PLAN_CSV_COLUMNS,
    FEATURE_FLAG_ROLLOUT_PLAN_SCHEMA_VERSION,
    generate_feature_flag_rollout_plan,
    render_feature_flag_rollout_plan_csv,
    render_feature_flag_rollout_plan_markdown,
)


def test_feature_flag_rollout_plan_shape_and_risk_adapted_stages() -> None:
    plan = generate_feature_flag_rollout_plan(_tact_spec())
    rows = list(csv.DictReader(StringIO(render_feature_flag_rollout_plan_csv(plan))))

    assert plan["schema_version"] == FEATURE_FLAG_ROLLOUT_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.feature_flag_rollout_plan"
    assert {"flags", "rollout_stages", "guardrail_metrics", "rollback_triggers", "owner_handoffs", "evidence_references"} <= set(plan)
    assert plan["summary"]["risk_level"] == "high"
    assert plan["rollout_stages"][1]["timing"] == "5% cohort"
    assert "## Rollout Stages" in render_feature_flag_rollout_plan_markdown(plan)
    assert render_feature_flag_rollout_plan_csv(plan).splitlines()[0] == ",".join(FEATURE_FLAG_ROLLOUT_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "flags"


def _tact_spec() -> dict:
    return {"source": {"idea_id": "bu-flags"}, "project": {"title": "Renewal Router", "specific_user": "CS operator", "workflow_context": "renewal alert workflow"}, "solution": {"technical_approach": "Send Slack and Salesforce write updates."}, "execution": {"risks": ["security review before customer rollout"]}, "evaluation": {"overall_score": 52}}
