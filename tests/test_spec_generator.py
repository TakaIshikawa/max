"""Tests for spec generator — transformation/normalization logic after LLM call."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from max.spec.generator import (
    DecisionOutput,
    GoalOutput,
    PatternOutput,
    RequirementOutput,
    SpecOutput,
    TechStackOutput,
    generate_spec,
)
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_dimension(value: float = 7.0, confidence: float = 0.7) -> DimensionScore:
    return DimensionScore(value=value, confidence=confidence, reasoning="test")


@pytest.fixture
def unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-gen001",
        title="Spec Gen Test Unit",
        one_liner="A unit for testing spec generation",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Need to validate spec generation",
        solution="Write comprehensive tests",
        target_users="both",
        value_proposition="Confidence in spec transformation logic",
        inspiring_insights=["ins-001"],
        evidence_signals=["sig-001"],
        tech_approach="Python with pytest",
        suggested_stack={"language": "python", "runtime": "cpython"},
        composability_notes="Standalone test suite",
    )


@pytest.fixture
def evaluation() -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id="bu-gen001",
        pain_severity=_make_dimension(8.0),
        addressable_scale=_make_dimension(7.0),
        build_effort=_make_dimension(7.5),
        composability=_make_dimension(8.5),
        competitive_density=_make_dimension(9.0),
        timing_fit=_make_dimension(8.0),
        compounding_value=_make_dimension(7.0),
        overall_score=78.0,
        strengths=["Strong demand", "Low competition"],
        weaknesses=["Small audience"],
        recommendation="yes",
    )


@pytest.fixture
def full_spec_output() -> SpecOutput:
    """A realistic SpecOutput as returned by the LLM."""
    return SpecOutput(
        name="spec-gen-tool",
        vision="Automated spec generation for buildable units",
        goals=[
            GoalOutput(id="G-1", description="Generate valid specs", success_criteria="All specs pass validation"),
            GoalOutput(id="G-2", description="Handle edge cases", success_criteria="No crashes on empty input"),
        ],
        tech_stack=TechStackOutput(
            languages=["Python"],
            frameworks=["Pydantic", "pytest"],
            infrastructure=["pip"],
        ),
        constraints=["MVP scope only", "No external API calls"],
        patterns=[
            PatternOutput(name="Builder", description="Builds specs step by step", scope=["generator"]),
        ],
        invariants=["All specs must have at least one requirement"],
        conventions=["snake_case for Python"],
        decisions=[
            DecisionOutput(
                id="ADR-1",
                title="Use Pydantic for validation",
                decision="Pydantic v2 models",
                rationale="Type safety and serialization",
            ),
        ],
        requirements=[
            RequirementOutput(
                title="Implement core generator",
                priority="critical",
                description="Core spec generation logic",
                acceptance_criteria=["Generates valid product section", "Generates requirements"],
                dependencies=[],
            ),
            RequirementOutput(
                title="Add validation layer",
                priority="high",
                description="Post-generation validation",
                acceptance_criteria=["Validates priorities", "Validates acceptance criteria"],
                dependencies=["Implement core generator"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Priority normalization
# ---------------------------------------------------------------------------


class TestPriorityNormalization:
    """The generator normalizes invalid priorities to 'medium'."""

    @pytest.mark.parametrize("priority", ["critical", "high", "medium", "low"])
    def test_valid_priorities_pass_through(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation, priority: str
    ) -> None:
        spec_output = SpecOutput(
            name="test",
            vision="test",
            requirements=[RequirementOutput(title="req", priority=priority)],
        )
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.requirements[0].priority == priority

    @pytest.mark.parametrize("invalid", ["urgent", "p0", "P1", "", "none", "CRITICAL", "High"])
    def test_invalid_priorities_normalize_to_medium(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation, invalid: str
    ) -> None:
        spec_output = SpecOutput(
            name="test",
            vision="test",
            requirements=[RequirementOutput(title="req", priority=invalid)],
        )
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.requirements[0].priority == "medium"


# ---------------------------------------------------------------------------
# Acceptance criteria fallback
# ---------------------------------------------------------------------------


class TestAcceptanceCriteriaFallback:
    """Requirements with empty acceptance_criteria get ['TBD'] as default."""

    def test_empty_acceptance_criteria_becomes_tbd(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        spec_output = SpecOutput(
            name="test",
            vision="test",
            requirements=[RequirementOutput(title="req", acceptance_criteria=[])],
        )
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.requirements[0].acceptance_criteria == ["TBD"]

    def test_nonempty_acceptance_criteria_preserved(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        criteria = ["AC-1", "AC-2"]
        spec_output = SpecOutput(
            name="test",
            vision="test",
            requirements=[RequirementOutput(title="req", acceptance_criteria=criteria)],
        )
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.requirements[0].acceptance_criteria == criteria


# ---------------------------------------------------------------------------
# Full transformation pipeline
# ---------------------------------------------------------------------------


class TestFullTransformationPipeline:
    """Mock structured_call with a complete SpecOutput and verify the TactSpec."""

    def test_product_fields(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation, full_spec_output: SpecOutput
    ) -> None:
        with patch("max.spec.generator.structured_call", return_value=full_spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.product.name == "spec-gen-tool"
        assert spec.product.vision == "Automated spec generation for buildable units"
        assert len(spec.product.goals) == 2
        assert spec.product.goals[0].id == "G-1"
        assert spec.product.goals[0].description == "Generate valid specs"
        assert spec.product.goals[0].success_criteria == "All specs pass validation"
        assert spec.product.goals[1].id == "G-2"
        assert spec.product.tech_stack.languages == ["Python"]
        assert spec.product.tech_stack.frameworks == ["Pydantic", "pytest"]
        assert spec.product.tech_stack.infrastructure == ["pip"]
        assert spec.product.constraints == ["MVP scope only", "No external API calls"]

    def test_architecture_fields(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation, full_spec_output: SpecOutput
    ) -> None:
        with patch("max.spec.generator.structured_call", return_value=full_spec_output):
            spec = generate_spec(unit, evaluation)

        assert len(spec.architecture.patterns) == 1
        assert spec.architecture.patterns[0].name == "Builder"
        assert spec.architecture.patterns[0].description == "Builds specs step by step"
        assert spec.architecture.patterns[0].scope == ["generator"]
        assert spec.architecture.invariants == ["All specs must have at least one requirement"]
        assert spec.architecture.conventions == ["snake_case for Python"]
        assert len(spec.architecture.decisions) == 1
        assert spec.architecture.decisions[0].id == "ADR-1"
        assert spec.architecture.decisions[0].title == "Use Pydantic for validation"
        assert spec.architecture.decisions[0].decision == "Pydantic v2 models"
        assert spec.architecture.decisions[0].rationale == "Type safety and serialization"

    def test_requirements_fields(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation, full_spec_output: SpecOutput
    ) -> None:
        with patch("max.spec.generator.structured_call", return_value=full_spec_output):
            spec = generate_spec(unit, evaluation)

        assert len(spec.requirements) == 2
        req0 = spec.requirements[0]
        assert req0.title == "Implement core generator"
        assert req0.priority == "critical"
        assert req0.description == "Core spec generation logic"
        assert req0.acceptance_criteria == ["Generates valid product section", "Generates requirements"]
        assert req0.dependencies == []

        req1 = spec.requirements[1]
        assert req1.title == "Add validation layer"
        assert req1.priority == "high"
        assert req1.dependencies == ["Implement core generator"]

    def test_buildable_unit_id(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation, full_spec_output: SpecOutput
    ) -> None:
        with patch("max.spec.generator.structured_call", return_value=full_spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.buildable_unit_id == "bu-gen001"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty lists, missing fields, minimal input."""

    def test_empty_goals(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        spec_output = SpecOutput(name="test", vision="test", goals=[])
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.product.goals == []

    def test_empty_patterns_and_decisions(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        spec_output = SpecOutput(name="test", vision="test", patterns=[], decisions=[])
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.architecture.patterns == []
        assert spec.architecture.decisions == []

    def test_empty_tech_stack(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        spec_output = SpecOutput(
            name="test",
            vision="test",
            tech_stack=TechStackOutput(languages=[], frameworks=[], infrastructure=[]),
        )
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.product.tech_stack.languages == []
        assert spec.product.tech_stack.frameworks == []
        assert spec.product.tech_stack.infrastructure == []

    def test_requirement_with_all_fields_empty(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        spec_output = SpecOutput(
            name="test",
            vision="test",
            requirements=[
                RequirementOutput(
                    title="",
                    priority="",
                    description="",
                    acceptance_criteria=[],
                    dependencies=[],
                ),
            ],
        )
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        req = spec.requirements[0]
        assert req.title == ""
        assert req.priority == "medium"  # empty string normalized
        assert req.description == ""
        assert req.acceptance_criteria == ["TBD"]  # empty list fallback
        assert req.dependencies == []

    def test_unit_with_empty_suggested_stack(
        self, evaluation: UtilityEvaluation
    ) -> None:
        unit = BuildableUnit(
            id="bu-empty-stack",
            title="Minimal Unit",
            one_liner="Minimal",
            category="cli_tool",
            problem="None",
            solution="None",
            value_proposition="None",
            suggested_stack={},
        )
        spec_output = SpecOutput(name="minimal", vision="minimal")
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.buildable_unit_id == "bu-empty-stack"
        assert spec.product.name == "minimal"

    def test_no_requirements_yields_empty_list(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        spec_output = SpecOutput(name="test", vision="test", requirements=[])
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.requirements == []

    def test_multiple_invalid_priorities_in_same_spec(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        spec_output = SpecOutput(
            name="test",
            vision="test",
            requirements=[
                RequirementOutput(title="a", priority="urgent"),
                RequirementOutput(title="b", priority="critical"),
                RequirementOutput(title="c", priority="MEDIUM"),
                RequirementOutput(title="d", priority="low"),
            ],
        )
        with patch("max.spec.generator.structured_call", return_value=spec_output):
            spec = generate_spec(unit, evaluation)

        assert spec.requirements[0].priority == "medium"   # "urgent" → normalized
        assert spec.requirements[1].priority == "critical"  # valid
        assert spec.requirements[2].priority == "medium"    # "MEDIUM" → normalized (case-sensitive)
        assert spec.requirements[3].priority == "low"       # valid


# ---------------------------------------------------------------------------
# JSON serialization passed to LLM
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    """Verify unit_json and eval_json contain expected fields."""

    def test_unit_json_fields(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        captured_prompt = {}

        def fake_structured_call(*, system, prompt, output_type, temperature, stage):
            captured_prompt["prompt"] = prompt
            return SpecOutput(name="test", vision="test")

        with patch("max.spec.generator.structured_call", side_effect=fake_structured_call):
            generate_spec(unit, evaluation)

        prompt = captured_prompt["prompt"]
        # The unit JSON should contain these fields
        assert '"id": "bu-gen001"' in prompt
        assert '"title": "Spec Gen Test Unit"' in prompt
        assert '"one_liner": "A unit for testing spec generation"' in prompt
        assert '"category": "cli_tool"' in prompt
        assert '"problem": "Need to validate spec generation"' in prompt
        assert '"solution": "Write comprehensive tests"' in prompt
        assert '"target_users": "both"' in prompt
        assert '"value_proposition": "Confidence in spec transformation logic"' in prompt
        assert '"tech_approach": "Python with pytest"' in prompt
        assert '"suggested_stack"' in prompt
        assert '"composability_notes": "Standalone test suite"' in prompt

    def test_eval_json_fields(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        captured_prompt = {}

        def fake_structured_call(*, system, prompt, output_type, temperature, stage):
            captured_prompt["prompt"] = prompt
            return SpecOutput(name="test", vision="test")

        with patch("max.spec.generator.structured_call", side_effect=fake_structured_call):
            generate_spec(unit, evaluation)

        prompt = captured_prompt["prompt"]
        assert '"overall_score": 78.0' in prompt
        assert '"strengths"' in prompt
        assert '"Strong demand"' in prompt
        assert '"weaknesses"' in prompt
        assert '"Small audience"' in prompt
        assert '"recommendation": "yes"' in prompt

    def test_unit_json_excludes_internal_fields(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        """The serialized JSON should not include fields not explicitly selected."""
        captured_prompt = {}

        def fake_structured_call(*, system, prompt, output_type, temperature, stage):
            captured_prompt["prompt"] = prompt
            return SpecOutput(name="test", vision="test")

        with patch("max.spec.generator.structured_call", side_effect=fake_structured_call):
            generate_spec(unit, evaluation)

        prompt = captured_prompt["prompt"]
        # Fields that should NOT be in the serialized unit JSON
        assert '"inspiring_insights"' not in prompt
        assert '"evidence_signals"' not in prompt
        assert '"status"' not in prompt
        assert '"created_at"' not in prompt
        assert '"updated_at"' not in prompt
        assert '"domain"' not in prompt
        assert '"ideation_mode"' not in prompt

    def test_structured_call_receives_correct_kwargs(
        self, unit: BuildableUnit, evaluation: UtilityEvaluation
    ) -> None:
        with patch("max.spec.generator.structured_call", return_value=SpecOutput(name="t", vision="v")) as mock:
            generate_spec(unit, evaluation)

        mock.assert_called_once()
        kwargs = mock.call_args.kwargs
        assert kwargs["output_type"] is SpecOutput
        assert kwargs["temperature"] == 0.4
        assert kwargs["stage"] == "spec_generation"
        assert isinstance(kwargs["system"], str)
        assert isinstance(kwargs["prompt"], str)
