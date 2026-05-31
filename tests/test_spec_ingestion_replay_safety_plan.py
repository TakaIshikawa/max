from __future__ import annotations

from max.spec.ingestion_replay_safety_plan import generate_ingestion_replay_safety_plan


def test_ingestion_replay_safety_plan_flags_blockers_and_computes_window() -> None:
    plan = generate_ingestion_replay_safety_plan(
        {"source": "rss", "profile": "p", "start_at": "2026-05-01T00:00:00+00:00", "end_at": "2026-05-10T00:00:00+00:00", "dedupe_enabled": False},
        {"rss:p": "2026-05-01T00:00:00+00:00"},
    )

    assert plan["scope"]["duration_hours"] == 216.0
    assert plan["checkpoint_backup"]["expected_checkpoint_after_replay"] == "2026-05-10T00:00:00+00:00"
    assert plan["blockers"] == ["missing checkpoint backup", "broad replay range", "dedupe disabled"]
    assert [step["id"] for step in plan["execution_steps"]] == ["STEP1", "STEP2", "STEP3"]
    assert [step["id"] for step in plan["rollback_steps"]] == ["RB1", "RB2"]
