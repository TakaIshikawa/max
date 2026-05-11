"""Tests for buyer committee alignment exports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.buyer_committee_alignment import (
    KIND,
    SCHEMA_VERSION,
    build_buyer_committee_alignment_export,
    render_buyer_committee_alignment_json,
    render_buyer_committee_alignment_markdown,
)


def _unit(
    *,
    unit_id: str = "bu-001",
    title: str = "Enterprise Workflow",
    domain: str = "sales",
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


def test_full_committee_coverage_accepts_aliases() -> None:
    store = _store(
        [
            _unit(
                metadata={
                    "buyer_roles": ["budget owner", "champion"],
                    "stakeholders": [
                        {"role": "technical buyer", "name": "IT"},
                        {"role": "security", "concerns": ["SOC2"]},
                    ],
                    "proof_points": {"end-user": ["Saves operators 4 hours weekly"]},
                }
            )
        ]
    )

    report = build_buyer_committee_alignment_export(store)
    row = report["units"][0]

    assert row["alignment_score"] == 100.0
    assert row["missing_roles"] == []
    assert row["covered_roles"] == [
        "economic_buyer",
        "champion",
        "technical_evaluator",
        "legal_security",
        "end_user",
    ]
    assert report["summary"]["fully_covered_units"] == 1
    assert report["recommendations"] == ["Maintain role-specific proof points for every committee member."]


def test_missing_roles_score_summary_and_next_action() -> None:
    report = build_buyer_committee_alignment_export(
        _store(
            [
                _unit(
                    unit_id="gap",
                    title="Gap Unit",
                    metadata={
                        "buyer_roles": ["champion"],
                        "decision_criteria": ["architect review"],
                    },
                )
            ]
        )
    )

    row = report["units"][0]

    assert row["alignment_score"] == 40.0
    assert row["covered_roles"] == ["champion", "technical_evaluator"]
    assert row["missing_roles"] == ["economic_buyer", "legal_security", "end_user"]
    assert row["recommended_next_action"] == "Validate budget owner value metrics"
    assert report["summary"]["units_with_gaps"] == 1
    assert report["summary"]["role_coverage"]["economic_buyer"] == {
        "covered_units": 0,
        "missing_units": 1,
    }
    assert "Close economic buyer gaps on 1 unit(s)." in report["recommendations"]


def test_empty_report_is_actionable() -> None:
    report = build_buyer_committee_alignment_export(_store([]))
    markdown = render_buyer_committee_alignment_markdown(report)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["unit_count"] == 0
    assert report["summary"]["average_alignment_score"] == 0.0
    assert report["recommendations"] == [
        "Add buyer committee metadata to buildable units before running alignment review.",
        "Capture at least one proof point or decision criterion for each required buyer role.",
    ]
    assert "No buildable units available" in markdown


def test_domain_filter_is_passed_to_store_and_source() -> None:
    store = _store([_unit()])

    report = build_buyer_committee_alignment_export(store, domain="enterprise")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="enterprise")
    assert report["source"] == {
        "project": "max",
        "entity_type": "buyer_committee_alignment",
        "domain_filter": "enterprise",
    }


def test_deterministic_sorting_and_rendering() -> None:
    report = build_buyer_committee_alignment_export(
        _store(
            [
                _unit(unit_id="b", title="Beta", metadata={"buyer_roles": ["champion"]}),
                _unit(
                    unit_id="a",
                    title="Alpha",
                    metadata={"buyer_roles": ["budget owner", "champion", "technical evaluator"]},
                ),
            ]
        )
    )

    markdown = render_buyer_committee_alignment_markdown(report)
    rendered_json = render_buyer_committee_alignment_json(report)

    assert [row["idea_id"] for row in report["units"]] == ["b", "a"]
    assert "# Buyer Committee Alignment" in markdown
    assert "| Unit | Domain | Score | Covered Roles | Missing Roles | Next Action |" in markdown
    assert "## Recommendations" in markdown
    assert markdown.endswith("\n")
    assert rendered_json == render_buyer_committee_alignment_json(report)
    parsed = json.loads(rendered_json)
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert list(parsed["source"]) == ["domain_filter", "entity_type", "project"]
