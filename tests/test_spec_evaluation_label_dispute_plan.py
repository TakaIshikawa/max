from __future__ import annotations

import pytest

from max.spec.evaluation_label_dispute_plan import generate_evaluation_label_dispute_plan


def test_evaluation_label_dispute_plan_validates_quorum() -> None:
    with pytest.raises(ValueError):
        generate_evaluation_label_dispute_plan([], [], quorum=0)


def test_evaluation_label_dispute_plan_respects_reviewer_capacity() -> None:
    plan = generate_evaluation_label_dispute_plan(
        [{"id": "d1", "dimension": "quality"}, {"id": "d2", "dimension": "quality"}],
        [{"id": "r1", "capacity": 1}, {"id": "r2", "capacity": 2}, {"id": "r3", "capacity": 1}],
        quorum=2,
    )

    assert plan["reviewer_assignments"][0]["reviewers"] == ["r1", "r2"]
    assert plan["reviewer_assignments"][1]["reviewers"] == ["r2", "r3"]
    assert all(row["quorum_met"] for row in plan["reviewer_assignments"])


def test_evaluation_label_dispute_plan_groups_disputed_dimensions() -> None:
    plan = generate_evaluation_label_dispute_plan(
        [{"id": "d2", "dimension": "safety"}, {"id": "d1", "dimension": "quality"}, {"id": "d3", "dimension": "safety"}],
        [{"id": "r1"}, {"id": "r2"}],
    )

    assert plan["dimension_groups"] == [
        {"id": "ELD1", "dimension": "quality", "dispute_count": 1},
        {"id": "ELD2", "dimension": "safety", "dispute_count": 2},
    ]


def test_evaluation_label_dispute_plan_orders_disputes_deterministically() -> None:
    plan = generate_evaluation_label_dispute_plan(
        [{"id": "z", "dimension": "tone"}, {"id": "a", "dimension": "accuracy"}],
        [{"id": "r1"}, {"id": "r2"}],
    )

    assert [row["dispute_id"] for row in plan["reviewer_assignments"]] == ["a", "z"]
    assert plan["evidence_packets"][0]["dispute_id"] == "a"
