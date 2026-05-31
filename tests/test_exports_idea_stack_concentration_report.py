from __future__ import annotations

from max.exports.idea_stack_concentration_report import generate_idea_stack_concentration_report


def test_idea_stack_concentration_flags_threshold_and_orders_stably() -> None:
    report = generate_idea_stack_concentration_report(
        [
            {"unit_id": "u1", "profile": "p", "recommendation": "build", "stack_tags": ["python"]},
            {"unit_id": "u2", "profile": "p", "recommendation": "build", "stack_tags": ["python"]},
            {"unit_id": "u3", "profile": "p", "recommendation": "build", "stack_tags": ["go"]},
        ],
        concentration_threshold=0.5,
    )

    assert report["rows"][0]["stack"] == "python"
    assert report["rows"][0]["share"] == 0.6667
    assert report["rows"][0]["severity"] == "warn"
