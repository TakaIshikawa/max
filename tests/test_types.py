"""Tests for type serialization and validation."""

from __future__ import annotations

import json

from max.types.tact_spec import TactGoal, TactProduct, TactRequirement, TactSpec, TactTechStack, TactArchitecture


def test_tact_product_camel_case_serialization() -> None:
    product = TactProduct(
        name="test-project",
        vision="A test project",
        tech_stack=TactTechStack(languages=["Python"]),
    )
    data = product.model_dump(by_alias=True)
    assert "techStack" in data
    assert "tech_stack" not in data


def test_tact_goal_camel_case_serialization() -> None:
    goal = TactGoal(id="G-1", description="Test", success_criteria="Works")
    data = goal.model_dump(by_alias=True)
    assert "successCriteria" in data
    assert data["successCriteria"] == "Works"


def test_tact_requirement_camel_case_serialization() -> None:
    req = TactRequirement(
        title="Test requirement",
        acceptance_criteria=["Criterion 1", "Criterion 2"],
    )
    data = req.model_dump(by_alias=True)
    assert "acceptanceCriteria" in data
    assert len(data["acceptanceCriteria"]) == 2


def test_tact_spec_round_trip_json() -> None:
    spec = TactSpec(
        buildable_unit_id="bu-001",
        product=TactProduct(name="test", vision="test vision"),
        architecture=TactArchitecture(),
        requirements=[
            TactRequirement(
                title="First requirement",
                acceptance_criteria=["AC-1"],
            ),
        ],
    )
    json_str = spec.model_dump_json(by_alias=True)
    parsed = json.loads(json_str)
    assert parsed["product"]["name"] == "test"
    assert parsed["requirements"][0]["acceptanceCriteria"] == ["AC-1"]

    # Round-trip back to model
    restored = TactSpec.model_validate_json(json_str)
    assert restored.product.name == "test"
    assert restored.requirements[0].acceptance_criteria == ["AC-1"]
