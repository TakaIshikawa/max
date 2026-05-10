"""Release notes generator for polished product release documentation.

Generates audience-appropriate summaries highlighting new features, improvements,
and breaking changes. Exports to markdown with optional sections for migration
guides and known issues.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.release_notes.v1"
KIND = "max.release_notes"


def build_release_notes(
    *,
    version: str,
    highlights: list[str] | None = None,
    features: list[dict[str, Any]] | None = None,
    improvements: list[dict[str, Any]] | None = None,
    breaking_changes: list[dict[str, Any]] | None = None,
    bug_fixes: list[dict[str, Any]] | None = None,
    migration_guide: list[dict[str, Any]] | None = None,
    known_issues: list[dict[str, Any]] | None = None,
    release_date: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Build release notes document.

    Args:
        version: Release version string
        highlights: Top-level summary bullet points
        features: New feature entries with title and description
        improvements: Improvement entries with title and description
        breaking_changes: Breaking change entries with title, description, and migration
        bug_fixes: Bug fix entries with title and description
        migration_guide: Migration steps with title and instructions
        known_issues: Known issue entries with title and workaround
        release_date: Optional release date string
        summary: Optional one-line release summary

    Returns:
        Structured release notes document dict.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "release_date": release_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": summary or "",
        "highlights": highlights or [],
        "features": [_validate_entry(f) for f in (features or [])],
        "improvements": [_validate_entry(i) for i in (improvements or [])],
        "breaking_changes": [_validate_breaking_change(b) for b in (breaking_changes or [])],
        "bug_fixes": [_validate_entry(b) for b in (bug_fixes or [])],
        "migration_guide": [_validate_migration_step(m) for m in (migration_guide or [])],
        "known_issues": [_validate_known_issue(k) for k in (known_issues or [])],
    }


def render_release_notes_markdown(document: dict[str, Any]) -> str:
    """Render release notes as Markdown.

    Args:
        document: Release notes document from build_release_notes

    Returns:
        Markdown formatted release notes.
    """
    lines = [
        f"# Release Notes — v{document['version']}",
        "",
        f"**Release date**: {document['release_date']}",
        "",
    ]

    if document.get("summary"):
        lines.extend([document["summary"], ""])

    # Highlights
    if document["highlights"]:
        lines.extend(["## Highlights", ""])
        for h in document["highlights"]:
            lines.append(f"- {h}")
        lines.append("")

    # New Features
    if document["features"]:
        lines.extend(["## New Features", ""])
        for f in document["features"]:
            lines.append(f"### {f['title']}")
            lines.append("")
            if f.get("description"):
                lines.append(f"{f['description']}")
                lines.append("")

    # Improvements
    if document["improvements"]:
        lines.extend(["## Improvements", ""])
        for imp in document["improvements"]:
            lines.append(f"- **{imp['title']}**: {imp.get('description', '')}")
        lines.append("")

    # Breaking Changes
    if document["breaking_changes"]:
        lines.extend(["## Breaking Changes", ""])
        for bc in document["breaking_changes"]:
            lines.append(f"### ⚠️ {bc['title']}")
            lines.append("")
            if bc.get("description"):
                lines.append(f"{bc['description']}")
                lines.append("")
            if bc.get("migration"):
                lines.append(f"**Migration**: {bc['migration']}")
                lines.append("")

    # Bug Fixes
    if document["bug_fixes"]:
        lines.extend(["## Bug Fixes", ""])
        for bf in document["bug_fixes"]:
            lines.append(f"- **{bf['title']}**: {bf.get('description', '')}")
        lines.append("")

    # Migration Guide
    if document["migration_guide"]:
        lines.extend(["## Migration Guide", ""])
        for i, step in enumerate(document["migration_guide"], 1):
            lines.append(f"### Step {i}: {step['title']}")
            lines.append("")
            if step.get("instructions"):
                lines.append(step["instructions"])
                lines.append("")

    # Known Issues
    if document["known_issues"]:
        lines.extend(["## Known Issues", ""])
        for issue in document["known_issues"]:
            lines.append(f"- **{issue['title']}**")
            if issue.get("workaround"):
                lines.append(f"  - Workaround: {issue['workaround']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_release_notes_json(document: dict[str, Any]) -> str:
    """Render release notes as formatted JSON."""
    return json.dumps(document, indent=2, default=str)


def _validate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Validate a basic entry with title and description."""
    return {
        "title": entry.get("title", ""),
        "description": entry.get("description", ""),
    }


def _validate_breaking_change(entry: dict[str, Any]) -> dict[str, Any]:
    """Validate a breaking change entry."""
    return {
        "title": entry.get("title", ""),
        "description": entry.get("description", ""),
        "migration": entry.get("migration", ""),
    }


def _validate_migration_step(entry: dict[str, Any]) -> dict[str, Any]:
    """Validate a migration guide step."""
    return {
        "title": entry.get("title", ""),
        "instructions": entry.get("instructions", ""),
    }


def _validate_known_issue(entry: dict[str, Any]) -> dict[str, Any]:
    """Validate a known issue entry."""
    return {
        "title": entry.get("title", ""),
        "workaround": entry.get("workaround", ""),
    }
