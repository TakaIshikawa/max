from __future__ import annotations

import pytest

from max.spec.backup_restore_drill_plan import generate_backup_restore_drill_plan


def test_backup_restore_drill_plan_contains_execution_phases() -> None:
    plan = generate_backup_restore_drill_plan(_spec())

    assert plan["summary"]["system_name"] == "billing warehouse"
    assert [item["name"] for item in plan["pre_drill_preparation"]] == ["daily snapshot", "wal archive"]
    assert [item["name"] for item in plan["data_validation"]] == ["checksum match", "record counts"]
    assert set(plan) >= {"restore_execution", "incident_criteria", "cleanup", "lessons_learned"}


def test_backup_restore_drill_plan_is_deterministic() -> None:
    assert generate_backup_restore_drill_plan(_spec()) == generate_backup_restore_drill_plan(_spec())


@pytest.mark.parametrize("field,match", [("backup_sources", "backup sources"), ("restore_target", "restore target"), ("rpo", "RPO"), ("rto", "RTO"), ("owners", "owners"), ("validation_checks", "validation checks")])
def test_backup_restore_drill_plan_validates_required_inputs(field: str, match: str) -> None:
    hints = dict(_spec()["metadata"]["backup_restore_drill"])
    hints[field] = []

    with pytest.raises(ValueError, match=match):
        generate_backup_restore_drill_plan({"metadata": {"backup_restore_drill": hints}})


def _spec() -> dict:
    return {
        "metadata": {
            "backup_restore_drill": {
                "system_name": "billing warehouse",
                "backup_sources": ["wal archive", "daily snapshot"],
                "restore_target": "isolated restore account",
                "rpo": "15 minutes",
                "rto": "2 hours",
                "owners": ["sre lead", "data owner"],
                "drill_date": "2026-08-01",
                "validation_checks": ["record counts", "checksum match"],
                "rollback_criteria": "delete restore if checksum fails",
            }
        }
    }
