from __future__ import annotations

import csv
from io import StringIO

from max.spec.feature_flag_cleanup_plan import (
    FEATURE_FLAG_CLEANUP_PLAN_CSV_COLUMNS,
    FEATURE_FLAG_CLEANUP_PLAN_SCHEMA_VERSION,
    generate_feature_flag_cleanup_plan,
    render_feature_flag_cleanup_plan_csv,
    render_feature_flag_cleanup_plan_markdown,
)


def test_feature_flag_cleanup_plan_shape_and_evidence() -> None:
    plan = generate_feature_flag_cleanup_plan(_tact_spec("disabled"))
    rows = list(csv.DictReader(StringIO(render_feature_flag_cleanup_plan_csv(plan))))

    assert plan["schema_version"] == FEATURE_FLAG_CLEANUP_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.feature_flag_cleanup_plan"
    assert {"stale_flag_inventory", "owners", "current_exposure", "removal_checklist", "data_config_cleanup", "monitoring", "rollback", "evidence"} <= set(plan)
    assert plan["summary"]["flag_name"] == "renewal_router_v1"
    assert plan["summary"]["extra_approval_required"] is False
    assert "## Removal Checklist" in render_feature_flag_cleanup_plan_markdown(plan)
    assert render_feature_flag_cleanup_plan_csv(plan).splitlines()[0] == ",".join(FEATURE_FLAG_CLEANUP_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "stale_flag_inventory"


def test_feature_flag_cleanup_plan_flags_active_rollout_for_approval() -> None:
    plan = generate_feature_flag_cleanup_plan(_tact_spec("partial"))

    assert plan["summary"]["extra_approval_required"] is True
    assert plan["current_exposure"][0]["severity"] == "high"
    assert "Escalate active or partially rolled-out flags" in plan["current_exposure"][0]["action"]


def _tact_spec(state: str) -> dict:
    return {"source": {"idea_id": "flag-cleanup"}, "project": {"title": "Flag Cleanup", "workflow_context": "renewal routing"}, "flag_cleanup": {"flag_name": "renewal_router_v1", "owner": "platform", "rollout_state": state, "current_exposure": "10% enterprise tenants"}}
