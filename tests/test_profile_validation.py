"""Comprehensive tests for profile validation in src/max/profiles/loader.py.

Tests cover:
1. Valid profiles pass validation
2. Unknown adapter names fail with appropriate error
3. Out-of-range weight values fail with appropriate error
4. Unknown categories generate warnings (but don't fail)
5. Multiple validation errors are reported together
6. Edge cases for weight validation (0.0, 10.0, negative, etc.)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from max.profiles.loader import (
    ProfileValidationError,
    load_profile,
    validate_profile,
)
from max.profiles.schema import (
    DomainContext,
    PipelineProfile,
    SourceConfig,
)


# ── Valid Profile Tests ────────────────────────────────────────────────


class TestValidProfiles:
    """Tests that valid profiles pass validation."""

    def test_valid_profile_passes_validation(self):
        """Test that a valid profile passes all validation checks."""
        profile = PipelineProfile(
            name="test",
            domain=DomainContext(
                name="test-domain",
                description="Test domain",
                categories=["mcp_server", "cli_tool"],  # known categories
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="hackernews", weight=1.0),
                SourceConfig(adapter="reddit", weight=2.5),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews", "reddit"]):
            issues = validate_profile(profile)

        # Should have no errors, only potential warnings about categories
        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 0

    def test_profile_with_all_default_weights(self):
        """Test profile with default weight values (1.0)."""
        profile = PipelineProfile(
            name="defaults",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["library"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="github"),  # default weight=1.0
                SourceConfig(adapter="npm_registry"),  # default weight=1.0
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["github", "npm_registry"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 0

    def test_profile_with_zero_weight(self):
        """Test that weight of 0.0 is valid."""
        profile = PipelineProfile(
            name="zero-weight",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["application"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="hackernews", weight=0.0),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 0

    def test_profile_with_max_weight(self):
        """Test that weight of 10.0 is valid."""
        profile = PipelineProfile(
            name="max-weight",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["feature"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="reddit", weight=10.0),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["reddit"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 0


# ── Unknown Adapter Tests ──────────────────────────────────────────────


class TestUnknownAdapters:
    """Tests for validation of adapter names."""

    def test_unknown_adapter_fails_validation(self):
        """Test that unknown adapter name raises error."""
        profile = PipelineProfile(
            name="bad-adapter",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["mcp_server"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="nonexistent_adapter", weight=1.0),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews", "reddit"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 1
        assert "Unknown adapter 'nonexistent_adapter'" in errors[0]
        assert "hackernews" in errors[0]
        assert "reddit" in errors[0]

    def test_multiple_unknown_adapters(self):
        """Test that multiple unknown adapters are all reported."""
        profile = PipelineProfile(
            name="multiple-bad",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["cli_tool"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="fake_adapter_1"),
                SourceConfig(adapter="fake_adapter_2"),
                SourceConfig(adapter="hackernews"),  # valid
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 2
        assert any("fake_adapter_1" in e for e in errors)
        assert any("fake_adapter_2" in e for e in errors)

    def test_load_profile_with_unknown_adapter_raises_exception(self, tmp_path: Path):
        """Test that loading a profile with unknown adapter raises ProfileValidationError."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        profile_data = {
            "name": "invalid",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["library"],
                "target_user_types": ["users"],
            },
            "sources": [
                {"adapter": "unknown_adapter"},
            ],
        }

        yaml_path = profiles_dir / "invalid.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(profile_data, f)

        with patch("max.profiles.loader.get_profiles_dir", return_value=profiles_dir):
            with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
                with pytest.raises(ProfileValidationError) as exc_info:
                    load_profile("invalid")

                assert "Unknown adapter 'unknown_adapter'" in str(exc_info.value)
                assert exc_info.value.issues[0] == "Unknown adapter 'unknown_adapter'. Available adapters: ['hackernews']"


# ── Weight Validation Tests ────────────────────────────────────────────


class TestWeightValidation:
    """Tests for weight value validation."""

    def test_negative_weight_fails_validation(self):
        """Test that negative weight values fail validation."""
        profile = PipelineProfile(
            name="negative-weight",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["automation"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="hackernews", weight=-1.0),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 1
        assert "Weight -1.0" in errors[0]
        assert "hackernews" in errors[0]
        assert "out of range" in errors[0]

    def test_weight_above_max_fails_validation(self):
        """Test that weight > 10.0 fails validation."""
        profile = PipelineProfile(
            name="high-weight",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["integration"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="reddit", weight=10.5),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["reddit"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 1
        assert "Weight 10.5" in errors[0]
        assert "reddit" in errors[0]
        assert "out of range" in errors[0]

    def test_extremely_high_weight_fails(self):
        """Test that extremely high weight values fail."""
        profile = PipelineProfile(
            name="extreme",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["application"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="github", weight=1000.0),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["github"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 1
        assert "Weight 1000.0" in errors[0]

    def test_load_profile_with_invalid_weight_raises_exception(self, tmp_path: Path):
        """Test that loading profile with invalid weight raises ProfileValidationError."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        profile_data = {
            "name": "bad-weight",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["feature"],
                "target_user_types": ["users"],
            },
            "sources": [
                {"adapter": "hackernews", "weight": 15.0},
            ],
        }

        yaml_path = profiles_dir / "bad-weight.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(profile_data, f)

        with patch("max.profiles.loader.get_profiles_dir", return_value=profiles_dir):
            with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
                with pytest.raises(ProfileValidationError) as exc_info:
                    load_profile("bad-weight")

                assert "Weight 15.0" in str(exc_info.value)
                assert "out of range" in str(exc_info.value)


# ── Category Validation Tests ──────────────────────────────────────────


class TestCategoryValidation:
    """Tests for category name validation (warnings only)."""

    def test_unknown_category_generates_warning(self):
        """Test that unknown categories generate warnings but don't fail."""
        profile = PipelineProfile(
            name="unknown-cat",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["totally_unknown_category"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="hackernews"),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        # Should have warning, not error
        errors = [i for i in issues if i.startswith("ERROR:")]
        warnings = [i for i in issues if i.startswith("WARNING:")]

        assert len(errors) == 0
        assert len(warnings) == 1
        assert "totally_unknown_category" in warnings[0]

    def test_known_categories_pass_without_warning(self):
        """Test that known categories don't generate warnings."""
        profile = PipelineProfile(
            name="known-cats",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["mcp_server", "cli_tool", "library"],  # all known
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="hackernews"),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        warnings = [i for i in issues if i.startswith("WARNING:")]
        assert len(warnings) == 0

    def test_mixed_known_and_unknown_categories(self):
        """Test profile with both known and unknown categories."""
        profile = PipelineProfile(
            name="mixed",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["mcp_server", "custom_category", "cli_tool", "another_custom"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="reddit"),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["reddit"]):
            issues = validate_profile(profile)

        warnings = [i for i in issues if i.startswith("WARNING:")]
        assert len(warnings) == 1
        # Should only mention unknown categories
        assert "custom_category" in warnings[0]
        assert "another_custom" in warnings[0]
        # Should not mention known categories
        assert "mcp_server" not in warnings[0]
        assert "cli_tool" not in warnings[0]

    def test_load_profile_with_unknown_category_succeeds_with_warning(self, tmp_path: Path, caplog):
        """Test that profiles with unknown categories load successfully (with warning)."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        profile_data = {
            "name": "unknown-cat",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["custom_category"],
                "target_user_types": ["users"],
            },
            "sources": [
                {"adapter": "hackernews"},
            ],
        }

        yaml_path = profiles_dir / "unknown-cat.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(profile_data, f)

        with patch("max.profiles.loader.get_profiles_dir", return_value=profiles_dir):
            with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
                # Should not raise - warnings are logged, not errors
                profile = load_profile("unknown-cat")
                assert profile.name == "unknown-cat"

                # Check that warning was logged
                assert any("custom_category" in record.message for record in caplog.records)


# ── Multiple Errors Tests ──────────────────────────────────────────────


class TestMultipleErrors:
    """Tests for reporting multiple validation errors together."""

    def test_multiple_errors_reported_together(self):
        """Test that all validation errors are reported together."""
        profile = PipelineProfile(
            name="multiple-errors",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["application"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="unknown_adapter_1", weight=-1.0),
                SourceConfig(adapter="unknown_adapter_2", weight=15.0),
                SourceConfig(adapter="hackernews", weight=20.0),  # known adapter, bad weight
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        # Should have: 2 unknown adapters + 3 bad weights = 5 errors
        assert len(errors) == 5

        # Check that all issues are present
        assert any("unknown_adapter_1" in e and "Unknown adapter" in e for e in errors)
        assert any("unknown_adapter_2" in e and "Unknown adapter" in e for e in errors)
        assert any("Weight -1.0" in e for e in errors)
        assert any("Weight 15.0" in e for e in errors)
        assert any("Weight 20.0" in e for e in errors)

    def test_multiple_errors_in_exception_message(self, tmp_path: Path):
        """Test that ProfileValidationError message includes all errors."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        profile_data = {
            "name": "multi-error",
            "domain": {
                "name": "test",
                "description": "Test",
                "categories": ["library"],
                "target_user_types": ["users"],
            },
            "sources": [
                {"adapter": "fake_adapter", "weight": -5.0},
            ],
        }

        yaml_path = profiles_dir / "multi-error.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(profile_data, f)

        with patch("max.profiles.loader.get_profiles_dir", return_value=profiles_dir):
            with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
                with pytest.raises(ProfileValidationError) as exc_info:
                    load_profile("multi-error")

                # Should mention multiple errors
                error_msg = str(exc_info.value)
                assert "2 errors" in error_msg
                assert "fake_adapter" in error_msg
                assert "Weight -5.0" in error_msg


# ── Edge Cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases in validation."""

    def test_empty_sources_list_passes(self):
        """Test that profile with no sources passes validation."""
        profile = PipelineProfile(
            name="no-sources",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["integration"],
                target_user_types=["users"],
            ),
            sources=[],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 0

    def test_integer_weight_is_valid(self):
        """Test that integer weights are accepted (not just floats)."""
        profile = PipelineProfile(
            name="int-weight",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["feature"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="hackernews", weight=5),  # int, not float
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 0

    def test_registry_loading_failure_is_handled(self):
        """Test that validation handles registry loading failures gracefully."""
        profile = PipelineProfile(
            name="registry-fail",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["automation"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="hackernews"),
            ],
        )

        # Simulate registry failure
        with patch("max.sources.registry.list_adapters", side_effect=RuntimeError("Registry error")):
            issues = validate_profile(profile)

        # Should report adapter as unknown (since registry failed)
        errors = [i for i in issues if i.startswith("ERROR:")]
        assert len(errors) == 1
        assert "hackernews" in errors[0]

    def test_disabled_source_is_still_validated(self):
        """Test that disabled sources are still validated."""
        profile = PipelineProfile(
            name="disabled",
            domain=DomainContext(
                name="test",
                description="Test",
                categories=["application"],
                target_user_types=["users"],
            ),
            sources=[
                SourceConfig(adapter="fake_adapter", enabled=False, weight=50.0),
            ],
        )

        with patch("max.sources.registry.list_adapters", return_value=["hackernews"]):
            issues = validate_profile(profile)

        errors = [i for i in issues if i.startswith("ERROR:")]
        # Should still report errors for disabled sources
        assert len(errors) == 2  # unknown adapter + bad weight
        assert any("fake_adapter" in e for e in errors)
        assert any("Weight 50.0" in e for e in errors)


# ── Integration Tests ──────────────────────────────────────────────────


class TestRealProfilesValidation:
    """Integration tests with real profile files."""

    def test_existing_profiles_pass_validation(self):
        """Test that all existing profile files pass validation."""
        # This test verifies backward compatibility
        from max.profiles.loader import list_profiles

        profiles = list_profiles()
        assert len(profiles) > 0

        for profile_name in profiles:
            # Should not raise
            profile = load_profile(profile_name)
            assert profile.name == profile_name
