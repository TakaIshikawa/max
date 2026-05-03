from __future__ import annotations

import csv
import json
from io import StringIO

from max.analysis import generate_design_brief_legal_review_checklist as exported_generate
from max.analysis import render_design_brief_legal_review_checklist_markdown as exported_render
from max.analysis import render_legal_review_checklist_csv as exported_csv_render
from max.analysis.design_brief_legal_review_checklist import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    generate_design_brief_legal_review_checklist,
    legal_review_checklist_filename,
    render_design_brief_legal_review_checklist,
    render_design_brief_legal_review_checklist_csv,
    render_design_brief_legal_review_checklist_markdown,
    render_legal_review_checklist_csv,
)


def _brief(**overrides) -> dict:
    brief = {
        "id": "dbf-legal",
        "title": "AgentAdversarialBench",
        "domain": "developer-tools",
        "theme": "agent-security-evaluation",
        "readiness_score": 86.0,
        "lead_idea_id": "bu-legal",
        "buyer": "engineering manager",
        "specific_user": "platform engineer",
        "workflow_context": "CI gate before deployment with customer workflow data",
        "why_this_now": "Agent tool use is growing in enterprise development teams.",
        "merged_product_concept": "Run adversarial workflow fixtures through a CLI and GitHub integration.",
        "synthesis_rationale": "Teams need repeatable agent safety checks with buyer-ready evidence.",
        "mvp_scope": ["CLI runner", "GitHub check output"],
        "first_milestones": ["Prototype CLI", "Mock GitHub status integration"],
        "validation_plan": "Run with three teams using synthetic workflow data.",
        "risks": ["Customer workflow data may include PII", "GitHub API terms and claims need review"],
        "source_idea_ids": ["bu-legal"],
        "evidence_counts": {"signals": 4, "insights": 2, "source_ideas": 1},
        "design_status": "approved",
        "created_at": "2026-04-22T00:00:00+00:00",
        "updated_at": "2026-04-22T00:00:00+00:00",
    }
    brief.update(overrides)
    return brief


def test_generate_design_brief_legal_review_checklist_is_stable_and_complete() -> None:
    first = generate_design_brief_legal_review_checklist(_brief())
    second = generate_design_brief_legal_review_checklist(_brief())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["brief_id"] == "dbf-legal"
    assert first["title"] == "AgentAdversarialBench"
    assert first["summary"]["review_gate"] == "ready_for_legal_review"
    assert [section["id"] for section in first["sections"]] == [
        "privacy",
        "data_rights",
        "claims_review",
        "contractual_procurement_risks",
        "security_review_handoff",
        "oss_licensing",
        "approvals",
        "unresolved_legal_questions",
    ]
    assert all(item["owner"] for item in first["checklist_items"])
    assert all(item["priority"] for item in first["checklist_items"])
    assert all(item["evidence_reference_ids"] for item in first["checklist_items"])
    assert all(item["completion_criteria"] for item in first["checklist_items"])
    assert "idea:bu-legal" in first["checklist_items"][0]["evidence_reference_ids"]
    assert first["unresolved_legal_questions"] == []


def test_generate_design_brief_legal_review_checklist_handles_sparse_briefs_conservatively() -> None:
    report = generate_design_brief_legal_review_checklist(
        {
            "id": "dbf-sparse",
            "title": "",
            "readiness_score": None,
            "mvp_scope": [],
            "risks": [],
            "source_idea_ids": [],
            "evidence_counts": {},
        }
    )

    assert report["title"] == "Untitled Design Brief"
    assert report["summary"]["review_gate"] == "needs_legal_discovery"
    assert report["evidence_references"] == [
        {
            "id": "brief:fallback",
            "type": "fallback",
            "summary": (
                "No source ideas, risks, validation plan, or evidence counts were persisted; "
                "checklist uses conservative fallback review items."
            ),
        }
    ]
    assert "brief:fallback" in report["checklist_items"][0]["evidence_reference_ids"]
    assert any(
        question["question"] == "Which user segment is in scope for privacy notices, terms, and claims review?"
        for question in report["unresolved_legal_questions"]
    )
    assert any("customer-facing claims" in item["task"] for item in report["checklist_items"])


def test_render_design_brief_legal_review_checklist_markdown_is_bundle_ready() -> None:
    report = generate_design_brief_legal_review_checklist(_brief())

    markdown = render_design_brief_legal_review_checklist_markdown(report)

    assert markdown.startswith("# Legal Review Checklist: AgentAdversarialBench")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Privacy" in markdown
    assert "## Data Rights" in markdown
    assert "## Claims Review" in markdown
    assert "## Contractual / Procurement Risks" in markdown
    assert "## Security Review Handoff" in markdown
    assert "## OSS / Licensing" in markdown
    assert "## Approvals" in markdown
    assert "## Unresolved Legal Questions" in markdown
    assert "- Owner: Privacy counsel" in markdown
    assert "- Priority: high" in markdown
    assert "- Evidence references: `idea:bu-legal`, `brief:risks`, `brief:evidence_counts`, `brief:validation_plan`" in markdown
    assert "- Completion criteria:" in markdown
    assert "## Evidence References" in markdown


def test_render_design_brief_legal_review_checklist_csv_is_parseable_and_ordered() -> None:
    report = generate_design_brief_legal_review_checklist(_brief())

    csv_text = render_design_brief_legal_review_checklist(report, fmt="csv")
    repeated = render_legal_review_checklist_csv(report)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == render_design_brief_legal_review_checklist_csv(report)
    assert csv_text == render_design_brief_legal_review_checklist(report, fmt="csv")
    assert csv_text == repeated
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert CSV_COLUMNS == (
        "review_area",
        "question",
        "risk_level",
        "required_evidence",
        "owner",
        "blocker_status",
        "notes",
    )
    assert rows[0] == {
        "review_area": "Privacy",
        "question": (
            "Classify personal, customer, telemetry, and workflow data used by "
            "CI gate before deployment with customer workflow data."
        ),
        "risk_level": "high",
        "required_evidence": (
            "Data categories, collection purpose, consent or notice assumptions, retention, "
            "deletion, and sharing boundaries are documented."
        ),
        "owner": "Privacy counsel",
        "blocker_status": "pending",
        "notes": "",
    }
    assert [row["risk_level"] for row in rows[:4]] == ["high", "high", "high", "high"]
    assert {row["review_area"] for row in rows} >= {
        "Privacy",
        "Claims Review",
        "OSS / Licensing",
        "Approvals",
    }
    assert any(row["owner"] == "Marketing counsel" for row in rows)
    assert any("customer-facing claims" in row["question"] for row in rows)
    assert all(row["blocker_status"] == "pending" for row in rows)
    assert all(row["notes"] == "" for row in rows)


def test_render_legal_review_checklist_csv_preserves_sparse_fields_and_escapes() -> None:
    report = {
        "checklist_items": [
            {
                "review_area": "Privacy, Terms",
                "question": "Can we use customer logs?\nWho approves?",
                "risk_level": "critical",
                "required_evidence": ["DPA", "retention policy"],
                "owner": "Legal, Privacy",
                "blocker_status": "blocked",
                "notes": "Needs counsel, security\nand product signoff.",
            },
            {
                "question": "Is a fallback review needed?",
                "risk_level": "low",
                "required_evidence": "",
                "owner": "",
                "blocker_status": "",
            },
        ]
    }

    csv_text = render_legal_review_checklist_csv(report)
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert '"Privacy, Terms"' in csv_text
    assert '"Can we use customer logs?\nWho approves?"' in csv_text
    assert rows[0] == {
        "review_area": "Privacy, Terms",
        "question": "Can we use customer logs?\nWho approves?",
        "risk_level": "critical",
        "required_evidence": "DPA; retention policy",
        "owner": "Legal, Privacy",
        "blocker_status": "blocked",
        "notes": "Needs counsel, security\nand product signoff.",
    }
    assert rows[1] == {
        "review_area": "",
        "question": "Is a fallback review needed?",
        "risk_level": "low",
        "required_evidence": "",
        "owner": "",
        "blocker_status": "",
        "notes": "",
    }


def test_render_design_brief_legal_review_checklist_keeps_markdown_and_json_formats() -> None:
    report = generate_design_brief_legal_review_checklist(_brief())

    markdown = render_design_brief_legal_review_checklist(report, fmt="markdown")
    rendered_json = render_design_brief_legal_review_checklist(report, fmt="json")

    assert markdown == render_design_brief_legal_review_checklist_markdown(report)
    assert json.loads(rendered_json) == report
    assert rendered_json == json.dumps(report, indent=2, sort_keys=True) + "\n"


def test_legal_review_checklist_filename_supports_csv() -> None:
    brief = _brief(title="Legal Review: Alpha / Beta")

    assert (
        legal_review_checklist_filename(brief, fmt="csv")
        == "dbf-legal-Legal-Review:-Alpha---Beta-legal-review-checklist.csv"
    )
    assert legal_review_checklist_filename(brief, fmt="json").endswith(".json")
    assert legal_review_checklist_filename(brief, fmt="markdown").endswith(".md")


def test_design_brief_legal_review_checklist_is_importable_from_analysis_package() -> None:
    report = exported_generate(_brief())
    markdown = exported_render(report)
    csv_text = exported_csv_render(report)

    assert report["checklist_items"][0]["id"] == "DBLR1"
    assert markdown.startswith("# Legal Review Checklist: AgentAdversarialBench")
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
