from __future__ import annotations

import json

from max.analysis import generate_design_brief_partner_enablement_plan as exported_generate
from max.analysis.design_brief_partner_enablement_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_partner_enablement_plan,
)


def test_partner_enablement_plan_returns_sorted_segment_rows() -> None:
    brief = {
        "metadata": {
            "partner_enablement_plan": {
                "segments": [
                    {"name": "System integrators", "assets": ["deck"], "certification": ["lab"], "owner": "alliances", "evidence": ["partner call"]},
                    {"name": "App marketplace", "assets": ["listing"], "certification_steps": ["security review"], "dependency_owner": "pm", "evidence": ["launch checklist"]},
                ]
            }
        }
    }

    plan = generate_design_brief_partner_enablement_plan(brief)

    assert plan == generate_design_brief_partner_enablement_plan(brief)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [row["segment"] for row in plan["partner_enablement"]] == ["App marketplace", "System integrators"]
    assert plan["summary"]["plan_status"] == "ready"
    assert exported_generate({})["kind"] == KIND


def test_partner_enablement_plan_reports_assets_certification_and_owner_gaps() -> None:
    plan = generate_design_brief_partner_enablement_plan(
        {"partner_enablement_plan": {"segments": [{"name": "Agencies"}]}}
    )

    assert plan["summary"]["plan_status"] == "blocked"
    assert [gap["id"] for gap in plan["enablement_gaps"]] == [
        "agencies_missing_assets",
        "agencies_missing_certification",
        "agencies_missing_dependency_owner",
    ]
