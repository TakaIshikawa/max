from __future__ import annotations

import csv
from io import StringIO

from max.spec.slo_exception_review import (
    SLO_EXCEPTION_REVIEW_CSV_COLUMNS,
    SLO_EXCEPTION_REVIEW_SCHEMA_VERSION,
    generate_slo_exception_review,
    render_slo_exception_review_csv,
    render_slo_exception_review_markdown,
)


def test_slo_exception_review_shape_and_strict_expiry() -> None:
    review = generate_slo_exception_review(_tact_spec())
    rows = list(csv.DictReader(StringIO(render_slo_exception_review_csv(review))))
    markdown = render_slo_exception_review_markdown(review)

    assert review["schema_version"] == SLO_EXCEPTION_REVIEW_SCHEMA_VERSION
    assert review["kind"] == "max.slo_exception_review"
    assert {"exception_classes", "request_evidence", "approval_criteria", "temporary_mitigations", "expiry_checks", "follow_up_actions", "evidence_references"} <= set(review)
    assert review["summary"]["strictness"] == "strict"
    assert review["exception_classes"][0]["timing"] == "7 days"
    assert review["expiry_checks"][0]["timing"] == "daily"
    assert "## Approval Criteria" in markdown
    assert "Strictness" in markdown
    assert render_slo_exception_review_csv(review).splitlines()[0] == ",".join(SLO_EXCEPTION_REVIEW_CSV_COLUMNS)
    assert rows[0]["section"] == "exception_classes"


def _tact_spec() -> dict:
    return {"source": {"idea_id": "bu-slo-exception"}, "project": {"title": "Realtime Case Router", "buyer": "support VP", "specific_user": "support lead", "workflow_context": "case routing"}, "solution": {"suggested_stack": {"queue": "Redis"}}, "execution": {"risks": ["critical outage risk during launch"]}}
