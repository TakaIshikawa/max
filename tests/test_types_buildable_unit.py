"""Tests for BuildableUnit type serialization and validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


def test_buildable_category_enum_values() -> None:
    """Test that BuildableCategory enum has expected values."""
    assert BuildableCategory.MCP_SERVER == "mcp_server"
    assert BuildableCategory.CLI_TOOL == "cli_tool"
    assert BuildableCategory.LIBRARY == "library"
    assert BuildableCategory.INTEGRATION == "integration"
    assert BuildableCategory.AUTOMATION == "automation"
    assert BuildableCategory.APPLICATION == "application"
    assert BuildableCategory.FEATURE == "feature"


def test_ideation_mode_enum_values() -> None:
    """Test that IdeationMode enum has expected values."""
    assert IdeationMode.DIRECT == "direct"
    assert IdeationMode.REFINEMENT == "refinement"
    assert IdeationMode.CROSS_DOMAIN == "cross_domain"
    assert IdeationMode.SYNTHESIS == "synthesis"
    assert IdeationMode.CROSS_SYNTHESIS == "cross_synthesis"


def test_buildable_unit_minimal_construction() -> None:
    """Test BuildableUnit construction with minimal required fields."""
    unit = BuildableUnit(
        title="Test Project",
        one_liner="A test project for validation",
        category="library",
        problem="Need to test something",
        solution="Build a test framework",
        value_proposition="Makes testing easier",
    )
    assert unit.title == "Test Project"
    assert unit.one_liner == "A test project for validation"
    assert unit.category == "library"
    assert unit.problem == "Need to test something"
    assert unit.solution == "Build a test framework"
    assert unit.value_proposition == "Makes testing easier"

    # Check defaults
    assert unit.id == ""
    assert unit.ideation_mode == IdeationMode.DIRECT
    assert unit.target_users == "both"
    assert unit.inspiring_insights == []
    assert unit.evidence_signals == []
    assert unit.source_idea_ids == []
    assert unit.tech_approach == ""
    assert unit.suggested_stack == {}
    assert unit.composability_notes == ""
    assert unit.domain == ""
    assert unit.prior_art_status == "unchecked"
    assert unit.status == "draft"
    assert isinstance(unit.created_at, datetime)
    assert isinstance(unit.updated_at, datetime)


def test_buildable_unit_all_fields() -> None:
    """Test BuildableUnit construction with all fields populated."""
    created = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    updated = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

    unit = BuildableUnit(
        id="bu-001",
        title="Full Feature",
        one_liner="Complete test coverage",
        category=BuildableCategory.MCP_SERVER,
        ideation_mode=IdeationMode.SYNTHESIS,
        problem="Complex problem statement",
        solution="Detailed solution approach",
        target_users="agents",
        value_proposition="High value for AI agents",
        inspiring_insights=["insight-1", "insight-2"],
        evidence_signals=["signal-1", "signal-2", "signal-3"],
        source_idea_ids=["idea-1", "idea-2"],
        tech_approach="Use Python with async/await",
        suggested_stack={"language": "Python", "framework": "FastAPI"},
        composability_notes="Works well with other MCP servers",
        domain="engineering",
        prior_art_status="clear",
        status="approved",
        created_at=created,
        updated_at=updated,
    )

    assert unit.id == "bu-001"
    assert unit.title == "Full Feature"
    assert unit.category == "mcp_server"
    assert unit.ideation_mode == IdeationMode.SYNTHESIS
    assert unit.target_users == "agents"
    assert len(unit.inspiring_insights) == 2
    assert len(unit.evidence_signals) == 3
    assert len(unit.source_idea_ids) == 2
    assert unit.tech_approach == "Use Python with async/await"
    assert unit.suggested_stack["language"] == "Python"
    assert unit.composability_notes == "Works well with other MCP servers"
    assert unit.domain == "engineering"
    assert unit.prior_art_status == "clear"
    assert unit.status == "approved"
    assert unit.created_at == created
    assert unit.updated_at == updated


def test_buildable_unit_missing_required_fields() -> None:
    """Test that BuildableUnit raises ValidationError when required fields are missing."""
    with pytest.raises(ValidationError) as exc_info:
        BuildableUnit()

    errors = exc_info.value.errors()
    required_fields = {err["loc"][0] for err in errors}
    assert "title" in required_fields
    assert "one_liner" in required_fields
    assert "category" in required_fields
    assert "problem" in required_fields
    assert "solution" in required_fields
    assert "value_proposition" in required_fields


def test_buildable_unit_invalid_ideation_mode() -> None:
    """Test that invalid ideation_mode raises ValidationError."""
    # Explicitly type as Any to test runtime validation of invalid value
    invalid_mode: Any = "invalid_mode"

    with pytest.raises(ValidationError) as exc_info:
        BuildableUnit(
            title="Test",
            one_liner="Test",
            category="library",
            problem="Test problem",
            solution="Test solution",
            value_proposition="Test value",
            ideation_mode=invalid_mode,
        )

    errors = exc_info.value.errors()
    assert any("ideation_mode" in str(err["loc"]) for err in errors)


def test_buildable_unit_category_accepts_string() -> None:
    """Test that category accepts any string (profile-defined categories)."""
    unit = BuildableUnit(
        title="Custom Category",
        one_liner="Test custom category",
        category="custom_category",  # Not in BuildableCategory enum
        problem="Test",
        solution="Test",
        value_proposition="Test",
    )
    assert unit.category == "custom_category"


def test_buildable_unit_category_accepts_enum() -> None:
    """Test that category accepts BuildableCategory enum values."""
    unit = BuildableUnit(
        title="Enum Category",
        one_liner="Test enum category",
        category=BuildableCategory.CLI_TOOL,
        problem="Test",
        solution="Test",
        value_proposition="Test",
    )
    assert unit.category == "cli_tool"


def test_buildable_unit_serialization() -> None:
    """Test BuildableUnit serialization to dict."""
    unit = BuildableUnit(
        id="bu-002",
        title="Test Serialization",
        one_liner="Testing JSON conversion",
        category=BuildableCategory.LIBRARY,
        ideation_mode=IdeationMode.REFINEMENT,
        problem="Need serialization",
        solution="Use Pydantic",
        value_proposition="Easy JSON handling",
        inspiring_insights=["insight-1"],
        suggested_stack={"lang": "Python"},
    )

    data = unit.model_dump()
    assert data["id"] == "bu-002"
    assert data["title"] == "Test Serialization"
    assert data["category"] == "library"
    assert data["ideation_mode"] == "refinement"
    assert data["inspiring_insights"] == ["insight-1"]
    assert data["suggested_stack"] == {"lang": "Python"}
    assert "created_at" in data
    assert "updated_at" in data


def test_buildable_unit_json_round_trip() -> None:
    """Test BuildableUnit JSON serialization and deserialization."""
    original = BuildableUnit(
        id="bu-003",
        title="Round Trip Test",
        one_liner="Testing JSON round-trip",
        category=BuildableCategory.INTEGRATION,
        ideation_mode=IdeationMode.CROSS_DOMAIN,
        problem="Data persistence",
        solution="JSON serialization",
        value_proposition="Portable data format",
        inspiring_insights=["i1", "i2"],
        evidence_signals=["s1"],
        source_idea_ids=["idea-x"],
        tech_approach="REST API",
        suggested_stack={"protocol": "HTTP"},
        composability_notes="RESTful",
        domain="backend",
        prior_art_status="weak_match",
        status="evaluated",
    )

    # Serialize to JSON
    json_str = original.model_dump_json()
    parsed = json.loads(json_str)

    assert parsed["id"] == "bu-003"
    assert parsed["title"] == "Round Trip Test"
    assert parsed["category"] == "integration"
    assert parsed["ideation_mode"] == "cross_domain"
    assert parsed["inspiring_insights"] == ["i1", "i2"]
    assert parsed["prior_art_status"] == "weak_match"

    # Deserialize from JSON
    restored = BuildableUnit.model_validate_json(json_str)
    assert restored.id == original.id
    assert restored.title == original.title
    assert restored.category == original.category
    assert restored.ideation_mode == original.ideation_mode
    assert restored.inspiring_insights == original.inspiring_insights
    assert restored.evidence_signals == original.evidence_signals
    assert restored.source_idea_ids == original.source_idea_ids
    assert restored.tech_approach == original.tech_approach
    assert restored.suggested_stack == original.suggested_stack
    assert restored.domain == original.domain
    assert restored.prior_art_status == original.prior_art_status
    assert restored.status == original.status


def test_buildable_unit_datetime_serialization() -> None:
    """Test that datetime fields are properly serialized."""
    created = datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
    unit = BuildableUnit(
        title="DateTime Test",
        one_liner="Testing datetime handling",
        category="library",
        problem="Time tracking",
        solution="Use datetime",
        value_proposition="Accurate timestamps",
        created_at=created,
        updated_at=created,
    )

    json_str = unit.model_dump_json()
    parsed = json.loads(json_str)

    # Pydantic serializes datetime to ISO format string
    assert "2024-03-15" in parsed["created_at"]
    assert "2024-03-15" in parsed["updated_at"]

    # Deserialize and verify datetime objects
    restored = BuildableUnit.model_validate_json(json_str)
    assert restored.created_at == created
    assert restored.updated_at == created


def test_buildable_unit_equality() -> None:
    """Test BuildableUnit equality comparison."""
    unit1 = BuildableUnit(
        id="bu-equal",
        title="Equality Test",
        one_liner="Testing equality",
        category="library",
        problem="Comparison",
        solution="Implement equals",
        value_proposition="Proper comparison",
    )

    unit2 = BuildableUnit(
        id="bu-equal",
        title="Equality Test",
        one_liner="Testing equality",
        category="library",
        problem="Comparison",
        solution="Implement equals",
        value_proposition="Proper comparison",
    )

    # Pydantic models don't implement __eq__ for structural equality by default
    # They use object identity unless configured otherwise
    assert unit1 != unit2  # Different instances

    # Same instance is equal to itself
    assert unit1 == unit1


def test_buildable_unit_model_copy() -> None:
    """Test BuildableUnit can be copied with modifications."""
    original = BuildableUnit(
        id="bu-original",
        title="Original",
        one_liner="Original unit",
        category="library",
        problem="Original problem",
        solution="Original solution",
        value_proposition="Original value",
        status="draft",
    )

    # Create a copy with modified fields
    updated = original.model_copy(update={"status": "approved", "id": "bu-updated"})

    assert updated.id == "bu-updated"
    assert updated.status == "approved"
    assert updated.title == "Original"  # Unchanged
    assert original.status == "draft"  # Original unchanged


def test_buildable_unit_list_fields_mutability() -> None:
    """Test that list fields are independent between instances."""
    unit1 = BuildableUnit(
        title="Unit 1",
        one_liner="First unit",
        category="library",
        problem="Problem 1",
        solution="Solution 1",
        value_proposition="Value 1",
    )

    unit2 = BuildableUnit(
        title="Unit 2",
        one_liner="Second unit",
        category="library",
        problem="Problem 2",
        solution="Solution 2",
        value_proposition="Value 2",
    )

    # Modify list in unit1
    unit1.inspiring_insights.append("insight-1")

    # unit2 should not be affected
    assert len(unit1.inspiring_insights) == 1
    assert len(unit2.inspiring_insights) == 0


def test_buildable_unit_dict_field_mutability() -> None:
    """Test that dict fields are independent between instances."""
    unit1 = BuildableUnit(
        title="Unit 1",
        one_liner="First unit",
        category="library",
        problem="Problem 1",
        solution="Solution 1",
        value_proposition="Value 1",
    )

    unit2 = BuildableUnit(
        title="Unit 2",
        one_liner="Second unit",
        category="library",
        problem="Problem 2",
        solution="Solution 2",
        value_proposition="Value 2",
    )

    # Modify dict in unit1
    unit1.suggested_stack["language"] = "Python"

    # unit2 should not be affected
    assert unit1.suggested_stack == {"language": "Python"}
    assert unit2.suggested_stack == {}
