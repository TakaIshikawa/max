"""Tests for tact compatibility — validates generated specs against tact constraints."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from max.publisher.file_writer import write_tact_spec
from max.types.tact_spec import (
    TactArchitecture,
    TactGoal,
    TactProduct,
    TactRequirement,
    TactSpec,
    TactTechStack,
)

VALID_PRIORITIES = {"critical", "high", "medium", "low"}


def _make_spec(
    *,
    goals: list[TactGoal] | None = None,
    requirements: list[TactRequirement] | None = None,
) -> TactSpec:
    return TactSpec(
        buildable_unit_id="bu-val001",
        product=TactProduct(
            name="validation-test",
            vision="Test spec for validation",
            goals=goals or [
                TactGoal(id="G-1", description="Goal one", success_criteria="SC-1"),
                TactGoal(id="G-2", description="Goal two", success_criteria="SC-2"),
            ],
            tech_stack=TactTechStack(languages=["Python"]),
            constraints=["Test constraint"],
        ),
        architecture=TactArchitecture(
            invariants=["No side effects"],
            conventions=["snake_case"],
        ),
        requirements=requirements or [
            TactRequirement(
                title="First requirement",
                priority="critical",
                description="Something critical",
                acceptance_criteria=["AC-1", "AC-2"],
            ),
            TactRequirement(
                title="Second requirement",
                priority="medium",
                description="Something medium",
                acceptance_criteria=["AC-3"],
                dependencies=["First requirement"],
            ),
        ],
    )


def test_acceptance_criteria_minimum_one() -> None:
    """Every requirement must have at least 1 acceptance criterion."""
    spec = _make_spec()
    for req in spec.requirements:
        assert len(req.acceptance_criteria) >= 1, f"Requirement '{req.title}' has no acceptance criteria"


def test_priority_enum_values() -> None:
    """Priority must be one of the valid tact enum values."""
    spec = _make_spec()
    for req in spec.requirements:
        assert req.priority in VALID_PRIORITIES, (
            f"Requirement '{req.title}' has invalid priority '{req.priority}'"
        )


def test_goal_id_uniqueness() -> None:
    """Goal IDs must be unique within a spec."""
    spec = _make_spec()
    goal_ids = [g.id for g in spec.product.goals]
    assert len(goal_ids) == len(set(goal_ids)), f"Duplicate goal IDs: {goal_ids}"


def test_product_name_is_kebab_case() -> None:
    """Product name should be kebab-case (no spaces, no uppercase)."""
    spec = _make_spec()
    name = spec.product.name
    assert " " not in name, f"Product name contains spaces: '{name}'"
    assert name == name.lower(), f"Product name not lowercase: '{name}'"


def test_yaml_output_validates_against_tact_constraints(tmp_path: Path) -> None:
    """Write spec to YAML and validate the output files match tact expectations."""
    spec = _make_spec()
    output_dir = tmp_path / ".tact"
    write_tact_spec(spec, output_dir)

    # Validate product.yaml
    with open(output_dir / "product.yaml") as f:
        product = yaml.safe_load(f)
    assert "techStack" in product, "product.yaml missing techStack (camelCase)"
    assert "name" in product
    assert "vision" in product
    assert isinstance(product["goals"], list)
    for goal in product["goals"]:
        assert "successCriteria" in goal, f"Goal missing successCriteria: {goal}"
        assert "id" in goal
        assert "description" in goal

    # Validate architecture.yaml
    with open(output_dir / "architecture.yaml") as f:
        arch = yaml.safe_load(f)
    assert isinstance(arch.get("invariants", []), list)
    assert isinstance(arch.get("conventions", []), list)

    # Validate requirements
    req_dir = output_dir / "requirements"
    req_files = sorted(req_dir.glob("REQ-*.yaml"))
    assert len(req_files) >= 1, "No requirement files generated"

    for req_file in req_files:
        with open(req_file) as f:
            req = yaml.safe_load(f)
        assert "title" in req, f"{req_file.name} missing title"
        assert "acceptanceCriteria" in req, f"{req_file.name} missing acceptanceCriteria"
        assert isinstance(req["acceptanceCriteria"], list)
        assert len(req["acceptanceCriteria"]) >= 1, (
            f"{req_file.name} has empty acceptanceCriteria"
        )
        assert req.get("priority") in VALID_PRIORITIES, (
            f"{req_file.name} has invalid priority: {req.get('priority')}"
        )


def test_generated_yaml_from_e2e_output() -> None:
    """If .tact/ output exists from an e2e run, validate all specs."""
    tact_dir = Path("/Users/taka/Project/experiments/max/.tact")
    if not tact_dir.exists():
        pytest.skip("No .tact/ output from e2e run")

    for project_dir in tact_dir.iterdir():
        if not project_dir.is_dir():
            continue

        product_path = project_dir / "product.yaml"
        assert product_path.exists(), f"Missing product.yaml in {project_dir.name}"

        with open(product_path) as f:
            product = yaml.safe_load(f)
        assert "techStack" in product, f"{project_dir.name}/product.yaml missing techStack"

        # Check goal ID uniqueness
        goal_ids = [g["id"] for g in product.get("goals", [])]
        assert len(goal_ids) == len(set(goal_ids)), (
            f"{project_dir.name} has duplicate goal IDs: {goal_ids}"
        )

        # Check all requirements
        req_dir = project_dir / "requirements"
        if req_dir.exists():
            for req_file in req_dir.glob("REQ-*.yaml"):
                with open(req_file) as f:
                    req = yaml.safe_load(f)
                assert len(req.get("acceptanceCriteria", [])) >= 1, (
                    f"{project_dir.name}/{req_file.name} has no acceptanceCriteria"
                )
                assert req.get("priority") in VALID_PRIORITIES, (
                    f"{project_dir.name}/{req_file.name} invalid priority: {req.get('priority')}"
                )
