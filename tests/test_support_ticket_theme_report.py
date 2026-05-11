"""Tests for support ticket theme report exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.support_ticket_theme_report import (
    SCHEMA_VERSION,
    build_support_ticket_theme_report,
    render_support_ticket_theme_report_csv,
    render_support_ticket_theme_report_json,
    render_support_ticket_theme_report_markdown,
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


def test_support_ticket_theme_report_groups_unknown_and_renders() -> None:
    report = build_support_ticket_theme_report(_store([
        _unit("bu-1", "Login Fix", {"support_theme": "auth", "ticket_count": 12, "severity": "high", "customer_segment": "enterprise", "product_area": "login", "sentiment": "negative", "first_seen_at": "2026-04-01"}),
        _unit("bu-2", "Billing Copy", {"ticket_count": 3, "severity": "low", "product_area": "billing"}),
    ]))

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["summary"]["ticket_count"] == 15
    assert [row["support_theme"] for row in report["theme_rollups"]] == ["auth", "unknown"]
    assert report["rows"][1]["support_theme"] == "unknown"
    assert report["severity_rollups"][0]["severity"] == "high"

    markdown = render_support_ticket_theme_report_markdown(report)
    rendered_json = render_support_ticket_theme_report_json(report)
    rows = list(csv.DictReader(io.StringIO(render_support_ticket_theme_report_csv(report))))
    assert "## Theme Rollup" in markdown
    assert "## Severity Distribution" in markdown
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rows[0]["support_theme"] == "auth"
