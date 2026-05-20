from __future__ import annotations

from unittest.mock import MagicMock

from max.spec.release_train_calendar_plan import generate_release_train_calendar_plan, render_release_train_calendar_plan_markdown


def _unit() -> MagicMock:
    unit = MagicMock()
    unit.id = "rel-1"
    unit.title = "May Release Train"
    unit.domain = "enterprise"
    unit.buyer = "Release VP"
    unit.specific_user = "QA Lead"
    unit.validation_plan = "pilot signoff"
    return unit


def test_release_train_uses_deterministic_relative_offsets_and_mvp_validation() -> None:
    plan = generate_release_train_calendar_plan(_unit(), None, {"execution": {"dependencies": ["Billing API"], "mvp_scope": ["checkout path"]}})

    assert plan["kind"] == "max.spec.release_train_calendar_plan"
    assert all("T-" in row["offset"] or row["offset"] == "T+0d" for row in plan["milestones"])
    assert "MVP validation" in plan["validation_checkpoints"][0]["checkpoint"]
    assert plan["dependency_deadlines"][0]["dependency"] == "Billing API"


def test_release_train_markdown_renders_milestone_order() -> None:
    markdown = render_release_train_calendar_plan_markdown(generate_release_train_calendar_plan(_unit()))

    assert markdown.index("scope lock") < markdown.index("build complete") < markdown.index("launch")
    assert "## Go/No-Go Reviews" in markdown
