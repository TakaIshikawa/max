from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_partner_referral_pipeline_coverage_report_export
from max.exports.partner_referral_pipeline_coverage_report import render_partner_referral_pipeline_coverage_report_markdown


def test_partner_referral_pipeline_flags_stale_and_low_conversion() -> None:
    report = build_partner_referral_pipeline_coverage_report_export(_store([
        _unit("a", {"partner": "North", "opportunity": "A", "stage": "referred", "age_days": 45}),
        _unit("b", {"partner": "North", "opportunity": "B", "stage": "qualified"}),
        _unit("c", {"partner": "South", "opportunity": "C", "stage": "closed_won"}),
    ]))

    assert report["summary"]["partner_count"] == 2
    assert report["summary"]["stale_referral_count"] == 1
    assert report["conversion_gaps"][0]["partner"] == "North"
    assert "Partner Coverage" in render_partner_referral_pipeline_coverage_report_markdown(report)


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
