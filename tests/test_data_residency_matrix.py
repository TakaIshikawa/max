"""Tests for data residency matrix exports."""

from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock

from max.exports.data_residency_matrix import build_data_residency_matrix_export, render_data_residency_matrix_csv, render_data_residency_matrix_markdown


def _unit(metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = "res-1"
    unit.title = "Tenant Data"
    unit.metadata = metadata
    return unit


def test_classifies_region_coverage_and_gaps() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [
        _unit({"data_regions_required": "eu, us, jp", "hosting_regions": ["eu"], "customer_regions": {"eu": True}, "regulated_data_types": ["pii"], "replication_strategy": "regional", "residency_exceptions": ["jp"]})
    ]

    report = build_data_residency_matrix_export(store, domain="enterprise")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="enterprise")
    rows = {row["required_region"]: row for row in report["region_rows"]}
    assert rows["eu"]["coverage_status"] == "covered"
    assert rows["jp"]["coverage_status"] == "exception-approved"
    assert rows["us"]["coverage_status"] == "gap"
    assert rows["us"]["unresolved_gaps"] == ["missing_hosting_region:us"]


def test_aggregates_by_region_and_data_type_and_renders_csv() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [_unit({"data_regions_required": ["eu"], "hosting_regions": [], "regulated_data_types": "pii, financial"})]
    report = build_data_residency_matrix_export(store)

    markdown = render_data_residency_matrix_markdown(report)
    rows = list(csv.DictReader(io.StringIO(render_data_residency_matrix_csv(report))))

    assert "## Region Coverage" in markdown
    assert report["summary"]["by_required_region"][0]["gap_count"] == 1
    assert [row["data_type"] for row in report["summary"]["by_data_type"]] == ["financial", "pii"]
    assert rows[0]["required_region"] == "eu"
