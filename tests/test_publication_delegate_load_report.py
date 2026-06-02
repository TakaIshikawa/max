from __future__ import annotations

import json

from max.exports.publication_delegate_load_report import (
    build_publication_delegate_load_report,
    render_publication_delegate_load_report_json,
    render_publication_delegate_load_report_markdown,
)


def test_publication_delegate_load_computes_utilization_and_overload_order() -> None:
    report = build_publication_delegate_load_report(
        [
            {"delegate": "Bea", "destination": "docs", "profile": "enterprise", "pending_count": 8, "oldest_pending_hours": 12, "capacity_limit": 4},
            {"delegate": "Ari", "destination": "slack", "profile": "default", "pending_count": 5, "oldest_pending_hours": 80, "capacity_limit": 5},
            {"delegate": "Cal", "destination": "docs", "profile": "default", "pending_count": 2, "oldest_pending_hours": 10, "capacity_limit": 0},
            {"delegate": "Dee", "destination": "email", "profile": "default", "pending_count": 1, "oldest_pending_hours": 2, "capacity_limit": 5},
            "malformed",
        ],
        oldest_pending_sla_hours=48,
    )

    assert [(row["delegate"], row["utilization"], row["overload_reasons"]) for row in report["overloaded_delegates"]] == [
        ("Bea", 2.0, ["capacity_exceeded"]),
        ("Ari", 1.0, ["sla_exceeded"]),
        ("Cal", 1.0, ["zero_capacity"]),
    ]
    assert report["summary"]["pending_count"] == 16
    assert report["summary"]["overloaded_delegate_count"] == 3
    assert report["destination_hot_spots"][0]["destination"] == "docs"
    assert report["destination_hot_spots"][0]["pending_count"] == 10


def test_publication_delegate_load_renderers() -> None:
    report = build_publication_delegate_load_report(
        [{"delegate": "Bea", "destination": "docs", "pending_count": 8, "oldest_pending_hours": 12, "capacity_limit": 4}]
    )

    rendered = render_publication_delegate_load_report_json(report)
    assert rendered.endswith("\n")
    assert json.loads(rendered)["summary"]["overloaded_delegate_count"] == 1
    assert "Bea -> docs" in render_publication_delegate_load_report_markdown(report)
