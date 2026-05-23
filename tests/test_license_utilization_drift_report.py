from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_license_utilization_drift_report_export
from max.exports.license_utilization_drift_report import render_license_utilization_drift_report_markdown


def test_license_utilization_drift_totals_and_statuses() -> None:
    report = build_license_utilization_drift_report_export(_store([
        _unit("a", {"account": "A", "purchased_seats": 10, "assigned_seats": 12, "active_users": 8}),
        _unit("b", {"account": "B", "purchased_seats": 20, "assigned_seats": 10, "active_users": 5}),
    ]))

    assert report["summary"]["total_purchased_seats"] == 30
    assert [row["drift_status"] for row in report["account_rows"]] == ["over_allocated", "under_used"]
    assert "over_allocated" in render_license_utilization_drift_report_markdown(report)


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = unit_id
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store
