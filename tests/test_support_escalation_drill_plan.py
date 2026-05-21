from __future__ import annotations

import json

from max.spec.support_escalation_drill_plan import generate_support_escalation_drill_plan


def test_support_escalation_drill_plan_rich_input() -> None:
    report = generate_support_escalation_drill_plan(_brief())

    assert report == generate_support_escalation_drill_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert [row["scenario"] for row in report["scenarios"]] == ["billing outage", "webhook delay"]
    assert report["summary"]["ready_count"] == 2
    assert report["summary"]["blocked_count"] == 0
    assert report["readiness_warnings"] == []


def test_support_escalation_drill_plan_flags_missing_paths() -> None:
    report = generate_support_escalation_drill_plan({})

    assert [row["warning"] for row in report["readiness_warnings"]] == [
        "missing paging owner",
        "missing customer communication path",
        "missing success criteria",
    ]


def _brief() -> dict:
    return {
        "support_escalation_drill": {
            "scenarios": [{"scenario": "webhook delay", "owner": "Support"}, {"scenario": "billing outage", "owner": "Support"}],
            "escalation_tiers": [{"tier": "tier 1"}, {"tier": "tier 2"}],
            "paging_paths": [{"path": "PagerDuty payments", "owner": "Support lead"}],
            "communications": [{"checkpoint": "customer status page"}],
            "success_criteria": [{"criterion": "page acknowledged under five minutes"}],
            "owners": [{"owner": "Support lead"}],
            "evidence_links": ["drill://support"],
            "follow_up_actions": [{"action": "file drill notes"}],
        }
    }
