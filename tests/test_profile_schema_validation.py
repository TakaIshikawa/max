"""JSON Schema validation tests for all profile YAML files.

This test suite validates that all YAML profile files conform to the
JSON Schema defined in profiles/schema.yaml.

Coverage:
1. Schema file itself is valid JSON Schema
2. All 13 domain profile YAML files validate against the schema
3. Schema correctly documents required fields
4. Schema correctly documents type constraints
5. Schema correctly documents enum constraints
6. Source adapter references match actual registered adapters in registry.py
7. Source weight values are valid numbers within specified range
8. Category taxonomy is consistent across all profiles
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator


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
            "nuget",
            "npm_registry",
            "pypi_registry",
            "security_advisories",
            "snyk_reports",
            "product_hunt",
            "rss_feed",
            "funding_rounds",
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

    def test_all_13_domain_profiles_present(self, profile_files: list[Path]):
        """Test that all 13 expected domain profile files are present."""
        expected_profiles = {
            "ai-infra",
            "construction",
            "creator-economy",
            "cybersecurity",
            "devtools",
            "education",
            "fintech",
            "healthcare",
            "hr",
            "legaltech",
            "proptech",
            "supply-chain",
            "sustainability",
        }

        found_profiles = {p.stem for p in profile_files}

        missing = expected_profiles - found_profiles
        if missing:
            pytest.fail(f"Missing {len(missing)} expected profile(s): {sorted(missing)}")

        # Also check for any unexpected profiles
        extra = found_profiles - expected_profiles
        if extra:
            # This is informational - new profiles are OK
            print(f"\nNote: Found {len(extra)} additional profile(s): {sorted(extra)}")

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

    def test_valid_snyk_reports_params_pass(self, validator: Draft7Validator):
        """Test that snyk_reports accepts report ingestion params."""
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
                    "adapter": "snyk_reports",
                    "enabled": False,
                    "params": {
                        "report_urls": ["https://example.com/snyk-report.json"],
                        "local_paths": ["reports/snyk.md"],
                        "sections": ["AI", "Supply chain"],
                        "keywords": ["vulnerability", "MCP"],
                        "max_items": 5,
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


# ── Adapter Registry Validation Tests ──────────────────────────────────


class TestAdapterRegistryValidation:
    """Tests that validate source adapters against the actual registry."""

    @pytest.fixture(scope="class")
    def registered_adapters(self) -> set[str]:
        """Get set of all registered adapter names from registry.py."""
        from max.sources.registry import list_adapters

        return set(list_adapters())

    def test_registry_has_adapters(self, registered_adapters: set[str]):
        """Test that adapter registry is not empty."""
        assert len(registered_adapters) > 0, "Adapter registry should not be empty"

    def test_all_profile_adapters_are_registered(
        self, profile_files: list[Path], registered_adapters: set[str]
    ):
        """Test that all adapters referenced in profiles exist in registry."""
        unknown_adapters = {}

        for profile_path in profile_files:
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)

            sources = profile_data.get("sources", [])
            for idx, source in enumerate(sources):
                adapter_name = source.get("adapter")
                if adapter_name and adapter_name not in registered_adapters:
                    if profile_path.name not in unknown_adapters:
                        unknown_adapters[profile_path.name] = []
                    unknown_adapters[profile_path.name].append(
                        f"  source[{idx}]: '{adapter_name}' not in registry"
                    )

        if unknown_adapters:
            error_report = []
            for filename, errors in unknown_adapters.items():
                error_report.append(f"\n{filename}:")
                error_report.extend(errors)
            error_report.append(f"\n\nRegistered adapters: {sorted(registered_adapters)}")

            pytest.fail(
                f"{len(unknown_adapters)} profile(s) reference unregistered adapters:"
                + "".join(error_report)
            )

    def test_schema_adapter_enum_matches_registry(
        self, schema: dict, registered_adapters: set[str]
    ):
        """Test that schema adapter enum includes all registered adapters.

        Note: This is a schema maintenance check. If this test fails, it means
        the schema.yaml file needs to be updated to include new adapters that
        have been added to the registry.
        """
        sources = schema["properties"]["sources"]
        adapter_prop = sources["items"]["properties"]["adapter"]
        schema_adapters = set(adapter_prop.get("enum", []))

        # Registry adapters should be subset of or equal to schema enum
        missing_in_schema = registered_adapters - schema_adapters
        extra_in_schema = schema_adapters - registered_adapters

        errors = []
        if missing_in_schema:
            errors.append(
                f"Schema adapter enum is missing {len(missing_in_schema)} "
                f"registered adapter(s): {sorted(missing_in_schema)}"
            )
        if extra_in_schema:
            errors.append(
                f"Schema adapter enum has {len(extra_in_schema)} adapter(s) "
                f"not in registry: {sorted(extra_in_schema)}"
            )

        if errors:
            pytest.fail("\n".join(errors))


# ── Weight Sum Validation Tests ────────────────────────────────────────


class TestWeightSumValidation:
    """Tests that validate source weight normalization."""

    def test_source_weights_are_valid_numbers(self, profile_files: list[Path]):
        """Test that all source weights are valid numbers in range."""
        invalid_weights = {}

        for profile_path in profile_files:
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)

            sources = profile_data.get("sources", [])
            for idx, source in enumerate(sources):
                weight = source.get("weight")
                if weight is not None:
                    # Check type
                    if not isinstance(weight, (int, float)):
                        if profile_path.name not in invalid_weights:
                            invalid_weights[profile_path.name] = []
                        invalid_weights[profile_path.name].append(
                            f"  source[{idx}] ({source.get('adapter')}): "
                            f"weight is {type(weight).__name__}, not a number"
                        )
                        continue

                    # Check range
                    if not (0.0 <= weight <= 10.0):
                        if profile_path.name not in invalid_weights:
                            invalid_weights[profile_path.name] = []
                        invalid_weights[profile_path.name].append(
                            f"  source[{idx}] ({source.get('adapter')}): "
                            f"weight {weight} out of range [0.0, 10.0]"
                        )

        if invalid_weights:
            error_report = []
            for filename, errors in invalid_weights.items():
                error_report.append(f"\n{filename}:")
                error_report.extend(errors)

            pytest.fail(
                f"{len(invalid_weights)} profile(s) have invalid source weights:"
                + "".join(error_report)
            )

    def test_source_weights_sum_is_reasonable(self, profile_files: list[Path]):
        """Test that sum of source weights per profile is reasonable.

        This is a sanity check - if weights are specified, the sum should not be
        extremely low (< 0.1) or extremely high (> 1000), which would indicate
        a configuration error.
        """
        suspicious_sums = {}

        for profile_path in profile_files:
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)

            sources = profile_data.get("sources", [])
            if not sources:
                continue

            # Collect weights, using default of 1.0 if not specified
            weights = [source.get("weight", 1.0) for source in sources]
            total_weight = sum(weights)

            # Only flag if weights were explicitly set and sum is suspicious
            has_explicit_weights = any("weight" in source for source in sources)
            if has_explicit_weights and (total_weight < 0.1 or total_weight > 1000):
                suspicious_sums[profile_path.name] = {
                    "total": total_weight,
                    "count": len(sources),
                    "weights": weights,
                }

        if suspicious_sums:
            error_report = []
            for filename, info in suspicious_sums.items():
                error_report.append(
                    f"\n{filename}: sum={info['total']:.2f} "
                    f"across {info['count']} sources (weights: {info['weights']})"
                )

            pytest.fail(
                f"{len(suspicious_sums)} profile(s) have suspicious weight sums "
                "(< 0.1 or > 1000):" + "".join(error_report)
            )


# ── Category Taxonomy Validation Tests ─────────────────────────────────


class TestCategoryTaxonomyConsistency:
    """Tests that validate category taxonomy consistency across profiles."""

    @pytest.fixture(scope="class")
    def all_categories_by_profile(self, profile_files: list[Path]) -> dict[str, set[str]]:
        """Collect all categories used by each profile."""
        categories_by_profile = {}

        for profile_path in profile_files:
            with open(profile_path) as f:
                profile_data = yaml.safe_load(f)

            domain = profile_data.get("domain", {})
            categories = domain.get("categories", [])
            categories_by_profile[profile_path.stem] = set(categories)

        return categories_by_profile

    @pytest.fixture(scope="class")
    def all_unique_categories(
        self, all_categories_by_profile: dict[str, set[str]]
    ) -> set[str]:
        """Get set of all unique categories across all profiles."""
        all_cats = set()
        for cats in all_categories_by_profile.values():
            all_cats.update(cats)
        return all_cats

    def test_profiles_have_categories(
        self, all_categories_by_profile: dict[str, set[str]]
    ):
        """Test that all profiles define at least one category."""
        profiles_without_categories = [
            name for name, cats in all_categories_by_profile.items() if not cats
        ]

        if profiles_without_categories:
            pytest.fail(
                f"{len(profiles_without_categories)} profile(s) have no categories: "
                f"{sorted(profiles_without_categories)}"
            )

    def test_category_names_are_consistent_format(self, all_unique_categories: set[str]):
        """Test that category names follow consistent naming convention.

        Categories should be:
        - lowercase with underscores (snake_case)
        - no spaces
        - alphanumeric plus underscores only
        """
        invalid_categories = []

        for category in all_unique_categories:
            # Check for spaces
            if " " in category:
                invalid_categories.append(f"'{category}' contains spaces")
                continue

            # Check for uppercase
            if category != category.lower():
                invalid_categories.append(f"'{category}' contains uppercase letters")
                continue

            # Check for valid characters (alphanumeric + underscore)
            if not all(c.isalnum() or c == "_" for c in category):
                invalid_categories.append(
                    f"'{category}' contains invalid characters (only a-z, 0-9, _ allowed)"
                )

        if invalid_categories:
            pytest.fail(
                f"{len(invalid_categories)} category name(s) violate naming convention:\n"
                + "\n".join(f"  - {msg}" for msg in invalid_categories)
            )

    def test_category_taxonomy_size_is_reasonable(self, all_unique_categories: set[str]):
        """Test that the global category taxonomy is not excessively large.

        A large number of unique categories (> 100) might indicate inconsistent
        naming or lack of taxonomy governance. With 13 domain profiles, 79 unique
        categories is reasonable (~6 categories per profile on average).
        """
        num_categories = len(all_unique_categories)
        # This is a soft limit - adjust if legitimate use cases require more
        # With 13 profiles and domain-specific categories, 100 is reasonable
        max_reasonable = 100

        if num_categories > max_reasonable:
            pytest.fail(
                f"Category taxonomy has {num_categories} unique categories "
                f"(> {max_reasonable}), which may indicate inconsistent naming.\n"
                f"Categories: {sorted(all_unique_categories)}"
            )

    def test_common_categories_are_consistently_named(
        self, all_categories_by_profile: dict[str, set[str]]
    ):
        """Test that commonly used categories have consistent names.

        If multiple profiles use similar category names (e.g., 'cli_tool' vs 'cli-tool'),
        this might indicate inconsistent naming that should be unified.
        """
        # Collect category frequency
        category_counts: dict[str, int] = {}
        for cats in all_categories_by_profile.values():
            for cat in cats:
                category_counts[cat] = category_counts.get(cat, 0) + 1

        # Group similar category names (normalized by removing - and _)
        normalized_groups: dict[str, list[str]] = {}
        for category in category_counts:
            normalized = category.replace("-", "").replace("_", "")
            if normalized not in normalized_groups:
                normalized_groups[normalized] = []
            normalized_groups[normalized].append(category)

        # Find groups with multiple variants
        inconsistent_groups = {
            norm: variants
            for norm, variants in normalized_groups.items()
            if len(variants) > 1
        }

        if inconsistent_groups:
            error_report = []
            for norm, variants in inconsistent_groups.items():
                usage = {v: category_counts[v] for v in variants}
                error_report.append(
                    f"\n  '{norm}' has {len(variants)} variants: {usage}"
                )

            pytest.fail(
                f"{len(inconsistent_groups)} category name(s) have inconsistent variants:"
                + "".join(error_report)
            )

    def test_schema_documents_common_categories(self, schema: dict):
        """Test that schema documents or references common categories.

        While the schema may not enumerate all categories, it should provide
        guidance on the expected category taxonomy in its description or examples.
        """
        domain_props = schema["properties"]["domain"]["properties"]
        categories_prop = domain_props["categories"]

        # Check that there's documentation about categories
        assert (
            "description" in categories_prop
        ), "Categories field should have a description"
        assert categories_prop["type"] == "array", "Categories should be an array"

        # Check that items are defined
        if "items" in categories_prop:
            items = categories_prop["items"]
            assert items["type"] == "string", "Category items should be strings"
            # Optional: check for guidance via description, examples, enum, or pattern
            # This is informational - we don't strictly require it
