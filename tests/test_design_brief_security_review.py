from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_security_review import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_security_review,
    render_design_brief_security_review,
    render_design_brief_security_review_csv,
    security_review_filename,
)


class FakeStore:
    def __init__(self, briefs: dict[str, dict]):
        self._briefs = briefs

    def get_design_brief(self, brief_id: str) -> dict | None:
        return self._briefs.get(brief_id)


def test_security_review_csv_export_normal_artifact() -> None:
    report = build_design_brief_security_review(
        FakeStore(
            {
                "dbf-security": {
                    "id": "dbf-security",
                    "title": "Security Review Brief",
                    "updated_at": "2026-05-01T00:00:00Z",
                    "threat_model": "OAuth integration can expose customer workflow data.",
                    "security_controls": ["least privilege OAuth scopes", "audit logging"],
                    "compliance_requirements": ["SOC2", "DPA"],
                    "risk_assessment": ["OAuth token leakage risk"],
                }
            }
        ),
        "dbf-security",
    )

    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["summary"]["risk_level"] == "high"
    csv_text = render_design_brief_security_review_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert rows == [
        {
            "review_id": "dbf-security-security-review",
            "brief_id": "dbf-security",
            "brief_title": "Security Review Brief",
            "threat_model": "OAuth integration can expose customer workflow data.",
            "security_controls": "least privilege OAuth scopes; audit logging",
            "compliance_requirements": "SOC2; DPA",
            "risk_assessment": "OAuth token leakage risk",
        }
    ]


def test_security_review_renderers_empty_data_and_filename() -> None:
    report = build_design_brief_security_review(FakeStore({"dbf-empty": {"id": "dbf-empty", "title": "Empty Security Review"}}), "dbf-empty")

    assert report is not None
    assert json.loads(render_design_brief_security_review(report, fmt="json")) == report
    assert "## Security Controls" in render_design_brief_security_review(report, fmt="markdown")
    rows = list(csv.DictReader(io.StringIO(render_design_brief_security_review(report, fmt="csv"))))
    assert rows[0]["threat_model"] == "Empty Security Review"
    assert rows[0]["compliance_requirements"] == ""
    assert security_review_filename({"id": "dbf-empty"}, fmt="csv") == "dbf-empty-security-review.csv"


def test_security_review_malformed_inputs_and_invalid_format() -> None:
    report = {
        "schema_version": SCHEMA_VERSION,
        "design_brief": {"id": "dbf-malformed", "title": "Malformed"},
        "review": {
            "id": "rev-malformed",
            "threat_model": {"entry": "API"},
            "security_controls": {"auth": "required"},
            "compliance_requirements": None,
            "risk_assessment": ["privacy | concern", ""],
        },
    }

    rows = list(csv.DictReader(io.StringIO(render_design_brief_security_review_csv(report))))
    assert rows[0]["security_controls"] == '{"auth":"required"}'
    assert rows[0]["risk_assessment"] == "privacy | concern"
    with pytest.raises(ValueError, match="Unsupported security review format: yaml"):
        render_design_brief_security_review(report, fmt="yaml")


def test_security_review_missing_brief_returns_none() -> None:
    assert build_design_brief_security_review(FakeStore({}), "dbf-missing") is None
