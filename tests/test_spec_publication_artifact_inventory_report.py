from __future__ import annotations

import json

from max.exports.spec_publication_artifact_inventory_report import (
    KIND,
    build_spec_publication_artifact_inventory_report,
    render_spec_publication_artifact_inventory_report_json,
    render_spec_publication_artifact_inventory_report_markdown,
)


def test_spec_publication_artifact_inventory_groups_destinations_and_formats() -> None:
    report = build_spec_publication_artifact_inventory_report(
        [
            {"artifact_id": "art-3", "unit_id": "unit-2", "spec_id": "spec-2", "destination": "portal", "format": "html", "status": "queued", "path": "/portal/spec-2"},
            {"artifact_id": "art-1", "unit_id": "unit-1", "spec_id": "spec-1", "destination": "archive", "format": "json", "status": "published", "path": "/archive/spec-1.json", "published_at": "2026-05-20T10:00:00Z"},
            {"artifact_id": "art-2", "unit_id": "unit-1", "spec_id": "spec-1", "destination": "archive", "format": "markdown", "status": "failed", "path": "/archive/spec-1.md", "error": "permission denied"},
        ]
    )

    assert report == build_spec_publication_artifact_inventory_report(
        [
            {"artifact_id": "art-3", "unit_id": "unit-2", "spec_id": "spec-2", "destination": "portal", "format": "html", "status": "queued", "path": "/portal/spec-2"},
            {"artifact_id": "art-1", "unit_id": "unit-1", "spec_id": "spec-1", "destination": "archive", "format": "json", "status": "published", "path": "/archive/spec-1.json", "published_at": "2026-05-20T10:00:00Z"},
            {"artifact_id": "art-2", "unit_id": "unit-1", "spec_id": "spec-1", "destination": "archive", "format": "markdown", "status": "failed", "path": "/archive/spec-1.md", "error": "permission denied"},
        ]
    )
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert [row["artifact_id"] for row in report["artifacts"]] == ["art-1", "art-2", "art-3"]
    assert report["summary"] == {
        "artifact_count": 3,
        "destination_count": 2,
        "format_count": 3,
        "published_count": 1,
        "queued_count": 1,
        "failed_artifact_count": 1,
        "missing_traceability_count": 0,
    }
    assert report["destination_totals"][0] == {"destination": "archive", "artifact_count": 2, "published_count": 1, "queued_count": 0, "failed_count": 1}
    assert [row["format"] for row in report["format_totals"]] == ["html", "json", "markdown"]
    assert [row["artifact_id"] for row in report["failed_artifacts"]] == ["art-2"]


def test_spec_publication_artifact_inventory_flags_missing_traceability() -> None:
    report = build_spec_publication_artifact_inventory_report(
        [
            {"destination": "archive", "format": "json", "status": "written", "path": "/archive/missing.json"},
            {"artifact_id": "art-2", "unit_id": "unit-2", "destination": "portal", "format": "html", "status": "published"},
        ]
    )

    assert report["summary"]["published_count"] == 2
    assert report["summary"]["missing_traceability_count"] == 2
    assert report["missing_traceability"] == [
        {"artifact_id": "art-2", "destination": "portal", "path": "", "missing_fields": ["spec_id"]},
        {"artifact_id": "artifact-1", "destination": "archive", "path": "/archive/missing.json", "missing_fields": ["artifact_id", "unit_id", "spec_id"]},
    ]


def test_spec_publication_artifact_inventory_markdown_and_json_rendering() -> None:
    report = build_spec_publication_artifact_inventory_report(
        [{"artifact_id": "art-1", "unit_id": "unit-1", "spec_id": "spec-1", "destination": "portal", "format": "html", "status": "error", "error": "timeout"}]
    )

    markdown = render_spec_publication_artifact_inventory_report_markdown(report)
    assert "- Artifacts: 1" in markdown
    assert "- Failed artifacts: 1" in markdown
    assert "- art-1: portal error (timeout)" in markdown
    assert "- No missing traceability fields were found." in markdown

    rendered_json = render_spec_publication_artifact_inventory_report_json(report)
    assert rendered_json.endswith("\n")
    assert json.loads(rendered_json)["summary"]["failed_artifact_count"] == 1
