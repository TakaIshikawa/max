from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from max.exports import build_security_questionnaire_evidence_aging_report_export
from max.exports.security_questionnaire_evidence_aging_report import render_security_questionnaire_evidence_aging_report_markdown


def test_security_questionnaire_evidence_buckets_and_owner_priorities() -> None:
    expired = (date.today() - timedelta(days=3)).isoformat()
    old = (date.today() - timedelta(days=220)).isoformat()
    report = build_security_questionnaire_evidence_aging_report_export(_store([
        _unit("expired", {"evidence_name": "SOC2", "owner": "Ada", "control_area": "trust", "submitted_at": old, "expires_at": expired}),
        _unit("missing", {"evidence_name": "Pen test", "owner": "Ada", "control_area": "security"}),
    ]))

    assert report["summary"]["bucket_counts"]["expired"] == 1
    assert report["summary"]["bucket_counts"]["missing"] == 1
    assert report["owner_priorities"][0]["owner"] == "Ada"
    assert "Owner Renewal Priorities" in render_security_questionnaire_evidence_aging_report_markdown(report)


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
