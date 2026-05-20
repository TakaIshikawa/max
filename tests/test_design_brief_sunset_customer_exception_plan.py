from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_sunset_customer_exception_plan import (
    KIND,
    build_design_brief_sunset_customer_exception_plan,
    render_design_brief_sunset_customer_exception_plan,
    sunset_customer_exception_plan_filename,
)


def test_sunset_customer_exception_plan_builds_complete_deterministic_rows() -> None:
    report = build_design_brief_sunset_customer_exception_plan(_brief())

    assert report == build_design_brief_sunset_customer_exception_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert [row["customer"] for row in report["exception_summary"]] == [
        "Acme Bank",
        "Strategic healthcare segment",
    ]
    assert report["exception_summary"][0] == {
        "id": "E1",
        "customer": "Acme Bank",
        "extension_window": "90 days after sunset",
        "commercial_impact": "$120k renewal at risk",
        "approval_owner": "VP Customer Success",
        "mitigation": "Weekly migration checkpoint",
    }
    assert report["support_commitments"]
    assert report["approval_owners"][0]["owner"] == "VP Customer Success"
    assert report["mitigation_steps"][0]["action"] == "Weekly migration checkpoint"
    assert report["recommendation"]["status"] == "ready_for_exception_review"
    assert report["missing_evidence"] == []


def test_sunset_customer_exception_plan_sparse_brief_flags_missing_evidence() -> None:
    report = build_design_brief_sunset_customer_exception_plan({"id": "dbf-sunset-sparse"})

    assert report["summary"]["recommendation_status"] == "blocked_pending_exception_evidence"
    assert [warning["id"] for warning in report["missing_evidence"]] == [
        "missing_customer_evidence",
        "missing_commitment_window",
        "missing_approval_owner",
        "missing_support_commitment",
        "missing_mitigation_plan",
    ]
    assert json.loads(json.dumps(report)) == report


def test_sunset_customer_exception_plan_renderers_and_filename() -> None:
    report = build_design_brief_sunset_customer_exception_plan(_brief())

    assert json.loads(render_design_brief_sunset_customer_exception_plan(report, "json")) == report
    markdown = render_design_brief_sunset_customer_exception_plan(report, "markdown")
    assert markdown.startswith("# Sunset Customer Exception Plan: Sunset Exception Brief")
    assert "## Exception Summary" in markdown
    assert "ready_for_exception_review" in markdown
    assert (
        sunset_customer_exception_plan_filename(_brief())
        == "dbf-sunset-1-Sunset-Exception-Brief-sunset-customer-exception-plan.md"
    )
    assert sunset_customer_exception_plan_filename(_brief(), "json").endswith(".json")
    with pytest.raises(ValueError, match="Unsupported sunset customer exception plan format"):
        render_design_brief_sunset_customer_exception_plan(report, "xml")


def _brief() -> dict:
    return {
        "id": "dbf-sunset-1",
        "title": "Sunset Exception Brief",
        "source_idea_ids": ["idea-sunset-1"],
        "exception_customers": ["Acme Bank", "Strategic healthcare segment", "Acme Bank"],
        "extension_windows": ["90 days after sunset", "60 days after sunset"],
        "commercial_impact": ["$120k renewal at risk", "strategic reference risk"],
        "support_commitments": ["Dedicated migration office hours"],
        "approval_owners": ["VP Customer Success", "Product GM"],
        "mitigation_steps": ["Weekly migration checkpoint", "Temporary compatibility export"],
    }
