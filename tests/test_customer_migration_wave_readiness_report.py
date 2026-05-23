from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_customer_migration_wave_readiness_report_export
from max.exports.customer_migration_wave_readiness_report import render_customer_migration_wave_readiness_report_markdown


def test_customer_migration_wave_readiness_groups_blocked_waves() -> None:
    report = build_customer_migration_wave_readiness_report_export(_store([
        _unit("a", {"wave": "wave 1", "customer": "A", "readiness_score": 90}),
        _unit("b", {"wave": "wave 1", "customer": "B", "readiness_score": 50, "blockers": ["DPA"]}),
    ]))

    assert report["summary"]["wave_count"] == 1
    assert report["summary"]["blocked_wave_count"] == 1
    assert report["wave_rows"][0]["launch_recommendation"].startswith("Do not launch")
    assert "Migration Waves" in render_customer_migration_wave_readiness_report_markdown(report)


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
