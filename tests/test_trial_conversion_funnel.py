"""Tests for trial conversion funnel exports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.trial_conversion_funnel import (
    KIND,
    SCHEMA_VERSION,
    build_trial_conversion_funnel_export,
    render_trial_conversion_funnel_json,
    render_trial_conversion_funnel_markdown,
)


def _unit(
    *,
    unit_id: str = "idea-1",
    title: str = "Trial Onboarding",
    domain: str = "growth",
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.domain = domain
    unit.metadata = metadata or {}
    return unit


def _store(units: list[MagicMock] | None = None) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    return store


def test_builds_required_keys_and_source_domain() -> None:
    store = _store([_unit()])

    report = build_trial_conversion_funnel_export(store, domain="growth")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"]["entity_type"] == "trial_conversion_funnel"
    assert report["source"]["domain_filter"] == "growth"
    assert set(report) == {"schema_version", "kind", "generated_at", "source", "funnel", "summary", "recommendations"}
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="growth")


def test_rows_include_counts_rates_segments_and_risk_notes() -> None:
    report = build_trial_conversion_funnel_export(
        _store([
            _unit(
                unit_id="a",
                metadata={
                    "segment": "Enterprise",
                    "funnel_stage": "activated",
                    "trial_count": 100,
                    "activation_count": 60,
                    "conversion_count": 25,
                    "risk_notes": ["low sales assist"],
                },
            )
        ])
    )

    row = report["funnel"][0]
    assert row["segment"] == "enterprise"
    assert row["funnel_stage"] == "activated"
    assert row["trial_count"] == 100
    assert row["activation_count"] == 60
    assert row["conversion_count"] == 25
    assert row["activation_rate_pct"] == 60.0
    assert row["conversion_rate_pct"] == 25.0
    assert row["risk_notes"] == ["low sales assist"]
    assert report["summary"]["conversion_rate_pct"] == 25.0


def test_zero_denominators_and_missing_metadata_do_not_error() -> None:
    report = build_trial_conversion_funnel_export(_store([_unit(metadata={"activation_count": 5, "conversion_count": 2})]))

    row = report["funnel"][0]
    assert row["trial_count"] == 0
    assert row["activation_rate_pct"] == 0.0
    assert row["conversion_rate_pct"] == 0.0
    assert "missing trial denominator" in row["risk_notes"]
    assert report["summary"]["zero_trial_unit_count"] == 1


def test_rows_sort_by_segment_stage_order_and_idea_id() -> None:
    report = build_trial_conversion_funnel_export(
        _store([
            _unit(unit_id="z", metadata={"segment": "smb", "stage": "converted"}),
            _unit(unit_id="b", metadata={"segment": "enterprise", "stage": "activated"}),
            _unit(unit_id="a", metadata={"segment": "enterprise", "stage": "activated"}),
            _unit(unit_id="q", metadata={"segment": "enterprise", "stage": "signup"}),
        ])
    )

    assert [row["idea_id"] for row in report["funnel"]] == ["q", "a", "b", "z"]


def test_empty_report_is_actionable() -> None:
    report = build_trial_conversion_funnel_export(_store())
    markdown = render_trial_conversion_funnel_markdown(report)

    assert report["funnel"] == []
    assert report["summary"]["unit_count"] == 0
    assert report["summary"]["activation_rate_pct"] == 0.0
    assert "Add trial_count" in report["recommendations"][0]
    assert "No buildable units available" in markdown


def test_markdown_and_json_are_deterministic() -> None:
    report = build_trial_conversion_funnel_export(
        _store([
            _unit(metadata={"segment": "smb", "stage": "paid", "trial_count": "10", "activation_count": "8", "conversion_count": "3"}),
        ])
    )

    markdown = render_trial_conversion_funnel_markdown(report)
    rendered_json = render_trial_conversion_funnel_json(report)
    assert "# Trial Conversion Funnel" in markdown
    assert "## Segment Rollup" in markdown
    assert rendered_json == render_trial_conversion_funnel_json(report)
    parsed = json.loads(rendered_json)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert list(parsed.keys()) == sorted(parsed.keys())
