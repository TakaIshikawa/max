"""Tests for competitive win/loss exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.competitive_win_loss import (
    KIND,
    SCHEMA_VERSION,
    build_competitive_win_loss_export,
    render_competitive_win_loss_csv,
    render_competitive_win_loss_json,
    render_competitive_win_loss_markdown,
)


def _unit(
    *,
    unit_id: str = "idea-1",
    title: str = "Enterprise Search",
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = metadata or {}
    return unit


def _store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_builds_schema_source_and_domain_filter() -> None:
    store = _store([_unit(metadata={"competitors": ["Acme"], "deal_outcome": "won"})])

    report = build_competitive_win_loss_export(store, domain="sales")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"]["entity_type"] == "competitive_win_loss"
    assert report["source"]["domain_filter"] == "sales"
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="sales")


def test_normalizes_won_lost_and_open_outcomes() -> None:
    report = build_competitive_win_loss_export(
        _store([
            _unit(unit_id="a", metadata={"competitor": "Acme", "deal_outcome": "closed won", "win_reason": "faster setup"}),
            _unit(unit_id="b", metadata={"competitor": "Beta", "deal_outcome": "LOSS", "loss_reason": "pricing"}),
            _unit(unit_id="c", metadata={"competitor": "Gamma", "deal_outcome": "stalled"}),
        ])
    )

    rows = {row["idea_id"]: row for row in report["opportunities"]}
    assert rows["a"]["outcome"] == "won"
    assert rows["a"]["win_reason"] == "faster setup"
    assert rows["b"]["outcome"] == "lost"
    assert rows["b"]["loss_reason"] == "pricing"
    assert rows["c"]["outcome"] == "open"
    assert report["summary"]["win_rate"] == 50.0


def test_competitor_aggregation_counts_outcomes_and_deal_value() -> None:
    report = build_competitive_win_loss_export(
        _store([
            _unit(unit_id="a", metadata={"competitors": ["Acme", "Beta"], "deal_outcome": "won", "deal_size": 10000}),
            _unit(unit_id="b", metadata={"competitor": "acme", "deal_outcome": "lost", "deal_size": "5,000"}),
            _unit(unit_id="c", metadata={"competitor": "Acme", "deal_outcome": "open", "deal_size": -10}),
        ])
    )

    rollups = {row["competitor"]: row for row in report["competitor_rollups"]}
    assert rollups["Acme"] == {
        "competitor": "Acme",
        "opportunity_count": 3,
        "win_count": 1,
        "loss_count": 1,
        "open_count": 1,
        "win_rate": 50.0,
        "total_deal_value": 15000.0,
    }
    assert rollups["Beta"]["win_count"] == 1
    assert report["summary"]["total_deal_value"] == 25000.0


def test_reason_rollups_separate_win_and_loss_reasons() -> None:
    report = build_competitive_win_loss_export(
        _store([
            _unit(unit_id="a", metadata={"competitor": "Acme", "deal_outcome": "won", "deal_size": 100, "win_reason": "security"}),
            _unit(unit_id="b", metadata={"competitor": "Beta", "deal_outcome": "won", "deal_size": 200, "win_reason": "security"}),
            _unit(unit_id="c", metadata={"competitor": "Acme", "deal_outcome": "lost", "deal_size": 300, "loss_reason": "pricing"}),
            _unit(unit_id="d", metadata={"competitor": "Beta", "deal_outcome": "lost", "deal_size": 400}),
        ])
    )

    assert report["reason_rollups"]["win_reasons"] == [
        {"reason": "security", "opportunity_count": 2, "total_deal_value": 300.0}
    ]
    assert report["reason_rollups"]["loss_reasons"] == [
        {"reason": "Unspecified", "opportunity_count": 1, "total_deal_value": 400.0},
        {"reason": "pricing", "opportunity_count": 1, "total_deal_value": 300.0},
    ]


def test_csv_rendering_has_stable_headers_and_rows() -> None:
    report = build_competitive_win_loss_export(
        _store([
            _unit(
                unit_id="b",
                title="Beta workflow",
                metadata={"competitors": "Zenith, Acme", "deal_outcome": "unknown", "segment": "SMB", "sales_stage": "Demo", "deal_size": "$50,000"},
            ),
            _unit(unit_id="a", title="Alpha workflow", metadata={"competitor": "Acme", "deal_outcome": "won", "deal_size": 10000}),
        ])
    )

    rendered = render_competitive_win_loss_csv(report)
    rows = list(csv.DictReader(io.StringIO(rendered)))

    assert rendered == render_competitive_win_loss_csv(report)
    assert rows[0].keys() == {
        "idea_id",
        "title",
        "competitor",
        "outcome",
        "segment",
        "sales_stage",
        "deal_size",
        "win_reason",
        "loss_reason",
    }
    assert [(row["competitor"], row["outcome"], row["idea_id"]) for row in rows] == [
        ("Acme", "won", "a"),
        ("Acme", "open", "b"),
        ("Zenith", "open", "b"),
    ]
    assert rows[1]["deal_size"] == "50000.0"


def test_empty_store_returns_actionable_report() -> None:
    report = build_competitive_win_loss_export(_store())
    markdown = render_competitive_win_loss_markdown(report)
    rendered_json = render_competitive_win_loss_json(report)
    rendered_csv = render_competitive_win_loss_csv(report)

    assert report["opportunities"] == []
    assert report["competitor_rollups"] == []
    assert report["summary"]["opportunity_count"] == 0
    assert "Add competitor names" in report["recommendations"][0]
    assert "No competitive opportunities found" in markdown
    assert json.loads(rendered_json)["opportunities"] == []
    assert list(csv.DictReader(io.StringIO(rendered_csv))) == []


def test_markdown_and_json_are_deterministic() -> None:
    report = build_competitive_win_loss_export(
        _store([
            _unit(
                metadata={
                    "sales": {"deal_size": "25000", "sales_stage": "Proposal"},
                    "competitors": [{"name": "Nimbus"}],
                    "deal_outcome": "won",
                    "segment": "enterprise",
                    "win_reason": "implementation speed",
                }
            )
        ])
    )

    markdown = render_competitive_win_loss_markdown(report)
    rendered_json = render_competitive_win_loss_json(report)

    assert "# Competitive Win/Loss" in markdown
    assert "## Competitor Rollup" in markdown
    assert "Nimbus" in markdown
    assert markdown.endswith("\n")
    assert rendered_json == render_competitive_win_loss_json(report)
    parsed = json.loads(rendered_json)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert list(parsed.keys()) == sorted(parsed.keys())
