"""Tests for customer success QBR exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.customer_success_qbr import (
    SCHEMA_VERSION,
    build_customer_success_qbr_export,
    render_customer_success_qbr_csv,
    render_customer_success_qbr_json,
    render_customer_success_qbr_markdown,
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


def test_customer_success_qbr_sorts_accounts_and_renders() -> None:
    report = build_customer_success_qbr_export(_store([
        _unit("bu-2", "Beta", {"account_name": "Beta Co", "segment": "smb", "health_score": 45, "usage_growth": -0.1, "open_risks": ["Low usage"], "renewal_date": "2026-12-01", "expansion_value": 1000}),
        _unit("bu-1", "Acme", {"account_name": "Acme", "segment": "enterprise", "health_score": 90, "usage_growth": 0.2, "achieved_outcomes": ["Launched"], "renewal_date": "2026-06-01", "expansion_value": 50000}),
    ]))

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["account_count"] == 2
    assert [row["account_name"] for row in report["accounts"]] == ["Acme", "Beta Co"]
    assert report["summary"]["risk_count"] == 1
    assert report["expansion_rollups"][0]["segment"] == "enterprise"

    markdown = render_customer_success_qbr_markdown(report)
    rendered_json = render_customer_success_qbr_json(report)
    rows = list(csv.DictReader(io.StringIO(render_customer_success_qbr_csv(report))))
    assert "## Executive Summary" in markdown
    assert "## Risks" in markdown
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rows[0]["account_name"] == "Acme"
