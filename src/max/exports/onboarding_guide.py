"""Developer onboarding guide export.

Generates new developer onboarding documentation compiling setup instructions,
architecture overview, key conventions, and first-task suggestions. Exports
structured markdown with checklists and learning path milestones.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.onboarding_guide.v1"
KIND = "max.onboarding_guide"


def build_onboarding_guide(
    *,
    project_name: str = "Project",
    setup_steps: list[dict[str, Any]] | None = None,
    architecture: dict[str, Any] | None = None,
    conventions: list[dict[str, Any]] | None = None,
    first_tasks: list[dict[str, Any]] | None = None,
    learning_path: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an onboarding guide document.

    Args:
        project_name: Name of the project
        setup_steps: Environment setup checklist items with title and instructions
        architecture: Architecture overview with components and description
        conventions: Key conventions with title and description
        first_tasks: Suggested first contributions with title and description
        learning_path: Learning milestones with title, resources, and order
        resources: Additional resources with title and url

    Returns:
        Structured onboarding guide document dict.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "setup_steps": [_validate_setup_step(s) for s in (setup_steps or [])],
        "architecture": _validate_architecture(architecture or {}),
        "conventions": [_validate_convention(c) for c in (conventions or [])],
        "first_tasks": [_validate_task(t) for t in (first_tasks or [])],
        "learning_path": [_validate_milestone(m) for m in (learning_path or [])],
        "resources": [_validate_resource(r) for r in (resources or [])],
    }


def render_onboarding_markdown(document: dict[str, Any]) -> str:
    """Render onboarding guide as Markdown with checklists.

    Args:
        document: Onboarding guide from build_onboarding_guide

    Returns:
        Markdown formatted onboarding guide.
    """
    lines = [
        f"# Developer Onboarding — {document['project_name']}",
        "",
        f"Generated: {document['generated_at']}",
        "",
    ]

    # Setup checklist
    setup_steps = document.get("setup_steps", [])
    if setup_steps:
        lines.extend(["## Environment Setup", ""])
        for step in setup_steps:
            lines.append(f"- [ ] **{step['title']}**")
            if step.get("instructions"):
                lines.append(f"  - {step['instructions']}")
            if step.get("verification"):
                lines.append(f"  - Verify: `{step['verification']}`")
        lines.append("")

    # Architecture overview
    arch = document.get("architecture", {})
    if arch.get("description") or arch.get("components"):
        lines.extend(["## Architecture Overview", ""])
        if arch.get("description"):
            lines.extend([arch["description"], ""])
        if arch.get("components"):
            lines.append("### Components")
            lines.append("")
            for comp in arch["components"]:
                lines.append(f"- **{comp['name']}**: {comp.get('description', '')}")
            lines.append("")

    # Conventions
    conventions = document.get("conventions", [])
    if conventions:
        lines.extend(["## Key Conventions", ""])
        for conv in conventions:
            lines.append(f"### {conv['title']}")
            lines.append("")
            if conv.get("description"):
                lines.append(conv["description"])
                lines.append("")

    # First tasks
    first_tasks = document.get("first_tasks", [])
    if first_tasks:
        lines.extend(["## Suggested First Contributions", ""])
        for i, task in enumerate(first_tasks, 1):
            difficulty = task.get("difficulty", "beginner")
            lines.append(f"{i}. **{task['title']}** [{difficulty}]")
            if task.get("description"):
                lines.append(f"   - {task['description']}")
        lines.append("")

    # Learning path
    learning_path = document.get("learning_path", [])
    if learning_path:
        lines.extend(["## Learning Path", ""])
        for i, milestone in enumerate(learning_path, 1):
            lines.append(f"### Milestone {i}: {milestone['title']}")
            lines.append("")
            if milestone.get("description"):
                lines.append(milestone["description"])
                lines.append("")
            if milestone.get("resources"):
                lines.append("**Suggested reading:**")
                lines.append("")
                for res in milestone["resources"]:
                    lines.append(f"- {res}")
                lines.append("")

    # Resources
    resources = document.get("resources", [])
    if resources:
        lines.extend(["## Additional Resources", ""])
        for res in resources:
            if res.get("url"):
                lines.append(f"- [{res['title']}]({res['url']})")
            else:
                lines.append(f"- {res['title']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_onboarding_json(document: dict[str, Any]) -> str:
    """Render onboarding guide as formatted JSON."""
    return json.dumps(document, indent=2, default=str)


def _validate_setup_step(step: dict[str, Any]) -> dict[str, Any]:
    """Validate an environment setup step."""
    return {
        "title": step.get("title", ""),
        "instructions": step.get("instructions", ""),
        "verification": step.get("verification", ""),
    }


def _validate_architecture(arch: dict[str, Any]) -> dict[str, Any]:
    """Validate architecture overview."""
    components = []
    for comp in arch.get("components", []):
        components.append({
            "name": comp.get("name", ""),
            "description": comp.get("description", ""),
        })
    return {
        "description": arch.get("description", ""),
        "components": components,
    }


def _validate_convention(conv: dict[str, Any]) -> dict[str, Any]:
    """Validate a convention entry."""
    return {
        "title": conv.get("title", ""),
        "description": conv.get("description", ""),
    }


def _validate_task(task: dict[str, Any]) -> dict[str, Any]:
    """Validate a first-task suggestion."""
    return {
        "title": task.get("title", ""),
        "description": task.get("description", ""),
        "difficulty": task.get("difficulty", "beginner"),
    }


def _validate_milestone(milestone: dict[str, Any]) -> dict[str, Any]:
    """Validate a learning path milestone."""
    return {
        "title": milestone.get("title", ""),
        "description": milestone.get("description", ""),
        "resources": milestone.get("resources", []),
    }


def _validate_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Validate a resource entry."""
    return {
        "title": resource.get("title", ""),
        "url": resource.get("url", ""),
    }
