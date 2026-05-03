"""Tests for design brief retention policy reports."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_retention_policy import (
    SCHEMA_VERSION,
    build_design_brief_retention_policy,
    render_design_brief_retention_policy,
)


class FakeStore:
    def __init__(self, briefs: dict[str, dict]):
        self._briefs = briefs

    def get_design_brief(self, brief_id: str) -> dict | None:
        return self._briefs.get(brief_id)


def test_render_design_brief_retention_policy_markdown_headings() -> None:
    report = _policy()

    markdown = render_design_brief_retention_policy(report, fmt="markdown")
    repeated = render_design_brief_retention_policy(report, fmt="markdown")

    assert markdown == repeated
    assert markdown.endswith("\n")
    assert markdown.startswith("# Retention Policy: Retention Test Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "Design brief: `dbf-retention`" in markdown
    assert "## Policy Summary" in markdown
    assert "## Data Categories" in markdown
    assert "## Retention Windows" in markdown
    assert "## Disposal Actions" in markdown
    assert "## Compliance Rationale" in markdown
    assert "## Owners And Review Cadence" in markdown
    assert "## Evidence And Source References" in markdown


def test_render_design_brief_retention_policy_markdown_retention_rows() -> None:
    report = _policy()

    markdown = render_design_brief_retention_policy(report, fmt="markdown")

    assert (
        "| Design brief record | internal | Persisted product concept, source relationships, "
        "readiness, risks, and handoff fields. | `title`, `merged_product_concept`, "
        "`mvp_scope`, `risks`, `validation_plan` |"
    ) in markdown
    assert (
        "| RP1 | design_brief_record | 24 months after the brief is archived | brief archived, "
        "superseded, or validation stopped | product owner | Keep enough context for handoff "
        "traceability while avoiding indefinite retention. |"
    ) in markdown
    assert (
        "| DC1 | Delete archived brief artifacts from downstream handoff locations when "
        "retention expires. | record deletion timestamp and artifact locations |"
    ) in markdown


def test_render_design_brief_retention_policy_markdown_owner_and_review_cadence() -> None:
    report = _policy()

    markdown = render_design_brief_retention_policy(report, fmt="markdown")

    assert (
        "- Review cadence: Monthly during validation, then quarterly after archival"
        in markdown
    )
    assert (
        "| RP4 sensitive_operational_data | security or compliance owner | Monthly during "
        "validation, then quarterly after archival |"
    ) in markdown
    assert "| Access control AC2 | security or compliance owner |" in markdown


def test_render_design_brief_retention_policy_markdown_evidence_and_missing_optional_data() -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "design_brief": {
            "id": "dbf-sparse",
            "title": "Sparse Retention Brief",
            "source_idea_ids": [],
        },
        "summary": {},
        "data_classes": [],
        "retention_rules": [],
        "deletion_controls": [],
        "evidence_references": [
            {
                "id": "sig-1",
                "type": "signal",
                "summary": "Customer asked about disposal proof.",
            }
        ],
    }

    markdown = render_design_brief_retention_policy(report, fmt="markdown")

    assert "Design brief: `dbf-sparse`" in markdown
    assert "| None | unknown | Not specified | none |" in markdown
    assert (
        "| None | Not specified | Not specified | Not specified | Unassigned | Not specified |"
        in markdown
    )
    assert "| None | Not specified | Not specified |" in markdown
    assert "**sig-1** (signal): Customer asked about disposal proof." in markdown
    assert "## Open Questions\n\n- None" in markdown
    assert "## Recommended Next Actions\n\n- None" in markdown


def test_render_design_brief_retention_policy_json_unchanged() -> None:
    report = _policy()

    rendered = render_design_brief_retention_policy(report, fmt="json")

    assert rendered == json.dumps(report, indent=2, sort_keys=True) + "\n"
    assert json.loads(rendered) == report


def test_render_design_brief_retention_policy_unsupported_format() -> None:
    with pytest.raises(ValueError, match="Unsupported retention policy format: html"):
        render_design_brief_retention_policy(_policy(), fmt="html")


def _policy() -> dict:
    brief_id = "dbf-retention"
    store = FakeStore(
        {
            brief_id: {
                "id": brief_id,
                "title": "Retention Test Brief",
                "domain": "customer-operations",
                "theme": "audit-handoff",
                "readiness_score": 88.0,
                "design_status": "approved",
                "lead_idea_id": "bu-retention",
                "source_idea_ids": ["bu-retention", "bu-support"],
                "created_at": "2026-04-25T10:00:00Z",
                "updated_at": "2026-04-26T11:00:00Z",
                "buyer": "operations director",
                "specific_user": "customer operations manager",
                "workflow_context": "customer onboarding audit handoff",
                "first_10_customers": "regulated customer success teams",
                "merged_product_concept": "Retention-aware design brief handoff.",
                "mvp_scope": ["Retention policy JSON", "Retention policy Markdown"],
                "validation_plan": "Confirm deletion owner and audit evidence before launch.",
                "risks": ["Customer data retention and audit ownership may be unclear."],
                "domain_risks": ["Privacy review required before telemetry collection."],
                "tech_approach": "Persist policy outputs with audit metadata.",
            }
        }
    )
    report = build_design_brief_retention_policy(store, brief_id)
    assert report is not None
    return report
