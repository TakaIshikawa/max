from types import SimpleNamespace
from unittest.mock import Mock

from max.exports import (
    build_insight_confidence_decay_report_export,
    render_insight_confidence_decay_report_markdown,
)


def test_confidence_decay_report_clamps_and_derives_decay_points():
    store = Mock()
    store.get_buildable_units.return_value = [
        SimpleNamespace(id="stable", title="Stable", metadata={"original_confidence": 80, "current_confidence": 76, "owner": "Ana"}),
        SimpleNamespace(id="decayed", title="Decayed", metadata={"original_confidence": 130, "current_confidence": "-5", "days_without_support": 95, "owner": "Bo"}),
        SimpleNamespace(id="explicit", title="Explicit", metadata={"original_confidence": 70, "current_confidence": 62, "decay_points": 17}),
    ]

    report = build_insight_confidence_decay_report_export(store, domain="research")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="research")
    assert report["summary"]["decayed_insight_count"] == 3
    assert report["summary"]["average_decay_points"] == 40.33
    decayed = next(row for row in report["insight_rows"] if row["insight_id"] == "decayed")
    assert decayed["original_confidence"] == 100
    assert decayed["current_confidence"] == 0
    assert decayed["decay_points"] == 100


def test_confidence_decay_markdown_lists_refresh_queue_before_stable():
    store = Mock()
    store.get_buildable_units.return_value = [
        SimpleNamespace(id="stable", title="Stable Insight", metadata={"original_confidence": 80, "current_confidence": 80}),
        SimpleNamespace(id="refresh", title="Refresh Insight", metadata={"original_confidence": 90, "current_confidence": 50}),
    ]

    markdown = render_insight_confidence_decay_report_markdown(build_insight_confidence_decay_report_export(store))

    assert markdown.index("Refresh Insight") < markdown.index("Stable Insights")
    assert "Stable Insight" in markdown
