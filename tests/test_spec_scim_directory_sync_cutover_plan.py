from __future__ import annotations

from max.spec import generate_scim_directory_sync_cutover_plan
from max.spec.scim_directory_sync_cutover_plan import render_scim_directory_sync_cutover_plan_markdown


def test_scim_directory_sync_cutover_plan_sections_and_defaults() -> None:
    plan = generate_scim_directory_sync_cutover_plan({"source_idp": "Okta", "target_scim_connector": "Max SCIM", "user_scope": ["employees"]})
    markdown = render_scim_directory_sync_cutover_plan_markdown(plan)

    assert plan["sync_scope"]["groups"] == ["Validate default all-groups mapping before cutover."]
    assert "## SCIM Scope" in markdown
    assert "## Reconciliation Checks" in markdown
    assert "## Cutover Checklist" in markdown
    assert "## Rollback" in markdown
    assert "## Approvals" in markdown
    assert "## Monitoring" in markdown
    assert callable(generate_scim_directory_sync_cutover_plan)
