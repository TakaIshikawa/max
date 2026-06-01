from __future__ import annotations

from max.spec.profile_deprecation_sunset_plan import generate_profile_deprecation_sunset_plan


def test_deprecated_profiles_with_active_schedules_block() -> None:
    plan = generate_profile_deprecation_sunset_plan({"profiles": [{"id": "p1", "deprecated": True, "active_schedule": True, "replacement": "p2"}]})
    assert plan["sunset_profiles"][0]["blocking"] is True
    assert plan["schedule_updates"]


def test_profiles_without_replacements_are_archive_only() -> None:
    plan = generate_profile_deprecation_sunset_plan({"profiles": [{"id": "p1", "deprecated": True}]})
    assert "archive profile without replacement" in plan["migration_actions"][0]["action"]


def test_summary_counts_deprecated_blocked_and_ready() -> None:
    plan = generate_profile_deprecation_sunset_plan({"profiles": [{"id": "p1", "deprecated": True, "active_schedule": True}, {"id": "p2", "deprecated": True, "replacement": "p3"}]})
    assert plan["summary"] == {"deprecated_count": 2, "blocked_count": 1, "replacement_ready_count": 1}
