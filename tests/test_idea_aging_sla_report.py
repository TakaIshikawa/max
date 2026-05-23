from types import SimpleNamespace
from unittest.mock import Mock

from max.exports import build_idea_aging_sla_report_export, render_idea_aging_sla_report_markdown


def test_idea_aging_sla_report_summarizes_and_sorts_overdue_first():
    store = Mock()
    store.get_buildable_units.return_value = [
        SimpleNamespace(id="fresh", title="Fresh", metadata={"created_at": "2099-01-01", "stage": "intake", "sla_days": 30}),
        SimpleNamespace(id="old", title="Old", metadata={"created_at": "2020-01-01", "stage": "review", "sla_days": 10, "owner": "Ana"}),
    ]

    report = build_idea_aging_sla_report_export(store, domain="growth")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="growth")
    assert report["summary"]["idea_count"] == 2
    assert report["summary"]["overdue_count"] == 1
    assert report["summary"]["oldest_age_days"] >= 1000
    assert report["idea_rows"][0]["idea_id"] == "old"
    assert report["overdue_idea_rows"][0]["recommended_next_action"].startswith("Escalate review")


def test_idea_aging_sla_markdown_lists_overdue_before_stage_summary():
    store = Mock()
    store.get_buildable_units.return_value = [
        SimpleNamespace(id="old", title="Old Idea", metadata={"created_at": "2020-01-01", "stage": "backlog", "sla_days": 10}),
    ]

    markdown = render_idea_aging_sla_report_markdown(build_idea_aging_sla_report_export(store))

    assert markdown.index("Old Idea") < markdown.index("Stage Summary")
