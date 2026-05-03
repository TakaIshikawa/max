"""Unit tests for design brief sales battlecard rendering."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_sales_battlecard import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    render_design_brief_sales_battlecard,
)


def _battlecard() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.sales_battlecard",
        "design_brief": {
            "id": "dbf-sales-csv",
            "title": 'Sales, Battlecard "CSV"\nBrief',
            "readiness_score": 91.5,
            "design_status": "approved",
            "source_idea_ids": ["bu-lead", "bu-support"],
        },
        "summary": {
            "buyer": "revenue leader",
            "target_user": "account executive",
            "workflow_context": "pilot discovery call",
            "value_proposition": "Convert design briefs into sales motions.",
            "primary_pain": "Sales teams lack deterministic handoff artifacts.",
            "primary_outcome": "Pilot-ready sales conversations.",
            "primary_risk": "Security review can delay sales access.",
            "fallbacks_used": [],
        },
        "positioning": {
            "one_liner": "A deterministic battlecard for design briefs.",
            "why_now": "CRM enablement workflows need stable exports.",
            "qualification_signal": "pilot discovery call",
            "disqualification_signal": "manual sales notes",
        },
        "objection_handling": [
            {
                "id": "status_quo",
                "objection": "We can keep using notes, spreadsheets, and chat.",
                "response": 'Show the "handoff" drift across the current process.',
                "proof_point": "Exports preserve source evidence.",
                "discovery_follow_up": "What breaks when volume doubles?",
                "source_idea_ids": ["bu-lead"],
            },
            {
                "id": "priority",
                "objection": "This is not a priority right now.",
                "response": "Tie the decision to launch readiness.",
                "proof_point": "Sales can reuse the same artifact in CRM.",
                "discovery_follow_up": "Which initiative owns enablement?",
                "source_idea_ids": ["bu-support"],
            },
        ],
        "demo_beats": [
            {
                "id": "DB1",
                "name": "Frame the current workflow",
                "setup": "Start with the rep preparing a pilot call.",
                "show": "Compare the CSV against manual notes.",
                "outcome": "The buyer sees faster enablement.",
                "ask": "Does this match your handoff?",
                "source_idea_ids": ["bu-lead", "bu-support"],
            }
        ],
        "proof_points": [
            {
                "claim": "Business value",
                "evidence": "CRM rows include objection, demo beat, and proof point data.",
                "source_idea_ids": ["bu-lead"],
            }
        ],
        "source_ideas": [
            {
                "id": "bu-lead",
                "title": "Lead sales enablement idea",
                "role": "lead",
                "rank": 0,
                "buyer": "revenue leader",
                "specific_user": "account executive",
                "workflow_context": "pilot discovery call",
                "value_proposition": "Make sales handoffs deterministic.",
            },
            {
                "id": "bu-support",
                "title": "Supporting CRM export idea",
                "role": "supporting",
                "rank": 1,
                "buyer": "sales ops",
                "specific_user": "enablement manager",
                "workflow_context": "CRM update",
                "value_proposition": "Keep enablement spreadsheets portable.",
            },
        ],
    }


def test_render_design_brief_sales_battlecard_csv_rows_are_stable_and_filterable() -> None:
    csv_text = render_design_brief_sales_battlecard(_battlecard(), fmt="csv")
    repeated = render_design_brief_sales_battlecard(_battlecard(), fmt="csv")
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [(row["section"], row["type"], row["item_order"]) for row in rows] == [
        ("sales_context", "context", "1"),
        ("positioning", "positioning", "1"),
        ("objection_handling", "objection", "1"),
        ("objection_handling", "objection", "2"),
        ("demo_beats", "demo_beat", "1"),
        ("proof_points", "proof_point", "1"),
        ("source_ideas", "source_idea", "1"),
        ("source_ideas", "source_idea", "2"),
    ]
    assert rows[0]["design_brief_id"] == "dbf-sales-csv"
    assert rows[0]["design_brief_title"] == 'Sales, Battlecard "CSV"\nBrief'
    assert rows[0]["readiness_score"] == "91.5"
    assert rows[0]["buyer"] == "revenue leader"
    assert rows[0]["target_user"] == "account executive"
    assert rows[0]["workflow_context"] == "pilot discovery call"
    assert rows[0]["value_proposition"] == "Convert design briefs into sales motions."
    assert rows[0]["primary_pain"] == "Sales teams lack deterministic handoff artifacts."
    assert rows[0]["primary_outcome"] == "Pilot-ready sales conversations."
    assert rows[0]["primary_risk"] == "Security review can delay sales access."
    assert rows[1]["one_liner"] == "A deterministic battlecard for design briefs."
    assert rows[1]["why_now"] == "CRM enablement workflows need stable exports."
    assert rows[1]["qualification_signal"] == "pilot discovery call"
    assert rows[1]["disqualification_signal"] == "manual sales notes"
    assert rows[2]["item_name"] == "We can keep using notes, spreadsheets, and chat."
    assert rows[2]["objection"] == "We can keep using notes, spreadsheets, and chat."
    assert rows[2]["response"] == 'Show the "handoff" drift across the current process.'
    assert rows[2]["proof_point"] == "Exports preserve source evidence."
    assert rows[2]["discovery_follow_up"] == "What breaks when volume doubles?"
    assert rows[4]["item_name"] == "Frame the current workflow"
    assert rows[4]["setup"] == "Start with the rep preparing a pilot call."
    assert rows[4]["show"] == "Compare the CSV against manual notes."
    assert rows[4]["outcome"] == "The buyer sees faster enablement."
    assert rows[4]["ask"] == "Does this match your handoff?"
    assert rows[5]["item_id"] == "PP1"
    assert rows[5]["item_name"] == "Business value"
    assert rows[5]["claim"] == "Business value"
    assert rows[5]["source_idea_ids"] == "bu-lead"
    assert rows[6]["item_id"] == "bu-lead"
    assert rows[6]["item_name"] == "Lead sales enablement idea"
    assert rows[6]["source_idea_ids"] == "bu-lead"


def test_render_design_brief_sales_battlecard_csv_escapes_commas_quotes_and_newlines() -> None:
    csv_text = render_design_brief_sales_battlecard(_battlecard(), fmt="csv")

    assert '"Sales, Battlecard ""CSV""\nBrief"' in csv_text
    assert '"We can keep using notes, spreadsheets, and chat."' in csv_text
    assert '"Show the ""handoff"" drift across the current process."' in csv_text
    assert list(csv.DictReader(io.StringIO(csv_text)))[0]["design_brief_title"] == (
        'Sales, Battlecard "CSV"\nBrief'
    )


def test_render_design_brief_sales_battlecard_json_and_markdown_remain_supported() -> None:
    battlecard = _battlecard()

    assert json.loads(render_design_brief_sales_battlecard(battlecard, fmt="json")) == battlecard
    markdown = render_design_brief_sales_battlecard(battlecard, fmt="markdown")
    assert markdown.startswith('# Sales Battlecard: Sales, Battlecard "CSV"\nBrief\n')
    assert "## Objection Handling" in markdown
    assert "## Demo Beats" in markdown
    assert "## Proof Points" in markdown


def test_render_design_brief_sales_battlecard_unsupported_format_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported sales battlecard format: xml"):
        render_design_brief_sales_battlecard(_battlecard(), fmt="xml")
