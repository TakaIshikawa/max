from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.contract_redline_risk_report import (
    build_contract_redline_risk_report_export,
    render_contract_redline_risk_report_json,
    render_contract_redline_risk_report_markdown,
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


def test_contract_risk_scoring_topics_and_sorting() -> None:
    report = build_contract_redline_risk_report_export(
        _store(
            [
                _unit("low", {"account": "Zenith", "redline_count": 1, "liability_cap_status": "standard"}),
                _unit("medium", {"account": "Acme", "redline_count": 4, "non_standard_terms": ["audit"], "security_terms": "custom"}),
                _unit("high", {"account": "Beta", "redline_count": 10, "redline_topics": ["DPA"], "non_standard_terms": ["liability"], "liability_cap_status": "uncapped", "blockers": ["privacy"], "target_close_date": "2026-05-25"}),
            ]
        )
    )

    assert [row["idea_id"] for row in report["contract_rows"]] == ["high", "medium", "low"]
    assert report["contract_rows"][0]["legal_risk_severity"] == "high"
    assert "blockers" in report["contract_rows"][0]["risk_drivers"]
    assert report["risk_topics"][0]["count"] >= 1


def test_domain_forwarding_renderers_and_empty_state() -> None:
    store = _store([])
    report = build_contract_redline_risk_report_export(store, domain="enterprise")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="enterprise")
    assert json.loads(render_contract_redline_risk_report_json(report)) == report
    assert "No contract redline records found" in render_contract_redline_risk_report_markdown(report)
