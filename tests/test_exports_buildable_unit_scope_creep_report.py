from __future__ import annotations

from max.exports.buildable_unit_scope_creep_report import generate_buildable_unit_scope_creep_report


def test_buildable_unit_scope_creep_report_classifies_creep() -> None:
    report = generate_buildable_unit_scope_creep_report(
        [
            {"unit_id": "u1", "profile": "core", "original_stack": "python", "current_stack": "node", "original_acceptance_criteria": ["a"], "current_acceptance_criteria": ["a"], "added_dependencies": []},
            {"unit_id": "u2", "profile": "core", "original_stack": "python", "current_stack": "python", "original_acceptance_criteria": ["a"], "current_acceptance_criteria": ["a"], "added_dependencies": ["django", "celery"]},
            {"unit_id": "u3", "profile": "growth", "original_stack": "python", "current_stack": "python", "original_acceptance_criteria": ["a"], "current_acceptance_criteria": ["a", "b", "c"], "added_dependencies": []},
            {"unit_id": "u4", "profile": "growth", "original_stack": "python", "current_stack": "python", "original_acceptance_criteria": ["a"], "current_acceptance_criteria": ["a"], "added_dependencies": []},
        ],
        added_criteria_warning=2,
        added_dependency_warning=2,
    )

    assert report["summary"] == {
        "unit_count": 4,
        "creeping_unit_count": 3,
        "stack_change_count": 1,
        "added_dependency_total": 2,
    }
    assert [row["unit_id"] for row in report["unit_rows"]] == ["u1", "u2", "u3", "u4"]
    assert [row["reason"] for row in report["unit_rows"]] == [
        "stack_changed",
        "dependency_growth",
        "acceptance_criteria_growth",
        "stable",
    ]
    assert report["unit_rows"][2]["added_criteria_count"] == 2
