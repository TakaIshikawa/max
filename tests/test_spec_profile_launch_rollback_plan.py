from __future__ import annotations

import pytest

from max.spec.profile_launch_rollback_plan import generate_profile_launch_rollback_plan


def test_profile_launch_rollback_dedupes_triggers_and_separates_sections() -> None:
    plan = generate_profile_launch_rollback_plan(
        {
            "metadata": {
                "profile_launch_rollback": {
                    "profile": "enterprise-risk",
                    "launch_version": "v3",
                    "rollback_version": "v2",
                    "launch_owner": "profile_owner",
                    "rollback_triggers": ["latency breach", "quality regression", "latency breach"],
                    "affected_sources": ["crm", "billing"],
                    "validation_checks": ["score parity", "score parity", "source freshness"],
                    "communication_channels": ["launch-room"],
                }
            }
        }
    )

    assert [item["name"] for item in plan["trigger_review"]] == ["latency breach", "quality regression"]
    assert [item["name"] for item in plan["validation_checks"]] == ["score parity", "source freshness"]
    assert plan["source_validation"][0]["id"].startswith("PLRS")
    assert plan["stakeholder_communication"][0]["id"].startswith("PLRC")


def test_profile_launch_rollback_validates_required_fields() -> None:
    with pytest.raises(ValueError, match="rollback_triggers"):
        generate_profile_launch_rollback_plan({"metadata": {"profile_launch_rollback": {"profile": "enterprise-risk"}}})
