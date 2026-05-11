"""Tests for partner ecosystem map exports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.partner_ecosystem_map import (
    KIND,
    SCHEMA_VERSION,
    build_partner_ecosystem_map_export,
    render_partner_ecosystem_map_json,
    render_partner_ecosystem_map_markdown,
)


def _unit(
    *,
    unit_id: str = "idea-1",
    title: str = "Partner Portal",
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


def test_builds_schema_source_and_direct_partner_rows() -> None:
    store = _store([
        _unit(
            metadata={
                "partners": [{"name": "Salesforce", "ecosystem": "crm", "strategic_value": "strategic", "integration_effort": "medium"}],
                "dependency_notes": ["requires marketplace listing"],
            }
        )
    ])

    report = build_partner_ecosystem_map_export(store, domain="growth")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["source"] == {
        "project": "max",
        "entity_type": "partner_ecosystem_map",
        "domain_filter": "growth",
    }
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="growth")
    row = report["partner_rows"][0]
    assert row["partner_name"] == "Salesforce"
    assert row["partner_type"] == "direct"
    assert row["partner_types"] == ["direct"]
    assert row["ecosystem"] == "crm"
    assert row["priority_tier"] == "tier_1"
    assert "executive sponsorship recommended" in row["dependency_notes"]


def test_classifies_integration_and_channel_partners() -> None:
    report = build_partner_ecosystem_map_export(
        _store([
            _unit(
                metadata={
                    "integration_partners": {"Snowflake": {"ecosystem": "data", "strategic_value": "high", "integration_effort": "high"}},
                    "channel_partners": "Accenture, Deloitte",
                }
            )
        ])
    )

    rows = {row["partner_name"]: row for row in report["partner_rows"]}
    assert rows["Snowflake"]["partner_type"] == "integration"
    assert rows["Snowflake"]["priority_tier"] == "tier_2"
    assert "high integration effort" in rows["Snowflake"]["dependency_notes"]
    assert rows["Accenture"]["partner_type"] == "channel"
    assert rows["Deloitte"]["partner_types"] == ["channel"]
    type_rollups = {row["partner_type"]: row for row in report["summary"]["by_partner_type"]}
    assert type_rollups["integration"]["partner_count"] == 1
    assert type_rollups["channel"]["partner_count"] == 2


def test_consolidates_duplicate_partner_names_within_unit() -> None:
    report = build_partner_ecosystem_map_export(
        _store([
            _unit(
                metadata={
                    "partners": [{"name": "HubSpot", "ecosystem": "crm", "strategic_value": "medium", "integration_effort": "medium"}],
                    "integration_partners": [{"name": "hubspot", "ecosystem": "crm", "strategic_value": "high", "integration_effort": "low"}],
                }
            )
        ])
    )

    assert report["partner_row_count"] == 1
    row = report["partner_rows"][0]
    assert row["partner_name"] == "HubSpot"
    assert row["partner_types"] == ["direct", "integration"]
    assert row["strategic_value_score"] == 3
    assert row["integration_effort_score"] == 1
    assert row["priority_tier"] == "tier_1"


def test_summary_rollups_by_ecosystem_and_priority() -> None:
    report = build_partner_ecosystem_map_export(
        _store([
            _unit(unit_id="a", metadata={"partners": [{"name": "Stripe", "ecosystem": "payments", "strategic_value": 4, "integration_effort": 1}]}),
            _unit(unit_id="b", metadata={"partners": [{"name": "Adyen", "ecosystem": "payments", "strategic_value": 2, "integration_effort": 4}]}),
            _unit(unit_id="c", metadata={"partners": [{"name": "Zendesk", "ecosystem": "support", "strategic_value": 3, "integration_effort": 2}]}),
        ])
    )

    assert report["summary"]["priority_counts"] == {"tier_1": 1, "tier_2": 1, "tier_3": 1}
    ecosystems = {row["ecosystem"]: row for row in report["summary"]["by_ecosystem"]}
    assert ecosystems["payments"]["partner_count"] == 2
    assert ecosystems["payments"]["priority_counts"] == {"tier_1": 1, "tier_2": 0, "tier_3": 1}
    assert ecosystems["support"]["priority_counts"]["tier_2"] == 1


def test_empty_report_is_actionable() -> None:
    report = build_partner_ecosystem_map_export(_store([]))
    markdown = render_partner_ecosystem_map_markdown(report)

    assert report["partner_row_count"] == 0
    assert report["summary"]["priority_counts"] == {"tier_1": 0, "tier_2": 0, "tier_3": 0}
    assert report["recommendations"] == ["Add partner metadata to buildable units before ecosystem planning."]
    assert "No partner metadata found" in markdown


def test_markdown_and_json_are_deterministic_and_rows_sort_by_priority() -> None:
    report = build_partner_ecosystem_map_export(
        _store([
            _unit(unit_id="z", metadata={"partners": [{"name": "Beta", "ecosystem": "crm", "strategic_value": "low", "integration_effort": "high"}]}),
            _unit(unit_id="a", metadata={"partners": [{"name": "Alpha", "ecosystem": "crm", "strategic_value": "strategic", "integration_effort": "low"}]}),
            _unit(unit_id="m", metadata={"partners": [{"name": "Mid", "ecosystem": "analytics", "strategic_value": "high", "integration_effort": "medium"}]}),
        ])
    )

    assert [row["partner_name"] for row in report["partner_rows"]] == ["Alpha", "Mid", "Beta"]
    markdown = render_partner_ecosystem_map_markdown(report)
    rendered_json = render_partner_ecosystem_map_json(report)
    assert "# Partner Ecosystem Map" in markdown
    assert "## Ecosystem Rollup" in markdown
    assert "## Recommendations" in markdown
    assert rendered_json == render_partner_ecosystem_map_json(report)
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
