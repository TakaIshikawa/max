from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_incident_sla_breach_trend_report_export
from max.exports.incident_sla_breach_trend_report import render_incident_sla_breach_trend_report_markdown


def test_incident_sla_breach_trend_totals_by_period_and_severity() -> None:
    report = build_incident_sla_breach_trend_report_export(_store([
        _unit("i1", {"incident_id": "i1", "period": "2026-05", "severity": "high", "breach_duration_minutes": 90}),
        _unit("i2", {"incident_id": "i2", "period": "2026-05", "severity": "high", "breach_duration_minutes": 45}),
    ]))

    assert report["summary"]["total_breach_minutes"] == 135
    assert report["trend_buckets"][0]["trend"] == "worsening"
    assert report["corrective_actions"][0].startswith("Escalate worsening")
    assert "Trend Buckets" in render_incident_sla_breach_trend_report_markdown(report)


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
