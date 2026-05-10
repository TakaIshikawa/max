"""Tests for release notes generator export."""

from __future__ import annotations

import json

from max.exports.release_notes import (
    KIND,
    SCHEMA_VERSION,
    build_release_notes,
    render_release_notes_json,
    render_release_notes_markdown,
)


# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_FEATURES = [
    {"title": "Real-time collaboration", "description": "Multiple users can edit simultaneously"},
    {"title": "AI-powered suggestions", "description": "Context-aware code completions"},
]

SAMPLE_IMPROVEMENTS = [
    {"title": "Faster startup", "description": "50% reduction in cold start time"},
    {"title": "Better error messages", "description": "Actionable error descriptions"},
]

SAMPLE_BREAKING_CHANGES = [
    {
        "title": "Config file format changed",
        "description": "YAML config replaced with TOML",
        "migration": "Run `migrate-config` to convert your config.yaml to config.toml",
    },
]

SAMPLE_BUG_FIXES = [
    {"title": "Fix crash on empty input", "description": "Handle null gracefully"},
]

SAMPLE_MIGRATION_GUIDE = [
    {"title": "Update config format", "instructions": "Run the migration script: `npx migrate`"},
    {"title": "Update import paths", "instructions": "Replace `@old/` with `@new/` in imports"},
]

SAMPLE_KNOWN_ISSUES = [
    {"title": "Slow on large files", "workaround": "Split files larger than 10MB"},
]


# ── build_release_notes tests ────────────────────────────────────────


def test_build_release_notes_schema() -> None:
    doc = build_release_notes(version="2.0.0")
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "generated_at" in doc


def test_build_release_notes_version() -> None:
    doc = build_release_notes(version="3.1.0")
    assert doc["version"] == "3.1.0"


def test_build_release_notes_all_sections() -> None:
    doc = build_release_notes(
        version="2.0.0",
        highlights=["Major rewrite"],
        features=SAMPLE_FEATURES,
        improvements=SAMPLE_IMPROVEMENTS,
        breaking_changes=SAMPLE_BREAKING_CHANGES,
        bug_fixes=SAMPLE_BUG_FIXES,
        migration_guide=SAMPLE_MIGRATION_GUIDE,
        known_issues=SAMPLE_KNOWN_ISSUES,
        summary="A complete overhaul of the platform.",
    )
    assert len(doc["features"]) == 2
    assert len(doc["improvements"]) == 2
    assert len(doc["breaking_changes"]) == 1
    assert len(doc["bug_fixes"]) == 1
    assert len(doc["migration_guide"]) == 2
    assert len(doc["known_issues"]) == 1
    assert doc["highlights"] == ["Major rewrite"]
    assert doc["summary"] == "A complete overhaul of the platform."


def test_build_release_notes_empty_sections() -> None:
    doc = build_release_notes(version="1.0.0")
    assert doc["features"] == []
    assert doc["improvements"] == []
    assert doc["breaking_changes"] == []
    assert doc["bug_fixes"] == []
    assert doc["migration_guide"] == []
    assert doc["known_issues"] == []


def test_build_release_notes_release_date() -> None:
    doc = build_release_notes(version="1.0.0", release_date="2026-05-10")
    assert doc["release_date"] == "2026-05-10"


# ── Markdown rendering ───────────────────────────────────────────────


def test_render_release_notes_markdown_title() -> None:
    doc = build_release_notes(version="2.0.0")
    md = render_release_notes_markdown(doc)
    assert "# Release Notes — v2.0.0" in md


def test_render_release_notes_markdown_highlights() -> None:
    doc = build_release_notes(version="2.0.0", highlights=["Big change", "New API"])
    md = render_release_notes_markdown(doc)
    assert "## Highlights" in md
    assert "- Big change" in md
    assert "- New API" in md


def test_render_release_notes_markdown_features() -> None:
    doc = build_release_notes(version="2.0.0", features=SAMPLE_FEATURES)
    md = render_release_notes_markdown(doc)
    assert "## New Features" in md
    assert "### Real-time collaboration" in md
    assert "Multiple users can edit simultaneously" in md


def test_render_release_notes_markdown_improvements() -> None:
    doc = build_release_notes(version="2.0.0", improvements=SAMPLE_IMPROVEMENTS)
    md = render_release_notes_markdown(doc)
    assert "## Improvements" in md
    assert "Faster startup" in md


def test_render_release_notes_markdown_breaking_changes() -> None:
    doc = build_release_notes(version="2.0.0", breaking_changes=SAMPLE_BREAKING_CHANGES)
    md = render_release_notes_markdown(doc)
    assert "## Breaking Changes" in md
    assert "Config file format changed" in md
    assert "Migration" in md


def test_render_release_notes_markdown_migration_guide() -> None:
    doc = build_release_notes(version="2.0.0", migration_guide=SAMPLE_MIGRATION_GUIDE)
    md = render_release_notes_markdown(doc)
    assert "## Migration Guide" in md
    assert "Update config format" in md
    assert "Update import paths" in md


def test_render_release_notes_markdown_known_issues() -> None:
    doc = build_release_notes(version="2.0.0", known_issues=SAMPLE_KNOWN_ISSUES)
    md = render_release_notes_markdown(doc)
    assert "## Known Issues" in md
    assert "Slow on large files" in md
    assert "Workaround:" in md


def test_render_release_notes_markdown_empty_sections_omitted() -> None:
    doc = build_release_notes(version="1.0.0")
    md = render_release_notes_markdown(doc)
    assert "## Highlights" not in md
    assert "## New Features" not in md
    assert "## Migration Guide" not in md


# ── JSON rendering ───────────────────────────────────────────────────


def test_render_release_notes_json_valid() -> None:
    doc = build_release_notes(version="2.0.0", features=SAMPLE_FEATURES)
    output = render_release_notes_json(doc)
    parsed = json.loads(output)
    assert parsed["version"] == "2.0.0"
    assert len(parsed["features"]) == 2
