from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from max.exports import build_data_processing_agreement_renewal_report_export
from max.exports.data_processing_agreement_renewal_report import render_data_processing_agreement_renewal_report_markdown


def test_data_processing_agreement_renewal_buckets_urgency_and_risk() -> None:
    soon = (date.today() + timedelta(days=10)).isoformat()
    report = build_data_processing_agreement_renewal_report_export(_store([
        _unit("a", {"customer": "A", "renewal_date": soon, "jurisdiction": "EU", "subprocessor_exposure": ["hosting"], "owner": "Legal"}),
        _unit("b", {"vendor": "B", "renewal_date": (date.today() + timedelta(days=120)).isoformat(), "owner": "Ops"}),
    ]))

    assert report["summary"]["bucket_counts"]["due_30"] == 1
    assert report["summary"]["high_risk_count"] == 1
    assert report["owner_actions"][0]["owner"] == "Legal"
    assert "Owner Renewal Actions" in render_data_processing_agreement_renewal_report_markdown(report)


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
