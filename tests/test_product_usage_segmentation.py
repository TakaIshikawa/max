"""Tests for product usage segmentation exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.product_usage_segmentation import (
    KIND,
    SCHEMA_VERSION,
    build_product_usage_segmentation_export,
    render_product_usage_segmentation_csv,
    render_product_usage_segmentation_json,
    render_product_usage_segmentation_markdown,
)


def _make_unit(
    *,
    unit_id: str = "bu-001",
    title: str = "Activation Dashboard",
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = metadata or {}
    return unit


def _mock_store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_build_schema_source_and_domain_filter() -> None:
    store = _mock_store([_make_unit()])

    report = build_product_usage_segmentation_export(store, domain="growth")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"]["entity_type"] == "product_usage_segmentation"
    assert report["source"]["domain_filter"] == "growth"
    assert report["source"]["defaults"]["account_segment"] == "unknown"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="growth")


def test_usage_rows_are_grouped_and_sorted_deterministically() -> None:
    report = build_product_usage_segmentation_export(
        _mock_store([
            _make_unit(
                unit_id="bu-2",
                title="Team Reports",
                metadata={
                    "active_users": 20,
                    "active_accounts": 8,
                    "usage_events": 400,
                    "segment": "smb",
                    "plan": "team",
                    "last_activity_at": "2026-04-15",
                },
            ),
            _make_unit(
                unit_id="bu-1",
                title="Enterprise Console",
                metadata={
                    "active_users": 700,
                    "active_accounts": 80,
                    "usage_events": 70_000,
                    "segment": "enterprise",
                    "plan": "enterprise",
                    "last_activity_at": "2026-05-01",
                },
            ),
            _make_unit(
                unit_id="bu-3",
                title="Expansion Alerts",
                metadata={
                    "usage": {
                        "active_users": "150",
                        "active_accounts": "30",
                        "usage_events": "9000",
                    },
                    "segment": "enterprise",
                    "plan": "pro",
                },
            ),
        ])
    )

    assert [row["idea_id"] for row in report["ideas"]] == ["bu-1", "bu-3", "bu-2"]
    assert report["ideas"][0]["usage_intensity"] == "high"
    assert report["ideas"][1]["usage_intensity"] == "medium"
    assert report["ideas"][2]["usage_intensity"] == "low"
    assert report["ideas"][0]["events_per_user"] == 100.0
    assert report["summary"]["active_users"] == 870
    assert report["summary"]["usage_events"] == 79_400


def test_segment_rollups_include_intensity_counts() -> None:
    report = build_product_usage_segmentation_export(
        _mock_store([
            _make_unit(metadata={"active_users": 500, "active_accounts": 10, "usage_events": 50_000, "segment": "enterprise"}),
            _make_unit(unit_id="bu-2", metadata={"active_users": 120, "active_accounts": 2, "usage_events": 3_000, "segment": "enterprise"}),
            _make_unit(unit_id="bu-3", metadata={"active_users": 1, "active_accounts": 1, "usage_events": 5, "segment": "smb"}),
        ])
    )

    assert report["segment_rollups"][0] == {
        "account_segment": "enterprise",
        "idea_count": 2,
        "active_users": 620,
        "active_accounts": 12,
        "usage_events": 53_000,
        "average_events_per_user": 85.48,
        "high_intensity_count": 1,
        "medium_intensity_count": 1,
        "low_intensity_count": 0,
        "no_usage_count": 0,
    }
    assert report["segment_rollups"][1]["account_segment"] == "smb"
    assert report["intensity_rollups"][0]["usage_intensity"] == "high"


def test_missing_metadata_uses_unknown_defaults_without_raising() -> None:
    report = build_product_usage_segmentation_export(_mock_store([_make_unit(metadata={})]))

    row = report["ideas"][0]
    assert row["account_segment"] == "unknown"
    assert row["plan"] == "unknown"
    assert row["usage_intensity"] == "none"
    assert row["active_users"] == 0
    assert row["active_accounts"] == 0
    assert row["usage_events"] == 0
    assert row["last_activity_at"] is None
    assert report["summary"]["unclassified_count"] == 1


def test_empty_store_returns_empty_report_and_renderers() -> None:
    report = build_product_usage_segmentation_export(_mock_store())

    assert report["summary"]["idea_count"] == 0
    assert report["segment_rollups"] == []
    assert report["ideas"] == []
    assert "No buildable units available" in render_product_usage_segmentation_markdown(report)
    assert render_product_usage_segmentation_csv(report).startswith("idea_id,title,account_segment")


def test_markdown_json_and_csv_renderers_are_deterministic() -> None:
    report = build_product_usage_segmentation_export(
        _mock_store([
            _make_unit(
                metadata={
                    "active_users": 250,
                    "active_accounts": 20,
                    "usage_events": 10_000,
                    "segment": "midmarket",
                    "plan": "pro",
                    "last_activity_at": "2026-05-02T00:00:00Z",
                }
            )
        ])
    )

    markdown = render_product_usage_segmentation_markdown(report)
    rendered_json = render_product_usage_segmentation_json(report)
    rendered_csv = render_product_usage_segmentation_csv(report)
    rows = list(csv.DictReader(io.StringIO(rendered_csv)))

    assert "# Product Usage Segmentation" in markdown
    assert "## Segment Rollup" in markdown
    assert "## Idea Usage" in markdown
    assert markdown.endswith("\n")
    assert rendered_json == render_product_usage_segmentation_json(report)
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rendered_csv.splitlines()[0].split(",") == [
        "idea_id",
        "title",
        "account_segment",
        "plan",
        "usage_intensity",
        "active_users",
        "active_accounts",
        "usage_events",
        "events_per_user",
        "events_per_account",
        "last_activity_at",
    ]
    assert rows[0]["usage_intensity"] == "medium"
    assert rows[0]["events_per_user"] == "40.0"
    assert rendered_csv.endswith("\n")
