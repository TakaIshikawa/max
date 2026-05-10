"""Tests for developer onboarding guide export."""

from __future__ import annotations

import json

from max.exports.onboarding_guide import (
    KIND,
    SCHEMA_VERSION,
    build_onboarding_guide,
    render_onboarding_json,
    render_onboarding_markdown,
)


# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_SETUP_STEPS = [
    {
        "title": "Install Python 3.11+",
        "instructions": "Use pyenv: `pyenv install 3.11`",
        "verification": "python --version",
    },
    {
        "title": "Clone the repository",
        "instructions": "git clone git@github.com:org/project.git",
        "verification": "ls project/",
    },
    {
        "title": "Install dependencies",
        "instructions": "Run `pip install -e '.[dev]'`",
        "verification": "pytest --version",
    },
]

SAMPLE_ARCHITECTURE = {
    "description": "Monorepo with modular service architecture",
    "components": [
        {"name": "API Gateway", "description": "FastAPI-based REST/GraphQL gateway"},
        {"name": "Worker Pool", "description": "Celery workers for async processing"},
        {"name": "Data Store", "description": "PostgreSQL with SQLAlchemy ORM"},
    ],
}

SAMPLE_CONVENTIONS = [
    {"title": "Code Style", "description": "We use ruff for linting and black for formatting"},
    {"title": "Git Workflow", "description": "Feature branches off main, squash-merge PRs"},
]

SAMPLE_FIRST_TASKS = [
    {"title": "Fix a typo in docs", "description": "Find and fix any typo in README", "difficulty": "beginner"},
    {"title": "Add a unit test", "description": "Increase coverage for utils module", "difficulty": "intermediate"},
]

SAMPLE_LEARNING_PATH = [
    {
        "title": "Understand the data model",
        "description": "Learn how entities relate to each other",
        "resources": ["docs/data-model.md", "src/models/README.md"],
    },
    {
        "title": "Master the API layer",
        "description": "Understand request/response lifecycle",
        "resources": ["docs/api-guide.md"],
    },
]

SAMPLE_RESOURCES = [
    {"title": "Project Wiki", "url": "https://wiki.example.com/project"},
    {"title": "API Docs", "url": "https://api.example.com/docs"},
]


# ── build_onboarding_guide tests ─────────────────────────────────────


def test_build_onboarding_guide_schema() -> None:
    doc = build_onboarding_guide()
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "generated_at" in doc


def test_build_onboarding_guide_project_name() -> None:
    doc = build_onboarding_guide(project_name="MaxPlatform")
    assert doc["project_name"] == "MaxPlatform"


def test_build_onboarding_guide_setup_steps() -> None:
    doc = build_onboarding_guide(setup_steps=SAMPLE_SETUP_STEPS)
    assert len(doc["setup_steps"]) == 3
    assert doc["setup_steps"][0]["title"] == "Install Python 3.11+"
    assert doc["setup_steps"][0]["verification"] == "python --version"


def test_build_onboarding_guide_architecture() -> None:
    doc = build_onboarding_guide(architecture=SAMPLE_ARCHITECTURE)
    assert doc["architecture"]["description"] == "Monorepo with modular service architecture"
    assert len(doc["architecture"]["components"]) == 3


def test_build_onboarding_guide_conventions() -> None:
    doc = build_onboarding_guide(conventions=SAMPLE_CONVENTIONS)
    assert len(doc["conventions"]) == 2
    assert doc["conventions"][0]["title"] == "Code Style"


def test_build_onboarding_guide_first_tasks() -> None:
    doc = build_onboarding_guide(first_tasks=SAMPLE_FIRST_TASKS)
    assert len(doc["first_tasks"]) == 2
    assert doc["first_tasks"][0]["difficulty"] == "beginner"


def test_build_onboarding_guide_learning_path() -> None:
    doc = build_onboarding_guide(learning_path=SAMPLE_LEARNING_PATH)
    assert len(doc["learning_path"]) == 2
    assert doc["learning_path"][0]["title"] == "Understand the data model"
    assert len(doc["learning_path"][0]["resources"]) == 2


def test_build_onboarding_guide_empty() -> None:
    doc = build_onboarding_guide()
    assert doc["setup_steps"] == []
    assert doc["conventions"] == []
    assert doc["first_tasks"] == []
    assert doc["learning_path"] == []


# ── Markdown rendering — checklists ──────────────────────────────────


def test_render_onboarding_markdown_title() -> None:
    doc = build_onboarding_guide(project_name="MyProject")
    md = render_onboarding_markdown(doc)
    assert "# Developer Onboarding — MyProject" in md


def test_render_onboarding_markdown_setup_checklist() -> None:
    doc = build_onboarding_guide(setup_steps=SAMPLE_SETUP_STEPS)
    md = render_onboarding_markdown(doc)
    assert "## Environment Setup" in md
    assert "- [ ] **Install Python 3.11+**" in md
    assert "- [ ] **Clone the repository**" in md
    assert "- [ ] **Install dependencies**" in md


def test_render_onboarding_markdown_setup_verification() -> None:
    doc = build_onboarding_guide(setup_steps=SAMPLE_SETUP_STEPS)
    md = render_onboarding_markdown(doc)
    assert "Verify: `python --version`" in md


def test_render_onboarding_markdown_architecture() -> None:
    doc = build_onboarding_guide(architecture=SAMPLE_ARCHITECTURE)
    md = render_onboarding_markdown(doc)
    assert "## Architecture Overview" in md
    assert "Monorepo with modular service architecture" in md
    assert "**API Gateway**" in md
    assert "**Worker Pool**" in md


def test_render_onboarding_markdown_conventions() -> None:
    doc = build_onboarding_guide(conventions=SAMPLE_CONVENTIONS)
    md = render_onboarding_markdown(doc)
    assert "## Key Conventions" in md
    assert "### Code Style" in md
    assert "ruff" in md


def test_render_onboarding_markdown_first_tasks() -> None:
    doc = build_onboarding_guide(first_tasks=SAMPLE_FIRST_TASKS)
    md = render_onboarding_markdown(doc)
    assert "## Suggested First Contributions" in md
    assert "**Fix a typo in docs** [beginner]" in md
    assert "**Add a unit test** [intermediate]" in md


def test_render_onboarding_markdown_learning_path() -> None:
    doc = build_onboarding_guide(learning_path=SAMPLE_LEARNING_PATH)
    md = render_onboarding_markdown(doc)
    assert "## Learning Path" in md
    assert "### Milestone 1: Understand the data model" in md
    assert "### Milestone 2: Master the API layer" in md
    assert "docs/data-model.md" in md


def test_render_onboarding_markdown_resources() -> None:
    doc = build_onboarding_guide(resources=SAMPLE_RESOURCES)
    md = render_onboarding_markdown(doc)
    assert "## Additional Resources" in md
    assert "[Project Wiki](https://wiki.example.com/project)" in md


def test_render_onboarding_markdown_empty_sections_omitted() -> None:
    doc = build_onboarding_guide()
    md = render_onboarding_markdown(doc)
    assert "## Environment Setup" not in md
    assert "## Architecture Overview" not in md
    assert "## Key Conventions" not in md


# ── JSON rendering ───────────────────────────────────────────────────


def test_render_onboarding_json_valid() -> None:
    doc = build_onboarding_guide(
        project_name="Test",
        setup_steps=SAMPLE_SETUP_STEPS,
        architecture=SAMPLE_ARCHITECTURE,
    )
    output = render_onboarding_json(doc)
    parsed = json.loads(output)
    assert parsed["project_name"] == "Test"
    assert len(parsed["setup_steps"]) == 3


def test_render_onboarding_json_roundtrip() -> None:
    doc = build_onboarding_guide(learning_path=SAMPLE_LEARNING_PATH)
    output = render_onboarding_json(doc)
    parsed = json.loads(output)
    assert len(parsed["learning_path"]) == 2
    assert parsed["learning_path"][0]["resources"] == ["docs/data-model.md", "src/models/README.md"]
