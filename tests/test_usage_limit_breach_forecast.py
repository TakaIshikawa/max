from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.usage_limit_breach_forecast import (
    build_usage_limit_breach_forecast_export,
    render_usage_limit_breach_forecast_json,
    render_usage_limit_breach_forecast_markdown,
)


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


def test_usage_forecast_calculates_risks_and_sorts() -> None:
    report = build_usage_limit_breach_forecast_export(
        _store(
            [
                _unit("normal", {"account": "Zenith", "plan_limit": 1000, "current_usage": 200, "usage_growth_rate": 10}),
                _unit("watch", {"account": "Beta", "plan_limit": 1000, "current_usage": 800, "usage_growth_rate": 10}),
                _unit("imminent", {"account": "Delta", "plan_limit": 1000, "current_usage": 900, "usage_growth_rate": 200, "measurement_window_days": 30}),
                _unit("breached", {"account": "Acme", "plan_limit": 1000, "current_usage": 1200, "usage_growth_rate": 0}),
                _unit("invalid", {"account": "Omega", "plan_limit": "bad", "current_usage": "nope"}),
            ]
        )
    )

    assert [row["idea_id"] for row in report["forecast_rows"][:4]] == ["breached", "imminent", "watch", "normal"]
    assert report["forecast_rows"][0]["utilization_percent"] == 120.0
    assert report["forecast_rows"][1]["days_to_breach"] == 15
    assert report["summary"]["risk_counts"]["breached"] == 1
    assert report["forecast_rows"][-1]["plan_limit"] is None


def test_domain_forwarding_renderers_and_empty_state() -> None:
    store = _store([])
    report = build_usage_limit_breach_forecast_export(store, domain="saas")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="saas")
    assert json.loads(render_usage_limit_breach_forecast_json(report)) == report
    assert "No usage limit records found" in render_usage_limit_breach_forecast_markdown(report)
