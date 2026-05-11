"""Tests for SLA breach risk exports."""

from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock

from max.exports.sla_breach_risk import build_sla_breach_risk_export, render_sla_breach_risk_csv, render_sla_breach_risk_markdown


def _unit(unit_id: str, metadata: dict | None = None) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = f"Unit {unit_id}"
    unit.metadata = metadata or {}
    return unit


def test_flags_independent_breach_risks_and_priority() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [
        _unit("a", {"sla_uptime_target": 99.9, "observed_uptime": 99.7, "response_time_target_ms": 200, "p95_response_time_ms": 350, "error_budget_remaining": 0.05, "customer_tier": "enterprise", "contract_value": 200000}),
        _unit("b", {}),
    ]

    report = build_sla_breach_risk_export(store, domain="platform")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="platform")
    high = report["sla_rows"][0]
    assert high["breach_indicators"] == ["uptime", "latency", "error_budget"]
    assert high["escalation_priority"] == "high"
    assert high["financial_exposure"] == 120000.0
    assert report["sla_rows"][1]["confidence"] == "low"


def test_tier_summary_and_renderers() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [_unit("a", {"observed_uptime": 99.0, "customer_tier": "premium", "contract_value": 50000})]
    report = build_sla_breach_risk_export(store)

    markdown = render_sla_breach_risk_markdown(report)
    rows = list(csv.DictReader(io.StringIO(render_sla_breach_risk_csv(report))))

    assert "## High Priority Breaches" in markdown
    assert "## Tier Aggregation" in markdown
    assert report["summary"]["by_customer_tier"][0]["customer_tier"] == "premium"
    assert rows[0]["customer_tier"] == "premium"
