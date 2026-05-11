"""Tests for design brief retention policy reports."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_retention_policy import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_retention_policy,
    render_design_brief_retention_policy,
    retention_policy_filename,
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


def test_render_design_brief_retention_policy_csv_sections_and_rows() -> None:
    report = _policy()

    rendered = render_design_brief_retention_policy(report, fmt="csv")
    repeated = render_design_brief_retention_policy(report, fmt="csv")
    reader = csv.DictReader(io.StringIO(rendered))
    rows = list(reader)

    assert rendered == repeated
    assert rendered.endswith("\n")
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert rendered.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert [row["section"] for row in rows] == [
        "data_classes",
        "data_classes",
        "data_classes",
        "data_classes",
        "retention_rules",
        "retention_rules",
        "retention_rules",
        "retention_rules",
        "deletion_controls",
        "deletion_controls",
        "deletion_controls",
        "audit_requirements",
        "audit_requirements",
        "audit_requirements",
        "open_questions",
        "recommended_next_actions",
        "recommended_next_actions",
        "recommended_next_actions",
    ]

    data_class = rows[0]
    assert data_class["design_brief_id"] == "dbf-retention"
    assert data_class["design_brief_title"] == "Retention Test Brief"
    assert data_class["item_id"] == "design_brief_record"
    assert data_class["item_name"] == "Design brief record"
    assert data_class["sensitivity"] == "internal"
    assert data_class["source_fields"] == (
        "title; merged_product_concept; mvp_scope; risks; validation_plan"
    )

    rule = rows[4]
    assert rule["item_id"] == "RP1"
    assert rule["data_class_id"] == "design_brief_record"
    assert rule["retention_period"] == "24 months after the brief is archived"
    assert rule["deletion_trigger"] == "brief archived, superseded, or validation stopped"
    assert rule["owner"] == "product owner"
    assert rule["verification"] == ""
    assert rule["rationale"] == (
        "Keep enough context for handoff traceability while avoiding indefinite retention."
    )

    control = rows[8]
    assert control["item_id"] == "DC1"
    assert control["control"] == (
        "Delete archived brief artifacts from downstream handoff locations when retention expires."
    )
    assert control["verification"] == "record deletion timestamp and artifact locations"
    assert control["action"] == control["control"]

    audit = rows[11]
    assert audit["item_id"] == "AR1"
    assert audit["control"] == "Log who generated or downloaded the retention policy artifact."
    assert audit["verification"] == audit["control"]

    assert rows[14]["section"] == "open_questions"
    assert rows[14]["item_id"] == "OQ1"
    assert rows[14]["action"] == (
        "Which legal, security, or compliance owner can approve restricted data retention?"
    )
    assert rows[15]["section"] == "recommended_next_actions"
    assert rows[15]["item_id"] == "RNA1"
    assert rows[15]["action"] == (
        "Run a security or compliance review before collecting restricted operational data."
    )


def test_render_design_brief_retention_policy_csv_does_not_change_json_or_markdown() -> None:
    report = _policy()
    markdown = render_design_brief_retention_policy(report, fmt="markdown")
    json_text = render_design_brief_retention_policy(report, fmt="json")

    render_design_brief_retention_policy(report, fmt="csv")

    assert render_design_brief_retention_policy(report, fmt="markdown") == markdown
    assert render_design_brief_retention_policy(report, fmt="json") == json_text


def test_retention_policy_filename_supports_csv_extension() -> None:
    assert (
        retention_policy_filename({"id": "dbf-retention"}, fmt="csv")
        == "dbf-retention-retention-policy.csv"
    )
    assert (
        retention_policy_filename({"id": "dbf-retention"}, fmt="json")
        == "dbf-retention-retention-policy.json"
    )
    assert (
        retention_policy_filename({"id": "dbf-retention"}, fmt="markdown")
        == "dbf-retention-retention-policy.md"
    )


def test_render_design_brief_retention_policy_unsupported_format() -> None:
    with pytest.raises(ValueError, match="Unsupported retention policy format: html"):
        render_design_brief_retention_policy(_policy(), fmt="html")


@pytest.mark.parametrize(
    "field,value",
    [
        ("data_classification", None),
        ("legal_basis", None),
        ("review_schedule", None),
    ],
)
def test_retention_policy_handles_missing_optional_metadata_fields(field: str, value) -> None:
    brief_id = f"dbf-missing-{field}"
    store = FakeStore(
        {
            brief_id: {
                "id": brief_id,
                "title": "Missing Optional Retention Metadata",
                "domain": "customer-operations",
                "theme": "retention",
                "readiness_score": 70.0,
                "design_status": "candidate",
                "source_idea_ids": [],
                "created_at": "2026-04-25T10:00:00Z",
                "updated_at": "2026-04-26T11:00:00Z",
                field: value,
            }
        }
    )

    report = build_design_brief_retention_policy(store, brief_id)

    assert report is not None
    assert report["data_classes"]
    assert render_design_brief_retention_policy(report, fmt="markdown").endswith("\n")
    csv_text = render_design_brief_retention_policy(report, fmt="csv")
    assert csv_text.startswith(",".join(CSV_COLUMNS))
    assert list(csv.DictReader(io.StringIO(csv_text)))


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
