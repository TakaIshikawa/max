"""Tests for product changelog export — Keep a Changelog format."""

from __future__ import annotations

import json

from max.exports.changelog_export import (
    KIND,
    SCHEMA_VERSION,
    build_changelog,
    render_changelog_json,
    render_changelog_markdown,
)


# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_VERSIONS = [
    {
        "version": "1.2.0",
        "date": "2026-05-01",
        "entries": [
            {"category": "Added", "description": "New dashboard analytics page"},
            {"category": "Added", "description": "Export to PDF support"},
            {"category": "Changed", "description": "Upgraded authentication flow"},
            {"category": "Fixed", "description": "Memory leak in WebSocket handler"},
        ],
    },
    {
        "version": "1.1.0",
        "date": "2026-04-15",
        "entries": [
            {"category": "Added", "description": "User profile avatars"},
            {"category": "Removed", "description": "Legacy API v1 endpoints"},
            {"category": "Fixed", "description": "Pagination offset bug"},
        ],
    },
]

SAMPLE_UNRELEASED = [
    {"category": "Added", "description": "Dark mode toggle"},
    {"category": "Changed", "description": "Improved search performance"},
]


# ── build_changelog tests ────────────────────────────────────────────


def test_build_changelog_schema() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "generated_at" in doc


def test_build_changelog_project_name() -> None:
    doc = build_changelog(SAMPLE_VERSIONS, project_name="MyApp")
    assert doc["project_name"] == "MyApp"


def test_build_changelog_versions_preserved() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    assert len(doc["versions"]) == 2
    assert doc["versions"][0]["version"] == "1.2.0"
    assert doc["versions"][1]["version"] == "1.1.0"


def test_build_changelog_unreleased() -> None:
    doc = build_changelog(SAMPLE_VERSIONS, unreleased=SAMPLE_UNRELEASED)
    assert len(doc["unreleased"]) == 2
    assert doc["unreleased"][0]["category"] == "Added"


def test_build_changelog_entries_categorized() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    entries = doc["versions"][0]["entries"]
    categories = {e["category"] for e in entries}
    assert "Added" in categories
    assert "Changed" in categories
    assert "Fixed" in categories


def test_build_changelog_invalid_category_defaults() -> None:
    versions = [{"version": "1.0.0", "entries": [{"category": "Invalid", "description": "test"}]}]
    doc = build_changelog(versions)
    assert doc["versions"][0]["entries"][0]["category"] == "Changed"


def test_build_changelog_empty() -> None:
    doc = build_changelog([])
    assert doc["versions"] == []
    assert doc["unreleased"] == []


# ── Markdown rendering ───────────────────────────────────────────────


def test_render_changelog_markdown_title() -> None:
    doc = build_changelog(SAMPLE_VERSIONS, project_name="TestApp")
    md = render_changelog_markdown(doc)
    assert "# Changelog — TestApp" in md


def test_render_changelog_markdown_keep_a_changelog_reference() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    md = render_changelog_markdown(doc)
    assert "Keep a Changelog" in md


def test_render_changelog_markdown_version_headers() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    md = render_changelog_markdown(doc)
    assert "## [1.2.0] - 2026-05-01" in md
    assert "## [1.1.0] - 2026-04-15" in md


def test_render_changelog_markdown_unreleased_section() -> None:
    doc = build_changelog(SAMPLE_VERSIONS, unreleased=SAMPLE_UNRELEASED)
    md = render_changelog_markdown(doc)
    assert "## [Unreleased]" in md
    assert "Dark mode toggle" in md


def test_render_changelog_markdown_categories() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    md = render_changelog_markdown(doc)
    assert "### Added" in md
    assert "### Changed" in md
    assert "### Fixed" in md
    assert "### Removed" in md


def test_render_changelog_markdown_entries_as_bullets() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    md = render_changelog_markdown(doc)
    assert "- New dashboard analytics page" in md
    assert "- Memory leak in WebSocket handler" in md


def test_render_changelog_markdown_no_unreleased_when_empty() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    md = render_changelog_markdown(doc)
    assert "[Unreleased]" not in md


# ── JSON rendering ───────────────────────────────────────────────────


def test_render_changelog_json_valid() -> None:
    doc = build_changelog(SAMPLE_VERSIONS)
    output = render_changelog_json(doc)
    parsed = json.loads(output)
    assert parsed["schema_version"] == SCHEMA_VERSION


def test_render_changelog_json_roundtrip() -> None:
    doc = build_changelog(SAMPLE_VERSIONS, project_name="App")
    output = render_changelog_json(doc)
    parsed = json.loads(output)
    assert parsed["project_name"] == "App"
    assert len(parsed["versions"]) == 2
