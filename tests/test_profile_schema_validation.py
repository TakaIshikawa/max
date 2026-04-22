"""JSON Schema validation tests for all profile YAML files.

This test suite validates that all YAML profile files conform to the
JSON Schema defined in profiles/schema.yaml.

Coverage:
1. Schema file itself is valid JSON Schema
2. All profile YAML files validate against the schema
3. Schema correctly documents required fields
4. Schema correctly documents type constraints
5. Schema correctly documents enum constraints
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator, ValidationError


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def schema_path() -> Path:
    """Path to profiles/schema.yaml."""
    # Walk up from tests/ to find project root
    current = Path(__file__).resolve().parent.parent
    return current / "profiles" / "schema.yaml"


@pytest.fixture(scope="module")
def schema(schema_path: Path) -> dict:
    """Load and return the JSON Schema from profiles/schema.yaml."""
    with open(schema_path) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def profiles_dir() -> Path:
    """Path to profiles/ directory."""
    current = Path(__file__).resolve().parent.parent
    return current / "profiles"


@pytest.fixture(scope="module")
def profile_files(profiles_dir: Path) -> list[Path]:
    """List of all YAML profile files."""
    # Exclude schema.yaml
    return sorted([f for f in profiles_dir.glob("*.yaml") if f.stem != "schema"])


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft7Validator:
    """Create a JSON Schema validator with format checking enabled."""
    return Draft7Validator(schema, format_checker=Draft7Validator.FORMAT_CHECKER)


# ── Schema Validity Tests ──────────────────────────────────────────────


class TestSchemaValidity:
    """Tests that verify the schema file itself is valid."""

    def test_schema_file_exists(self, schema_path: Path):
        """Test that profiles/schema.yaml exists."""
        assert schema_path.exists(), f"Schema file not found at {schema_path}"

    def test_schema_is_valid_yaml(self, schema: dict):
        """Test that schema.yaml is valid YAML."""
        assert isinstance(schema, dict), "Schema must be a YAML object/dict"

    def test_schema_has_required_metaschema(self, schema: dict):
        """Test that schema declares JSON Schema version."""
        assert "$schema" in schema, "Schema must declare $schema property"
        assert "json-schema.org" in schema["$schema"], "Must be a JSON Schema"

    def test_schema_has_title_and_description(self, schema: dict):
        """Test that schema has title and description."""
        assert "title" in schema, "Schema should have a title"
        assert "description" in schema, "Schema should have a description"
        assert len(schema["description"]) > 0, "Description should not be empty"

    def test_schema_defines_type(self, schema: dict):
        """Test that schema defines root type."""
        assert schema.get("type") == "object", "Root schema type must be 'object'"

    def test_schema_defines_required_fields(self, schema: dict):
        """Test that schema defines required fields."""
        assert "required" in schema, "Schema should define required fields"
        assert isinstance(schema["required"], list), "Required must be a list"
        # At minimum, name and domain should be required
        assert "name" in schema["required"], "'name' should be required"
        assert "domain" in schema["required"], "'domain' should be required"

    def test_schema_defines_properties(self, schema: dict):
        """Test that schema defines properties."""
        assert "properties" in schema, "Schema should define properties"
        assert isinstance(schema["properties"], dict), "Properties must be a dict"

    def test_schema_validator_can_be_created(self, validator: Draft7Validator):
        """Test that a validator can be created from the schema."""
        assert validator is not None
        # Check schema itself is valid according to JSON Schema spec
        Draft7Validator.check_schema(validator.schema)


# ── Property Definition Tests ──────────────────────────────────────────


class TestSchemaProperties:
    """Tests that verify schema properly documents all properties."""

    def test_schema_documents_name_field(self, schema: dict):
        """Test that 'name' field is properly documented."""
        assert "name" in schema["properties"]
        name_prop = schema["properties"]["name"]
        assert name_prop["type"] == "string"
        assert "description" in name_prop

    def test_schema_documents_domain_field(self, schema: dict):
        """Test that 'domain' field is properly documented."""
        assert "domain" in schema["properties"]
        domain_prop = schema["properties"]["domain"]
        assert domain_prop["type"] == "object"
        assert "description" in domain_prop
        assert "required" in domain_prop
        assert "properties" in domain_prop

    def test_schema_documents_domain_subfields(self, schema: dict):
        """Test that domain subfields are documented."""
        domain = schema["properties"]["domain"]
        props = domain["properties"]

        # All required domain fields should be documented
        assert "name" in props
        assert "description" in props
        assert "categories" in props
        assert "target_user_types" in props

        # Check types
        assert props["name"]["type"] == "string"
        assert props["description"]["type"] == "string"
        assert props["categories"]["type"] == "array"
        assert props["target_user_types"]["type"] == "array"

    def test_schema_documents_sources_field(self, schema: dict):
        """Test that 'sources' field is properly documented."""
        assert "sources" in schema["properties"]
        sources_prop = schema["properties"]["sources"]
        assert sources_prop["type"] == "array"
        assert "items" in sources_prop
        assert sources_prop["items"]["type"] == "object"

    def test_schema_documents_source_adapter_enum(self, schema: dict):
        """Test that adapter field has enum constraint."""
        sources = schema["properties"]["sources"]
        adapter_prop = sources["items"]["properties"]["adapter"]

        assert "enum" in adapter_prop, "Adapter should have enum constraint"
        assert isinstance(adapter_prop["enum"], list)
        assert len(adapter_prop["enum"]) > 0

        # Check for known adapters
        known_adapters = [
            "hackernews",
            "reddit",
            "github",
            "github_issues",
            "npm_registry",
            "pypi_registry",
            "security_advisories",
            "product_hunt",
            "rss_feed",
        ]
        for adapter in known_adapters:
            assert (
                adapter in adapter_prop["enum"]
            ), f"Adapter '{adapter}' should be in enum"

    def test_schema_documents_source_weight_constraints(self, schema: dict):
        """Test that weight field has proper constraints."""
        sources = schema["properties"]["sources"]
        weight_prop = sources["items"]["properties"]["weight"]

        assert weight_prop["type"] == "number"
        assert "minimum" in weight_prop
        assert "maximum" in weight_prop
        assert weight_prop["minimum"] == 0.0
        assert weight_prop["maximum"] == 10.0

    def test_schema_documents_source_watchlist(self, schema: dict):
        """Test that source watchlist field is documented."""
        sources = schema["properties"]["sources"]
        watchlist_prop = sources["items"]["properties"]["watchlist"]

        assert watchlist_prop["type"] == "array"
        assert watchlist_prop["items"]["type"] == "string"
        assert watchlist_prop["items"]["minLength"] == 1

    def test_schema_documents_rss_feed_params_shape(self, schema: dict):
        """Test that rss_feed adapter params are documented."""
        source_item = schema["properties"]["sources"]["items"]
        rss_rule = next(
            rule
            for rule in source_item["allOf"]
            if rule["if"]["properties"]["adapter"]["const"] == "rss_feed"
        )
        params = rss_rule["then"]["properties"]["params"]

        assert params["properties"]["feeds"]["type"] == "array"
        assert params["properties"]["feeds"]["items"]["type"] == "string"
        assert params["properties"]["feeds"]["items"]["format"] == "uri"
        assert params["properties"]["max_age_days"]["type"] == "integer"
        assert params["properties"]["max_age_days"]["minimum"] == 1

    def test_schema_documents_evaluation_field(self, schema: dict):
        """Test that 'evaluation' field is properly documented."""
        assert "evaluation" in schema["properties"]
        eval_prop = schema["properties"]["evaluation"]
        assert eval_prop["type"] == "object"
        assert "properties" in eval_prop

    def test_schema_documents_weight_profile_enum(self, schema: dict):
        """Test that weight_profile has enum constraint."""
        evaluation = schema["properties"]["evaluation"]
        weight_profile_prop = evaluation["properties"]["weight_profile"]

        assert "enum" in weight_profile_prop, "weight_profile should have enum"
        # Check for known weight profiles
        known_profiles = ["default", "quick_wins", "moonshots", "ecosystem", "agent_first"]
        for profile in known_profiles:
            assert (
                profile in weight_profile_prop["enum"]
            ), f"Weight profile '{profile}' should be in enum"

    def test_schema_documents_ideation_mode_enum(self, schema: dict):
        """Test that ideation_mode has enum constraint."""
        ideation_prop = schema["properties"]["ideation_mode"]

        assert "enum" in ideation_prop, "ideation_mode should have enum"
        # Check for known ideation modes
        known_modes = ["direct", "refinement", "cross_domain", "synthesis", "cross_synthesis"]
        for mode in known_modes:
            assert mode in ideation_prop["enum"], f"Ideation mode '{mode}' should be in enum"

    def test_schema_documents_signal_limit_constraints(self, schema: dict):
        """Test that signal_limit has proper integer constraints."""
        signal_limit_prop = schema["properties"]["signal_limit"]

        assert signal_limit_prop["type"] == "integer"
        assert "minimum" in signal_limit_prop
        assert signal_limit_prop["minimum"] >= 1

    def test_schema_documents_min_score_constraints(self, schema: dict):
        """Test that min_score has proper constraints."""
        evaluation = schema["properties"]["evaluation"]
        min_score_prop = evaluation["properties"]["min_score"]

        assert min_score_prop["type"] == "number"
        assert "minimum" in min_score_prop
        assert "maximum" in min_score_prop
        assert min_score_prop["minimum"] == 0.0
        assert min_score_prop["maximum"] == 100.0


# ── Profile File Validation Tests ──────────────────────────────────────


class TestProfileFilesValidation:
    """Tests that validate all profile YAML files against the schema."""

    def test_profiles_directory_exists(self, profiles_dir: Path):
        """Test that profiles/ directory exists."""
        assert profiles_dir.exists(), f"Profiles directory not found at {profiles_dir}"
        assert profiles_dir.is_dir(), f"{profiles_dir} is not a directory"

    def test_profile_files_found(self, profile_files: list[Path]):
        """Test that profile YAML files are found."""
        assert len(profile_files) > 0, "No profile files found (excluding schema.yaml)"

    def test_all_profiles_are_valid_yaml(self, profile_files: list[Path]):
        """Test that each profile file is valid YAML."""
        for profile_path in profile_files:
            with open(profile_path) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict), f"{profile_path.name} must be a YAML object/dict"

    def test_all_profiles_validate_against_schema(
        self, profile_files: list[Path], validator: Draft7Validator
    ):
        """Test that each profile file validates against the JSON Schema."""
        validation_errors = {}

        for profile_path in profile_files:
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)

            # Validate and collect all errors
            errors = list(validator.iter_errors(profile_data))

            if errors:
                # Format error messages for readability
                error_messages = []
                for error in errors:
                    path = ".".join(str(p) for p in error.path) if error.path else "root"
                    error_messages.append(f"  - {path}: {error.message}")
                validation_errors[profile_path.name] = error_messages

        if validation_errors:
            error_report = []
            for filename, errors in validation_errors.items():
                error_report.append(f"\n{filename}:")
                error_report.extend(errors)

            pytest.fail(
                f"{len(validation_errors)} profile(s) failed schema validation:"
                + "\n".join(error_report)
            )

    def test_all_profiles_have_required_fields(self, profile_files: list[Path]):
        """Test that each profile has all required fields."""
        for profile_path in profile_files:
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)

            # Required top-level fields
            assert "name" in profile_data, f"{profile_path.name} missing 'name' field"
            assert "domain" in profile_data, f"{profile_path.name} missing 'domain' field"

            # Required domain fields
            domain = profile_data["domain"]
            assert "name" in domain, f"{profile_path.name} domain missing 'name'"
            assert "description" in domain, f"{profile_path.name} domain missing 'description'"
            assert "categories" in domain, f"{profile_path.name} domain missing 'categories'"
            assert (
                "target_user_types" in domain
            ), f"{profile_path.name} domain missing 'target_user_types'"

    def test_all_profile_names_match_filenames(self, profile_files: list[Path]):
        """Test that profile 'name' field matches filename."""
        mismatches = []

        for profile_path in profile_files:
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)

            filename_stem = profile_path.stem
            profile_name = profile_data.get("name", "")

            if profile_name != filename_stem:
                mismatches.append(
                    f"{profile_path.name}: name '{profile_name}' != filename '{filename_stem}'"
                )

        if mismatches:
            pytest.fail(
                f"{len(mismatches)} profile(s) have name/filename mismatches:\n"
                + "\n".join(f"  - {m}" for m in mismatches)
            )


# ── Type Constraint Tests ──────────────────────────────────────────────


class TestTypeConstraints:
    """Tests that verify schema enforces type constraints."""

    def test_invalid_name_type_fails(self, validator: Draft7Validator):
        """Test that non-string name fails validation."""
        invalid_profile = {
            "name": 123,  # Should be string
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["cli_tool"],
                "target_user_types": ["users"],
            },
        }

        errors = list(validator.iter_errors(invalid_profile))
        assert len(errors) > 0
        # Should have error about 'name' type
        assert any(
            "name" in str(error.path) and "type" in error.message.lower() for error in errors
        )

    def test_invalid_weight_type_fails(self, validator: Draft7Validator):
        """Test that non-numeric weight fails validation."""
        invalid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["library"],
                "target_user_types": ["users"],
            },
            "sources": [
                {
                    "adapter": "hackernews",
                    "weight": "high",  # Should be number
                }
            ],
        }

        errors = list(validator.iter_errors(invalid_profile))
        assert len(errors) > 0

    def test_invalid_weight_range_fails(self, validator: Draft7Validator):
        """Test that out-of-range weight fails validation."""
        invalid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["application"],
                "target_user_types": ["users"],
            },
            "sources": [
                {
                    "adapter": "reddit",
                    "weight": 15.0,  # Exceeds maximum of 10.0
                }
            ],
        }

        errors = list(validator.iter_errors(invalid_profile))
        assert len(errors) > 0
        # Should have error about weight maximum
        assert any("maximum" in error.message.lower() for error in errors)

    def test_invalid_signal_limit_type_fails(self, validator: Draft7Validator):
        """Test that non-integer signal_limit fails validation."""
        invalid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["feature"],
                "target_user_types": ["users"],
            },
            "signal_limit": 30.5,  # Should be integer
        }

        errors = list(validator.iter_errors(invalid_profile))
        assert len(errors) > 0

    def test_invalid_categories_type_fails(self, validator: Draft7Validator):
        """Test that non-array categories fails validation."""
        invalid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": "cli_tool",  # Should be array
                "target_user_types": ["users"],
            },
        }

        errors = list(validator.iter_errors(invalid_profile))
        assert len(errors) > 0

    def test_valid_rss_feed_params_pass(self, validator: Draft7Validator):
        """Test that rss_feed accepts feed URL strings and optional max age."""
        valid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["integration"],
                "target_user_types": ["users"],
            },
            "sources": [
                {
                    "adapter": "rss_feed",
                    "enabled": False,
                    "params": {
                        "feeds": ["https://example.com/feed.xml"],
                        "max_age_days": 14,
                    },
                }
            ],
        }

        assert list(validator.iter_errors(valid_profile)) == []

    @pytest.mark.parametrize(
        "params",
        [
            {"feeds": "https://example.com/feed.xml"},
            {"feeds": ["not-a-url"]},
            {"feeds": ["ftp://example.com/feed.xml"]},
            {"feeds": ["https://example.com/feed.xml"], "max_age_days": 0},
            {"feeds": ["https://example.com/feed.xml"], "max_age_days": "14"},
        ],
    )
    def test_invalid_rss_feed_params_fail(self, validator: Draft7Validator, params: dict):
        """Test that malformed rss_feed params fail validation."""
        invalid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["integration"],
                "target_user_types": ["users"],
            },
            "sources": [
                {
                    "adapter": "rss_feed",
                    "params": params,
                }
            ],
        }

        assert list(validator.iter_errors(invalid_profile))


# ── Enum Constraint Tests ──────────────────────────────────────────────


class TestEnumConstraints:
    """Tests that verify schema enforces enum constraints."""

    def test_invalid_adapter_name_fails(self, validator: Draft7Validator):
        """Test that unknown adapter name fails validation."""
        invalid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["integration"],
                "target_user_types": ["users"],
            },
            "sources": [
                {
                    "adapter": "nonexistent_adapter",  # Not in enum
                }
            ],
        }

        errors = list(validator.iter_errors(invalid_profile))
        assert len(errors) > 0
        # Should have error about enum (message contains "is not one of")
        assert any("is not one of" in error.message for error in errors)

    def test_invalid_weight_profile_fails(self, validator: Draft7Validator):
        """Test that unknown weight_profile fails validation."""
        invalid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["automation"],
                "target_user_types": ["users"],
            },
            "evaluation": {
                "weight_profile": "unknown_profile",  # Not in enum
            },
        }

        errors = list(validator.iter_errors(invalid_profile))
        assert len(errors) > 0
        assert any("is not one of" in error.message for error in errors)

    def test_invalid_ideation_mode_fails(self, validator: Draft7Validator):
        """Test that unknown ideation_mode fails validation."""
        invalid_profile = {
            "name": "test",
            "domain": {
                "name": "test",
                "description": "test",
                "categories": ["mcp_server"],
                "target_user_types": ["users"],
            },
            "ideation_mode": "unknown_mode",  # Not in enum
        }

        errors = list(validator.iter_errors(invalid_profile))
        assert len(errors) > 0
        assert any("is not one of" in error.message for error in errors)


# ── Default Value Tests ────────────────────────────────────────────────


class TestDefaultValues:
    """Tests that verify schema documents default values correctly."""

    def test_schema_documents_default_weight(self, schema: dict):
        """Test that weight field has documented default."""
        sources = schema["properties"]["sources"]
        weight_prop = sources["items"]["properties"]["weight"]
        assert "default" in weight_prop
        assert weight_prop["default"] == 1.0

    def test_schema_documents_default_enabled(self, schema: dict):
        """Test that enabled field has documented default."""
        sources = schema["properties"]["sources"]
        enabled_prop = sources["items"]["properties"]["enabled"]
        assert "default" in enabled_prop
        assert enabled_prop["default"] is True

    def test_schema_documents_default_weight_profile(self, schema: dict):
        """Test that weight_profile has documented default."""
        evaluation = schema["properties"]["evaluation"]
        weight_profile_prop = evaluation["properties"]["weight_profile"]
        assert "default" in weight_profile_prop
        assert weight_profile_prop["default"] == "default"

    def test_schema_documents_default_min_score(self, schema: dict):
        """Test that min_score has documented default."""
        evaluation = schema["properties"]["evaluation"]
        min_score_prop = evaluation["properties"]["min_score"]
        assert "default" in min_score_prop
        assert min_score_prop["default"] == 50.0

    def test_schema_documents_default_ideation_mode(self, schema: dict):
        """Test that ideation_mode has documented default."""
        ideation_prop = schema["properties"]["ideation_mode"]
        assert "default" in ideation_prop
        assert ideation_prop["default"] == "direct"

    def test_schema_documents_default_signal_limit(self, schema: dict):
        """Test that signal_limit has documented default."""
        signal_limit_prop = schema["properties"]["signal_limit"]
        assert "default" in signal_limit_prop
        assert signal_limit_prop["default"] == 30

    def test_schema_documents_default_output_dir(self, schema: dict):
        """Test that output_dir has documented default."""
        output_dir_prop = schema["properties"]["output_dir"]
        assert "default" in output_dir_prop
        assert output_dir_prop["default"] == ".max-output"
