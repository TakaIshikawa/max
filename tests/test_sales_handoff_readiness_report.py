from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.sales_handoff_readiness_report import (
    KIND,
    SCHEMA_VERSION,
    build_sales_handoff_readiness_report_export,
    render_sales_handoff_readiness_report_json,
    render_sales_handoff_readiness_report_markdown,
)


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = unit_id
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_sales_handoff_readiness_scoring_and_sorting() -> None:
    report = build_sales_handoff_readiness_report_export(
        _store(
            [
                _unit(
                    "ready",
                    {
                        "account": "Zenith",
                        "owner": "Mina",
                        "opportunity_stage": "closed_won",
                        "handoff_notes": "Expansion handoff complete",
                        "success_criteria": ["30-day activation"],
                        "technical_requirements": ["SSO"],
                        "buyer_roles": ["Economic buyer"],
                    },
                ),
                _unit("incomplete", {"account": "Acme", "handoff_notes": "Needs kickoff", "open_questions": ["Data owner?"]}),
                _unit(
                    "blocked",
                    {
                        "account": "Beta",
                        "handoff_notes": "Large deployment",
                        "success_criteria": ["Migration"],
                        "technical_requirements": ["DPA"],
                        "buyer_roles": ["Legal"],
                        "risk_flags": ["security review blocked"],
                    },
                ),
            ]
        )
    )

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert [row["idea_id"] for row in report["readiness_rows"]] == ["blocked", "incomplete", "ready"]
    statuses = {row["idea_id"]: row["readiness_status"] for row in report["readiness_rows"]}
    assert statuses == {"blocked": "blocked", "incomplete": "incomplete", "ready": "ready"}
    assert report["summary"]["status_counts"] == {"blocked": 1, "incomplete": 1, "ready": 1}
    assert report["summary"]["ready_percent"] == 33.3


def test_domain_forwarding_and_renderers() -> None:
    store = _store([_unit("ready", {"account": "Acme", "handoff_notes": "Done", "success_criteria": ["Adoption"], "technical_requirements": ["API"], "buyer_roles": ["VP"]})])

    report = build_sales_handoff_readiness_report_export(store, domain="fintech")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="fintech")
    assert report["source"]["domain_filter"] == "fintech"
    assert json.loads(render_sales_handoff_readiness_report_json(report)) == report
    markdown = render_sales_handoff_readiness_report_markdown(report)
    assert markdown.startswith("# Sales Handoff Readiness Report")
    assert "| Account | Owner | Stage | Status | Missing Items | Risks | Recommendation |" in markdown


def test_empty_store_behavior() -> None:
    report = build_sales_handoff_readiness_report_export(_store([]))

    assert report["summary"]["account_count"] == 0
    assert report["readiness_rows"] == []
    assert "No sales handoff candidates found" in render_sales_handoff_readiness_report_markdown(report)
