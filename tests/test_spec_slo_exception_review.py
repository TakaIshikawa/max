"""Tests for TactSpec SLO exception review generation."""

from __future__ import annotations

import csv
import io
import json

from max.spec import generate_slo_exception_review as exported_generate
from max.spec import render_slo_exception_review_csv as exported_render_csv
from max.spec import render_slo_exception_review_markdown as exported_render_markdown
from max.spec.generator import generate_spec_preview
from max.spec.slo_exception_review import (
    SLO_EXCEPTION_REVIEW_CSV_COLUMNS,
    SLO_EXCEPTION_REVIEW_SCHEMA_VERSION,
    generate_slo_exception_review,
    render_slo_exception_review_csv,
    render_slo_exception_review_markdown,
)


def test_generate_slo_exception_review_has_stable_shape(sample_unit, sample_evaluation) -> None:
    review = generate_slo_exception_review(generate_spec_preview(sample_unit, sample_evaluation))

    assert review == generate_slo_exception_review(generate_spec_preview(sample_unit, sample_evaluation))
    assert review["schema_version"] == SLO_EXCEPTION_REVIEW_SCHEMA_VERSION
    assert review["kind"] == "max.slo_exception_review"
    assert set(review) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "exception_classes",
        "request_evidence",
        "approval_criteria",
        "temporary_mitigations",
        "expiry_checks",
        "follow_up_actions",
        "evidence_references",
    }
    assert review["summary"]["strictness"] == "strict"
    assert review["summary"]["expiry_window"] == "24 hours"
    assert review["approval_criteria"][1]["severity"] == "required"
    assert review["expiry_checks"][0]["expiry"] == "24 hours"


def test_sparse_slo_exception_review_uses_standard_defaults() -> None:
    review = generate_slo_exception_review({"project": {"title": "Sparse Preview"}})

    assert review["summary"]["strictness"] == "standard"
    assert review["summary"]["expiry_window"] == "7 days"
    assert review["source"]["type"] == "tact_spec"
    assert review["summary"]["target_user"] == "primary user"
    assert review["evidence_references"] == []


def test_render_slo_exception_review_markdown_and_csv(sample_unit, sample_evaluation) -> None:
    review = generate_slo_exception_review(generate_spec_preview(sample_unit, sample_evaluation))
    markdown = render_slo_exception_review_markdown(review)
    csv_text = render_slo_exception_review_csv(review)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert markdown.startswith("# MCP Test Framework SLO Exception Review")
    assert "- Source ID: bu-test001" in markdown
    assert "- Strictness: strict" in markdown
    for heading in (
        "## Exception Classes",
        "## Request Evidence",
        "## Approval Criteria",
        "## Temporary Mitigations",
        "## Expiry Checks",
        "## Follow-up Actions",
        "## Evidence References",
    ):
        assert heading in markdown
    assert csv_text.splitlines()[0] == ",".join(SLO_EXCEPTION_REVIEW_CSV_COLUMNS)
    assert rows[0]["section"] == "exception_classes"
    assert any(row["section"] == "expiry_checks" and row["timing"] == "24 hours" for row in rows)


def test_slo_exception_review_is_exported_and_json_serializable(sample_unit, sample_evaluation) -> None:
    review = exported_generate(generate_spec_preview(sample_unit, sample_evaluation))

    assert json.loads(json.dumps(review))["kind"] == "max.slo_exception_review"
    assert exported_render_markdown(review).startswith("# MCP Test Framework SLO Exception Review")
    assert exported_render_csv(review).startswith(",".join(SLO_EXCEPTION_REVIEW_CSV_COLUMNS))
