"""Product changelog export in Keep a Changelog format.

Generates user-facing changelogs from release data, grouping changes by version
with categorized entries (Added, Changed, Fixed, Removed). Exports to markdown
and structured JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.changelog_export.v1"
KIND = "max.changelog_export"

VALID_CATEGORIES = {"Added", "Changed", "Fixed", "Removed", "Deprecated", "Security"}


def build_changelog(
    versions: list[dict[str, Any]],
    *,
    project_name: str = "Project",
    unreleased: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a changelog document from version entries.

    Args:
        versions: List of version dicts, each containing:
            - version: str (semver)
            - date: str (ISO date or YYYY-MM-DD)
            - entries: list of entry dicts with "category" and "description"
        project_name: Name of the project
        unreleased: Optional list of entry dicts for unreleased changes

    Returns:
        Structured changelog document dict.
    """
    validated_versions = [_validate_version(v) for v in versions]
    validated_unreleased = [_validate_entry(e) for e in (unreleased or [])]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "unreleased": validated_unreleased,
        "versions": validated_versions,
    }


def render_changelog_markdown(document: dict[str, Any]) -> str:
    """Render changelog as Keep a Changelog formatted Markdown.

    Args:
        document: Changelog document from build_changelog

    Returns:
        Markdown formatted changelog.
    """
    lines = [
        f"# Changelog — {document['project_name']}",
        "",
        "All notable changes to this project will be documented in this file.",
        "",
        "The format is based on [Keep a Changelog](https://keepachangelog.com/).",
        "",
    ]

    # Unreleased section
    unreleased = document.get("unreleased", [])
    if unreleased:
        lines.extend(["## [Unreleased]", ""])
        lines.extend(_render_entries_by_category(unreleased))

    # Version sections
    for version in document["versions"]:
        version_str = version["version"]
        date_str = version.get("date", "")
        header = f"## [{version_str}]"
        if date_str:
            header += f" - {date_str}"
        lines.extend([header, ""])
        lines.extend(_render_entries_by_category(version["entries"]))

    return "\n".join(lines).rstrip() + "\n"


def render_changelog_json(document: dict[str, Any]) -> str:
    """Render changelog as formatted JSON.

    Args:
        document: Changelog document from build_changelog

    Returns:
        JSON formatted string.
    """
    return json.dumps(document, indent=2, default=str)


def _render_entries_by_category(entries: list[dict[str, Any]]) -> list[str]:
    """Group entries by category and render as markdown sections."""
    lines: list[str] = []
    by_category: dict[str, list[str]] = {}

    for entry in entries:
        cat = entry.get("category", "Changed")
        by_category.setdefault(cat, []).append(entry["description"])

    # Render in canonical order
    for cat in ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]:
        if cat in by_category:
            lines.append(f"### {cat}")
            lines.append("")
            for desc in by_category[cat]:
                lines.append(f"- {desc}")
            lines.append("")

    return lines


def _validate_version(version: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a version entry."""
    return {
        "version": version.get("version", "0.0.0"),
        "date": version.get("date", ""),
        "entries": [_validate_entry(e) for e in version.get("entries", [])],
    }


def _validate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a changelog entry."""
    category = entry.get("category", "Changed")
    if category not in VALID_CATEGORIES:
        category = "Changed"
    return {
        "category": category,
        "description": entry.get("description", ""),
    }
