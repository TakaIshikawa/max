from __future__ import annotations

import json

from max.analysis.design_brief_customer_cutover_rehearsal_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_customer_cutover_rehearsal_plan,
)


def test_customer_cutover_rehearsal_plan_normalizes_sections() -> None:
    plan = generate_design_brief_customer_cutover_rehearsal_plan(
        {
            "metadata": {
                "customer_cutover_rehearsal_plan": {
                    "rehearsal_windows": [{"name": "dry run 2", "window": "2026-07-02"}, {"name": "dry run 1", "window": "2026-07-01"}],
                    "participants": [{"name": "customer admin", "owner": "CSM"}],
                    "dependencies": [{"name": "VPN allowlist", "owner": "IT"}],
                    "validation_checks": [{"name": "record counts", "owner": "Data", "evidence": ["EV1"]}],
                    "rollback_contacts": [{"name": "SRE lead", "owner": "SRE"}],
                    "evidence": ["EV1", "EV2"],
                }
            }
        }
    )

    assert plan["kind"] == KIND
    assert plan["schema_version"] == SCHEMA_VERSION
    assert [row["name"] for row in plan["rehearsal_windows"]] == ["dry run 1", "dry run 2"]
    assert plan["summary"]["gap_count"] == 0
    assert plan["evidence_references"] == ["EV1", "EV2"]
    assert json.loads(json.dumps(plan)) == plan


def test_customer_cutover_rehearsal_plan_reports_required_gaps() -> None:
    plan = generate_design_brief_customer_cutover_rehearsal_plan(
        {"customer_cutover_rehearsal_plan": {"validation_checks": [{"name": "checksum"}]}}
    )

    assert [gap["id"] for gap in plan["readiness_gaps"]] == [
        "missing_rehearsal_window",
        "missing_rollback_contact",
        "checksum_missing_owner",
    ]
    assert json.loads(json.dumps(plan)) == plan
