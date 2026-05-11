"""Tests for localization readiness exports."""

from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock

from max.exports.localization_readiness import build_localization_readiness_export, render_localization_readiness_csv, render_localization_readiness_markdown


def _unit(metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = "loc-1"
    unit.title = "Billing"
    unit.metadata = metadata
    return unit


def test_normalizes_locale_shapes_and_computes_readiness() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [
        _unit({"target_locales": "ja-JP, de-DE", "translated_locales": ["ja-JP"], "currency_support": {"ja-JP": True, "de-DE": True}, "timezone_support": ["ja-JP"], "localized_docs": [], "legal_review_status": {"ja-JP": "approved"}, "market_priority": "high"})
    ]

    report = build_localization_readiness_export(store, domain="growth")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="growth")
    rows = {row["locale"]: row for row in report["locale_rows"]}
    assert rows["ja-JP"]["readiness_pct"] == 80.0
    assert rows["ja-JP"]["launch_blockers"] == ["docs"]
    assert rows["de-DE"]["readiness_pct"] == 20.0
    assert report["summary"]["by_locale"][0]["locale"] == "de-DE"


def test_renderers_include_blockers() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [_unit({"target_locales": ["fr-FR"], "market_priority": "high"})]
    report = build_localization_readiness_export(store)

    markdown = render_localization_readiness_markdown(report)
    rows = list(csv.DictReader(io.StringIO(render_localization_readiness_csv(report))))

    assert "## High Priority Blockers" in markdown
    assert rows[0]["locale"] == "fr-FR"
    assert "translation" in rows[0]["launch_blockers"]
