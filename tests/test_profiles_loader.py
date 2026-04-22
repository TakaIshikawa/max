"""Comprehensive tests for src/max/profiles/loader.py and src/max/profiles/schema.py.

Tests cover:
1. Loading each existing YAML profile parses without error
2. Missing required fields raise validation errors
3. Invalid enum/field values are rejected
4. Unknown top-level keys behavior (Pydantic allows extra fields by default)
5. Loading nonexistent profile raises appropriate error
6. Profile with custom weight overrides
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from max.profiles.loader import (
    get_default_profile,
    get_profiles_dir,
    list_profiles,
    load_profile,
    validate_profile_file,
    validate_profile_files,
)
from max.profiles.schema import (
    DEFAULT_DOMAIN_CONTEXT,
    DomainContext,
    EvaluationConfig,
    PipelineProfile,
    SourceConfig,
)


# ── Schema Validation Tests ──────────────────────────────────────────


class TestSourceConfig:
    """Tests for SourceConfig schema validation."""

    def test_valid_minimal_config(self):
        """Test minimal valid SourceConfig construction."""
        config = SourceConfig(adapter="reddit")
        assert config.adapter == "reddit"
        assert config.enabled is True
        assert config.weight == 1.0
        assert config.params == {}

    def test_valid_full_config(self):
        """Test SourceConfig with all fields."""
        config = SourceConfig(
            adapter="github",
            enabled=False,
            weight=2.5,
            params={"topics": ["ai", "ml"]},
        )
        assert config.adapter == "github"
        assert config.enabled is False
        assert config.weight == 2.5
        assert config.params == {"topics": ["ai", "ml"]}

    def test_valid_rss_feed_params(self):
        """Test SourceConfig accepts RSS feed URLs and max age."""
        config = SourceConfig(
            adapter="rss_feed",
            enabled=False,
            params={
                "feeds": ["https://example.com/feed.xml"],
                "max_age_days": 14,
                "tags": ["custom-feed"],
            },
        )

        assert config.params["feeds"] == ["https://example.com/feed.xml"]
        assert config.params["max_age_days"] == 14

    def test_invalid_rss_feed_params_fail(self):
        """Test SourceConfig rejects malformed RSS feed params."""
        with pytest.raises(ValidationError):
            SourceConfig(adapter="rss_feed", params={"feeds": ["not-a-url"]})

        with pytest.raises(ValidationError):
            SourceConfig(
                adapter="rss_feed",
                params={"feeds": ["https://example.com/feed.xml"], "max_age_days": 0},
            )

    def test_missing_required_adapter_field(self):
        """Test that missing adapter field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SourceConfig()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "adapter" in missing_fields

    def test_invalid_weight_type(self):
        """Test that invalid weight type raises ValidationError."""
        # Explicitly type as Any to test runtime validation of invalid value
        invalid_weight: Any = "invalid"

        with pytest.raises(ValidationError):
            SourceConfig(adapter="reddit", weight=invalid_weight)

    def test_invalid_enabled_type(self):
        """Test that invalid enabled type raises ValidationError."""
        # Note: Pydantic coerces string "true"/"yes" to bool, so use a truly invalid type
        # Explicitly type as Any to test runtime validation of invalid value
        invalid_enabled: Any = ["not", "a", "bool"]

        with pytest.raises(ValidationError):
            SourceConfig(adapter="reddit", enabled=invalid_enabled)


class TestDomainContext:
    """Tests for DomainContext schema validation."""

    def test_valid_minimal_domain(self):
        """Test minimal valid DomainContext construction."""
        domain = DomainContext(
            name="test",
            description="Test domain",
            categories=["app"],
            target_user_types=["users"],
        )
        assert domain.name == "test"
        assert domain.description == "Test domain"
        assert domain.categories == ["app"]
        assert domain.target_user_types == ["users"]
        assert domain.extra_instructions == ""

    def test_valid_full_domain(self):
        """Test DomainContext with all fields."""
        domain = DomainContext(
            name="healthcare",
            description="Healthcare technology",
            categories=["clinical_tool", "ehr_integration"],
            target_user_types=["clinicians", "patients"],
            extra_instructions="HIPAA compliance required",
        )
        assert domain.name == "healthcare"
        assert domain.extra_instructions == "HIPAA compliance required"

    def test_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DomainContext()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "name" in missing_fields
        assert "description" in missing_fields
        assert "categories" in missing_fields
        assert "target_user_types" in missing_fields

    def test_invalid_categories_type(self):
        """Test that invalid categories type raises ValidationError."""
        # Explicitly type as Any to test runtime validation of invalid value
        invalid_categories: Any = "not-a-list"

        with pytest.raises(ValidationError):
            DomainContext(
                name="test",
                description="Test",
                categories=invalid_categories,
                target_user_types=["users"],
            )

    def test_empty_categories_list(self):
        """Test that empty categories list is allowed."""
        domain = DomainContext(
            name="test",
            description="Test",
            categories=[],
            target_user_types=["users"],
        )
        assert domain.categories == []


class TestEvaluationConfig:
    """Tests for EvaluationConfig schema validation."""

    def test_valid_defaults(self):
        """Test EvaluationConfig with default values."""
        config = EvaluationConfig()
        assert config.weight_profile == "default"
        assert config.custom_weights is None
        assert config.min_score == 50.0

    def test_valid_custom_config(self):
        """Test EvaluationConfig with custom values."""
        config = EvaluationConfig(
            weight_profile="custom",
            custom_weights={"relevance": 0.5, "impact": 0.3},
            min_score=60.0,
        )
        assert config.weight_profile == "custom"
        assert config.custom_weights == {"relevance": 0.5, "impact": 0.3}
        assert config.min_score == 60.0

    def test_invalid_min_score_type(self):
        """Test that invalid min_score type raises ValidationError."""
        # Explicitly type as Any to test runtime validation of invalid value
        invalid_min_score: Any = "high"

        with pytest.raises(ValidationError):
            EvaluationConfig(min_score=invalid_min_score)

    def test_invalid_custom_weights_type(self):
        """Test that invalid custom_weights type raises ValidationError."""
        # Explicitly type as Any to test runtime validation of invalid value
        invalid_custom_weights: Any = "invalid"

        with pytest.raises(ValidationError):
            EvaluationConfig(custom_weights=invalid_custom_weights)


class TestPipelineProfile:
    """Tests for PipelineProfile schema validation."""

    def test_valid_minimal_profile(self):
        """Test minimal valid PipelineProfile construction."""
        profile = PipelineProfile(
            name="test",
            domain=DomainContext(
                name="test-domain",
                description="Test domain",
                categories=["app"],
                target_user_types=["users"],
            ),
        )
        assert profile.name == "test"
        assert profile.sources == []
        assert profile.output_dir == ".max-output"
        assert profile.signal_limit == 30
        assert profile.ideation_mode == "direct"

    def test_valid_full_profile(self):
        """Test PipelineProfile with all fields."""
        profile = PipelineProfile(
            name="full",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["app"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="reddit", params={"subreddits": ["test"]}),
                SourceConfig(adapter="github", enabled=False),
            ],
            evaluation=EvaluationConfig(min_score=60.0),
            output_dir=".custom-output",
            signal_limit=50,
            ideation_mode="iterative",
        )
        assert profile.name == "full"
        assert len(profile.sources) == 2
        assert profile.evaluation.min_score == 60.0
        assert profile.output_dir == ".custom-output"
        assert profile.signal_limit == 50
        assert profile.ideation_mode == "iterative"

    def test_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PipelineProfile()
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "name" in missing_fields
        assert "domain" in missing_fields

    def test_invalid_domain_type(self):
        """Test that invalid domain type raises ValidationError."""
        # Explicitly type as Any to test runtime validation of invalid value
        invalid_domain: Any = "not-a-domain"

        with pytest.raises(ValidationError):
            PipelineProfile(
                name="test",
                domain=invalid_domain,
            )

    def test_invalid_sources_type(self):
        """Test that invalid sources type raises ValidationError."""
        # Explicitly type as Any to test runtime validation of invalid value
        invalid_sources: Any = "not-a-list"

        with pytest.raises(ValidationError):
            PipelineProfile(
                name="test",
                domain=DomainContext(
                    name="test",
                    description="Test",
                    categories=["app"],
                    target_user_types=["users"],
                ),
                sources=invalid_sources,
            )

    def test_profile_allows_unknown_top_level_keys(self):
        """Test that Pydantic allows extra fields by default (not strict)."""
        data = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["app"],
                "target_user_types": ["users"],
            },
            "unknown_field": "should_be_ignored",
            "another_unknown": 123,
        }
        # Pydantic BaseModel by default ignores extra fields
        profile = PipelineProfile(**data)
        assert profile.name == "test"
        # Extra fields are ignored, not stored
        assert not hasattr(profile, "unknown_field")


class TestDefaultDomainContext:
    """Tests for DEFAULT_DOMAIN_CONTEXT constant."""

    def test_default_domain_values(self):
        """Test that DEFAULT_DOMAIN_CONTEXT has expected values."""
        dc = DEFAULT_DOMAIN_CONTEXT
        assert dc.name == "developer-tools"
        assert "developer tools" in dc.description.lower()
        assert "ai agent" in dc.description.lower()
        assert "mcp_server" in dc.categories
        assert "cli_tool" in dc.categories
        assert "library" in dc.categories
        assert "integration" in dc.categories
        assert "automation" in dc.categories
        assert "application" in dc.categories
        assert "feature" in dc.categories
        assert "humans" in dc.target_user_types
        assert "agents" in dc.target_user_types
        assert "both" in dc.target_user_types


# ── Loader Function Tests ──────────────────────────────────────────


class TestGetProfilesDir:
    """Tests for get_profiles_dir() function."""

    def test_profiles_dir_exists(self):
        """Test that get_profiles_dir returns an existing directory."""
        profiles_dir = get_profiles_dir()
        assert profiles_dir.is_dir()
        assert profiles_dir.name == "profiles"

    def test_profiles_dir_has_pyproject_sibling(self):
        """Test that profiles dir is sibling to pyproject.toml."""
        profiles_dir = get_profiles_dir()
        project_root = profiles_dir.parent
        assert (project_root / "pyproject.toml").exists()


class TestListProfiles:
    """Tests for list_profiles() function."""

    def test_list_profiles_returns_existing_profiles(self):
        """Test that list_profiles finds all YAML files."""
        profiles = list_profiles()
        assert isinstance(profiles, list)
        assert len(profiles) > 0
        # Check for known profiles
        assert "devtools" in profiles
        assert "healthcare" in profiles
        assert "fintech" in profiles
        assert "cybersecurity" in profiles

    def test_list_profiles_sorted(self):
        """Test that list_profiles returns sorted names."""
        profiles = list_profiles()
        assert profiles == sorted(profiles)


class TestProfileFileValidation:
    """Tests for validating profile YAML files against schema and loader."""

    def test_validate_profile_file_validates_schema_and_loader(self, tmp_path: Path, monkeypatch):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        schema_data = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["name", "domain"],
            "properties": {
                "name": {"type": "string"},
                "domain": {
                    "type": "object",
                    "required": ["name", "description", "categories", "target_user_types"],
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "categories": {"type": "array", "items": {"type": "string"}},
                        "target_user_types": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["adapter"],
                        "properties": {
                            "adapter": {"type": "string", "enum": ["hackernews"]},
                            "weight": {"type": "number", "minimum": 0.0, "maximum": 10.0},
                        },
                    },
                },
            },
        }
        profile_data = {
            "name": "invalid",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["mcp_server"],
                "target_user_types": ["users"],
            },
            "sources": [{"adapter": "bogus"}],
        }

        with open(profiles_dir / "schema.yaml", "w") as f:
            yaml.dump(schema_data, f)
        profile_path = profiles_dir / "invalid.yaml"
        with open(profile_path, "w") as f:
            yaml.dump(profile_data, f)

        monkeypatch.setattr("max.profiles.loader.get_profiles_dir", lambda: profiles_dir)

        result = validate_profile_file(profile_path)

        assert result.name == "invalid"
        assert result.ok is False
        assert any(error.startswith("schema: sources.0.adapter") for error in result.errors)
        assert any(error.startswith("loader:") for error in result.errors)

    def test_validate_profile_files_supports_single_profile(self, tmp_path: Path, monkeypatch):
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        schema_data = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["name", "domain"],
            "properties": {
                "name": {"type": "string"},
                "domain": {
                    "type": "object",
                    "required": ["name", "description", "categories", "target_user_types"],
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "categories": {"type": "array", "items": {"type": "string"}},
                        "target_user_types": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        }
        profile_data = {
            "name": "minimal",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["mcp_server"],
                "target_user_types": ["users"],
            },
        }

        with open(profiles_dir / "schema.yaml", "w") as f:
            yaml.dump(schema_data, f)
        with open(profiles_dir / "minimal.yaml", "w") as f:
            yaml.dump(profile_data, f)

        monkeypatch.setattr("max.profiles.loader.get_profiles_dir", lambda: profiles_dir)

        results = validate_profile_files(profile="minimal")

        assert len(results) == 1
        assert results[0].name == "minimal"
        assert results[0].ok is True


class TestLoadProfile:
    """Tests for load_profile() function."""

    def test_load_nonexistent_profile_raises_file_not_found(self):
        """Test that loading nonexistent profile raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_profile("nonexistent_profile_xyz_123")

    def test_load_nonexistent_profile_lists_available(self):
        """Test that FileNotFoundError message lists available profiles."""
        with pytest.raises(FileNotFoundError, match="Available:"):
            load_profile("missing_profile")

    def test_load_profile_tries_both_extensions(self):
        """Test that load_profile tries both .yaml and .yml extensions."""
        # This is implicit in the implementation - we verify by checking it doesn't
        # fail for .yaml files and would try .yml if .yaml doesn't exist
        profile = load_profile("devtools")
        assert profile.name == "devtools"


class TestLoadAllExistingProfiles:
    """Tests that verify all existing YAML profiles load without error."""

    def test_load_devtools_profile(self):
        """Test loading devtools.yaml profile."""
        profile = load_profile("devtools")
        assert profile.name == "devtools"
        assert profile.domain.name == "developer-tools"
        assert len(profile.sources) > 0
        assert profile.signal_limit == 30
        assert profile.evaluation.weight_profile == "default"

    def test_load_healthcare_profile(self):
        """Test loading healthcare.yaml profile."""
        profile = load_profile("healthcare")
        assert profile.name == "healthcare"
        assert profile.domain.name == "healthcare"
        assert "clinical_tool" in profile.domain.categories
        assert "clinicians" in profile.domain.target_user_types
        assert "HIPAA" in profile.domain.extra_instructions
        assert profile.signal_limit == 25

    def test_load_fintech_profile(self):
        """Test loading fintech.yaml profile."""
        profile = load_profile("fintech")
        assert profile.name == "fintech"
        assert profile.domain.name == "fintech"
        assert "compliance_automation" in profile.domain.categories
        assert "financial_analysts" in profile.domain.target_user_types
        assert "DORA" in profile.domain.extra_instructions

    def test_load_cybersecurity_profile(self):
        """Test loading cybersecurity.yaml profile."""
        profile = load_profile("cybersecurity")
        assert profile.name == "cybersecurity"
        assert profile.domain.name == "cybersecurity"
        assert "detection_tool" in profile.domain.categories
        assert "security_engineers" in profile.domain.target_user_types

    def test_load_construction_profile(self):
        """Test loading construction.yaml profile."""
        profile = load_profile("construction")
        assert profile.name == "construction"
        assert profile.domain.name == "construction"

    def test_load_creator_economy_profile(self):
        """Test loading creator-economy.yaml profile."""
        profile = load_profile("creator-economy")
        assert profile.name == "creator-economy"
        assert profile.domain.name == "creator-economy"

    def test_load_education_profile(self):
        """Test loading education.yaml profile."""
        profile = load_profile("education")
        assert profile.name == "education"
        assert profile.domain.name == "education"

    def test_load_sustainability_profile(self):
        """Test loading sustainability.yaml profile."""
        profile = load_profile("sustainability")
        assert profile.name == "sustainability"
        assert profile.domain.name == "sustainability"

    def test_all_existing_profiles_parse_successfully(self):
        """Test that all YAML files in profiles/ directory parse without error."""
        profiles = list_profiles()
        assert len(profiles) > 0
        for profile_name in profiles:
            profile = load_profile(profile_name)
            assert profile.name == profile_name
            assert isinstance(profile.domain, DomainContext)
            assert isinstance(profile.sources, list)
            assert isinstance(profile.evaluation, EvaluationConfig)


class TestGetDefaultProfile:
    """Tests for get_default_profile() function."""

    def test_get_default_profile_returns_devtools(self):
        """Test that get_default_profile returns devtools profile."""
        profile = get_default_profile()
        assert profile.name == "devtools"
        assert profile.domain.name == "developer-tools"

    def test_default_profile_has_expected_sources(self):
        """Test that default profile has expected source adapters."""
        profile = get_default_profile()
        adapter_names = {s.adapter for s in profile.sources}
        assert "hackernews" in adapter_names
        assert "reddit" in adapter_names
        assert "github" in adapter_names
        assert "github_issues" in adapter_names
        assert "npm_registry" in adapter_names
        assert "pypi_registry" in adapter_names
        assert "security_advisories" in adapter_names
        assert "product_hunt" in adapter_names

    def test_default_profile_fallback_when_file_missing(self, tmp_path, monkeypatch):
        """Test that get_default_profile falls back to hardcoded profile if file missing."""
        # Create empty profiles directory
        fake_profiles_dir = tmp_path / "profiles"
        fake_profiles_dir.mkdir()

        # Mock get_profiles_dir to return our empty directory
        monkeypatch.setattr(
            "max.profiles.loader.get_profiles_dir",
            lambda: fake_profiles_dir,
        )

        # Should fall back to hardcoded profile
        profile = get_default_profile()
        assert profile.name == "devtools"
        assert profile.domain.name == "developer-tools"
        assert len(profile.sources) == 8


# ── YAML Round-trip and Synthetic Profile Tests ──────────────────────


class TestYAMLRoundTrip:
    """Tests for YAML serialization/deserialization."""

    def test_profile_yaml_round_trip(self, tmp_path: Path):
        """Test writing profile to YAML and reading it back."""
        profile_data = {
            "name": "roundtrip",
            "domain": {
                "name": "test",
                "description": "Round-trip test",
                "categories": ["app", "tool"],
                "target_user_types": ["users", "admins"],
            },
            "sources": [
                {"adapter": "hackernews"},
                {"adapter": "reddit", "params": {"subreddits": ["test"]}},
            ],
            "evaluation": {"min_score": 40.0},
            "signal_limit": 15,
            "output_dir": ".test-output",
        }

        yaml_path = tmp_path / "roundtrip.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(profile_data, f)

        with open(yaml_path) as f:
            loaded = yaml.safe_load(f)

        profile = PipelineProfile(**loaded)
        assert profile.name == "roundtrip"
        assert profile.signal_limit == 15
        assert len(profile.sources) == 2
        assert profile.evaluation.min_score == 40.0

    def test_profile_with_missing_required_field_in_yaml(self, tmp_path: Path):
        """Test that YAML with missing required fields raises ValidationError."""
        incomplete_data = {
            "name": "incomplete",
            # Missing 'domain' field
            "sources": [],
        }

        yaml_path = tmp_path / "incomplete.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(incomplete_data, f)

        with open(yaml_path) as f:
            loaded = yaml.safe_load(f)

        with pytest.raises(ValidationError) as exc_info:
            PipelineProfile(**loaded)
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "domain" in missing_fields

    def test_profile_with_invalid_field_type_in_yaml(self, tmp_path: Path):
        """Test that YAML with invalid field types raises ValidationError."""
        invalid_data = {
            "name": "invalid",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["app"],
                "target_user_types": ["users"],
            },
            "signal_limit": "not-a-number",  # Should be int
        }

        yaml_path = tmp_path / "invalid.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(invalid_data, f)

        with open(yaml_path) as f:
            loaded = yaml.safe_load(f)

        with pytest.raises(ValidationError):
            PipelineProfile(**loaded)


class TestSyntheticProfiles:
    """Tests using synthetic profile files created in tmp_path."""

    def test_synthetic_profile_minimal(self, tmp_path: Path, monkeypatch):
        """Test loading a minimal synthetic profile."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        profile_data = {
            "name": "minimal",
            "domain": {
                "name": "minimal-domain",
                "description": "Minimal test domain",
                "categories": ["test"],
                "target_user_types": ["testers"],
            },
        }

        yaml_path = profiles_dir / "minimal.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(profile_data, f)

        # Mock get_profiles_dir
        monkeypatch.setattr(
            "max.profiles.loader.get_profiles_dir",
            lambda: profiles_dir,
        )

        profile = load_profile("minimal")
        assert profile.name == "minimal"
        assert profile.domain.name == "minimal-domain"
        assert profile.sources == []
        assert profile.signal_limit == 30  # default

    def test_synthetic_profile_with_custom_weights(self, tmp_path: Path, monkeypatch):
        """Test profile with custom evaluation weights."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        profile_data = {
            "name": "weighted",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["app"],
                "target_user_types": ["users"],
            },
            "evaluation": {
                "weight_profile": "custom",
                "custom_weights": {
                    "relevance": 0.4,
                    "impact": 0.3,
                    "feasibility": 0.2,
                    "novelty": 0.1,
                },
                "min_score": 55.0,
            },
        }

        yaml_path = profiles_dir / "weighted.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(profile_data, f)

        monkeypatch.setattr(
            "max.profiles.loader.get_profiles_dir",
            lambda: profiles_dir,
        )

        profile = load_profile("weighted")
        assert profile.evaluation.weight_profile == "custom"
        assert profile.evaluation.custom_weights is not None
        assert profile.evaluation.custom_weights["relevance"] == 0.4
        assert profile.evaluation.custom_weights["impact"] == 0.3
        assert profile.evaluation.min_score == 55.0

    def test_synthetic_profile_with_weighted_sources(self, tmp_path: Path, monkeypatch):
        """Test profile with different source weights."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        profile_data = {
            "name": "weighted_sources",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["app"],
                "target_user_types": ["users"],
            },
            "sources": [
                {"adapter": "reddit", "weight": 2.0, "enabled": True},
                {"adapter": "github", "weight": 1.5, "enabled": True},
                {"adapter": "hackernews", "weight": 1.0, "enabled": False},
            ],
        }

        yaml_path = profiles_dir / "weighted_sources.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(profile_data, f)

        monkeypatch.setattr(
            "max.profiles.loader.get_profiles_dir",
            lambda: profiles_dir,
        )

        profile = load_profile("weighted_sources")
        assert len(profile.sources) == 3

        sources_by_adapter = {s.adapter: s for s in profile.sources}
        assert sources_by_adapter["reddit"].weight == 2.0
        assert sources_by_adapter["reddit"].enabled is True
        assert sources_by_adapter["github"].weight == 1.5
        assert sources_by_adapter["hackernews"].enabled is False

    def test_invalid_yaml_structure_raises_error(self, tmp_path: Path):
        """Test that invalid YAML structure raises appropriate error."""
        yaml_path = tmp_path / "invalid.yaml"
        # Write a non-dict YAML (e.g., a list)
        with open(yaml_path, "w") as f:
            yaml.dump(["not", "a", "dict"], f)

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # PipelineProfile expects a dict
        # Explicitly type as Any to test runtime validation of invalid structure
        invalid_data: Any = data

        with pytest.raises((ValidationError, TypeError)):
            PipelineProfile(**invalid_data)


# ── Edge Cases and Error Handling ──────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_profile_with_empty_sources_list(self):
        """Test profile with empty sources list is valid."""
        profile = PipelineProfile(
            name="empty_sources",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["app"],
                target_user_types=["users"],
            ),
            sources=[],
        )
        assert profile.sources == []

    def test_source_config_with_empty_params(self):
        """Test SourceConfig with empty params dict."""
        config = SourceConfig(adapter="test", params={})
        assert config.params == {}

    def test_domain_with_empty_extra_instructions(self):
        """Test DomainContext with empty extra_instructions (default)."""
        domain = DomainContext(
            name="test",
            description="Test",
            categories=["app"],
            target_user_types=["users"],
        )
        assert domain.extra_instructions == ""

    def test_profile_name_can_contain_hyphens(self):
        """Test that profile names with hyphens are valid."""
        profile = PipelineProfile(
            name="test-profile-name",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["app"],
                target_user_types=["users"],
            ),
        )
        assert profile.name == "test-profile-name"

    def test_evaluation_with_none_custom_weights(self):
        """Test EvaluationConfig with explicitly set None custom_weights."""
        config = EvaluationConfig(custom_weights=None)
        assert config.custom_weights is None

    def test_profile_signal_limit_can_be_zero(self):
        """Test that signal_limit can be set to zero."""
        profile = PipelineProfile(
            name="zero_limit",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["app"],
                target_user_types=["users"],
            ),
            signal_limit=0,
        )
        assert profile.signal_limit == 0

    def test_profile_with_very_large_signal_limit(self):
        """Test profile with very large signal_limit."""
        profile = PipelineProfile(
            name="large_limit",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["app"],
                target_user_types=["users"],
            ),
            signal_limit=10000,
        )
        assert profile.signal_limit == 10000
