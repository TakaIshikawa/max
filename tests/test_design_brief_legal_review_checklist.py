from __future__ import annotations

import csv
import json
from io import StringIO

from max.analysis import generate_design_brief_legal_review_checklist as exported_generate
from max.analysis import render_design_brief_legal_review_checklist_markdown as exported_render
from max.analysis.design_brief_legal_review_checklist import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    generate_design_brief_legal_review_checklist,
    legal_review_checklist_filename,
    render_design_brief_legal_review_checklist,
    render_design_brief_legal_review_checklist_csv,
    render_design_brief_legal_review_checklist_markdown,
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
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text == render_design_brief_legal_review_checklist_csv(report)
    assert csv_text == render_design_brief_legal_review_checklist(report, fmt="csv")
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows[0] == {
        "checklist_category": "privacy",
        "item": "DBLR1",
        "owner_reviewer": "Privacy counsel",
        "jurisdiction_or_policy_area": "Privacy",
        "severity_priority": "high",
        "required_action": (
            "Classify personal, customer, telemetry, and workflow data used by "
            "CI gate before deployment with customer workflow data."
        ),
        "status": "pending",
        "due_date": "",
        "evidence_source_references": "idea:bu-legal; brief:risks; brief:evidence_counts; brief:validation_plan",
    }
    assert {row["checklist_category"] for row in rows} >= {
        "privacy",
        "claims_review",
        "oss_licensing",
        "approvals",
    }
    assert any(row["owner_reviewer"] == "Marketing counsel" for row in rows)
    assert any("customer-facing claims" in row["required_action"] for row in rows)
    assert all(row["status"] == "pending" for row in rows)


def test_render_design_brief_legal_review_checklist_csv_flattens_lists_and_due_dates() -> None:
    report = generate_design_brief_legal_review_checklist(_brief())
    report["sections"][0]["items"][0]["due_date"] = "2026-05-15"
    report["sections"][0]["items"][0]["evidence_reference_ids"] = [
        "idea:bu-legal",
        "brief:risks",
        "brief:validation_plan",
    ]

    rows = list(csv.DictReader(StringIO(render_design_brief_legal_review_checklist_csv(report))))

    assert rows[0]["due_date"] == "2026-05-15"
    assert rows[0]["evidence_source_references"] == "idea:bu-legal; brief:risks; brief:validation_plan"


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

    assert report["checklist_items"][0]["id"] == "DBLR1"
    assert markdown.startswith("# Legal Review Checklist: AgentAdversarialBench")
