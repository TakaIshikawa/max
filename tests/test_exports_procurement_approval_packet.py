from __future__ import annotations

import json

from max.exports.procurement_approval_packet import (
    build_procurement_approval_packet,
    render_procurement_approval_packet_json,
    render_procurement_approval_packet_markdown,
)


def test_procurement_approval_packet_prioritizes_blockers_missing_docs_and_overdue_actions() -> None:
    packet = build_procurement_approval_packet(
        [
            {
                "request": "Analytics renewal",
                "vendor": "Metricly",
                "department": "Marketing",
                "status": "ready",
                "required_artifacts": ["DPA", "security review"],
                "owner": "procurement",
                "deadline": "2026-06-15",
            },
            {
                "request": "Warehouse expansion",
                "vendor": "Acme Cloud",
                "department": "Data",
                "required_artifacts": ["security review", "DPA", "budget approval"],
                "missing_artifacts": ["DPA"],
                "blockers": ["legal approval blocked"],
                "owner": "legal",
                "deadline": "2026-05-25",
            },
            {
                "request": "Support tooling",
                "vendor": "DeskStack",
                "department": "Support",
                "missing_artifacts": ["budget approval"],
                "owner": "support-ops",
                "deadline": "2026-05-01",
            },
        ],
        as_of="2026-05-20",
    )

    assert [item["request"] for item in packet["items"]] == ["Warehouse expansion", "Support tooling", "Analytics renewal"]
    assert packet["summary"]["blocked_count"] == 1
    assert packet["summary"]["pending_count"] == 1
    assert packet["summary"]["ready_count"] == 1
    assert packet["summary"]["overdue_count"] == 1
    assert packet["summary"]["missing_document_count"] == 2
    markdown = render_procurement_approval_packet_markdown(packet)
    assert markdown.index("#### Warehouse expansion") < markdown.index("#### Analytics renewal")
    assert "- Required artifacts: budget approval, DPA, security review" in markdown
    assert "- Missing artifacts: DPA" in markdown
    assert "- Blockers: legal approval blocked" in markdown
    assert "- Owner: legal" in markdown
    assert "- Deadline: 2026-05-25" in markdown


def test_procurement_approval_packet_groups_and_normalizes_missing_values() -> None:
    packet = build_procurement_approval_packet(
        [
            {"request": "CRM", "department": "Sales", "status": "approved"},
            {"request": "BI", "department": "Sales", "missing_artifacts": "security review"},
        ],
        group_by="department",
    )

    assert packet["groups"][0]["name"] == "Sales"
    assert packet["groups"][0]["item_count"] == 2
    markdown = render_procurement_approval_packet_markdown(packet)
    assert "Unspecified vendor" in markdown
    assert "Unassigned" in markdown
    assert json.loads(render_procurement_approval_packet_json(packet))["summary"]["item_count"] == 2


def test_procurement_approval_packet_renders_empty_state() -> None:
    packet = build_procurement_approval_packet([])

    assert packet["summary"]["item_count"] == 0
    assert "No procurement approval items were supplied." in render_procurement_approval_packet_markdown(packet)
