"""Tests for compliance evidence packet exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.compliance_evidence_packet import (
    SCHEMA_VERSION,
    build_compliance_evidence_packet,
    render_compliance_evidence_packet_csv,
    render_compliance_evidence_packet_json,
    render_compliance_evidence_packet_markdown,
)


def _unit(unit_id: str, title: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_compliance_evidence_packet_surfaces_missing_evidence_and_renders() -> None:
    report = build_compliance_evidence_packet(_store([
        _unit("bu-1", "Access Logs", {"control_id": "SOC2-CC6", "framework": "SOC2", "evidence_url": "https://example.test/evidence", "owner": "Security", "evidence_status": "approved", "review_date": "2026-06-01", "risk_level": "low"}),
        _unit("bu-2", "Data Map", {"control_id": "GDPR-30", "framework": "GDPR", "owner": "Legal", "evidence_status": "failed", "review_date": "2026-05-20", "risk_level": "high"}),
    ]))

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["missing_evidence_count"] == 1
    assert report["missing_evidence"][0]["control_id"] == "GDPR-30"
    assert report["framework_rollups"][0]["framework"] == "gdpr"
    assert report["review_schedule"][0]["review_date"] == "2026-05-20"

    markdown = render_compliance_evidence_packet_markdown(report)
    rendered_json = render_compliance_evidence_packet_json(report)
    rows = list(csv.DictReader(io.StringIO(render_compliance_evidence_packet_csv(report))))
    assert "## Missing Evidence" in markdown
    assert "## Evidence Table" in markdown
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rows[0]["control_id"] == "GDPR-30"
