"""Profile loader — find, parse, and validate pipeline profiles from YAML files."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from max.profiles.schema import (
    DEFAULT_DOMAIN_CONTEXT,
    EvaluationConfig,
    PipelineProfile,
    SourceConfig,
)

logger = logging.getLogger(__name__)


class ProfileValidationError(Exception):
    """Raised when profile validation fails."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if len(self.issues) == 1:
            return f"Profile validation failed: {self.issues[0]}"
        return f"Profile validation failed with {len(self.issues)} errors:\n" + "\n".join(
            f"  - {issue}" for issue in self.issues
        )


@dataclass(frozen=True)
class ProfileFileValidationResult:
    """Validation result for a single profile YAML file."""

    name: str
    path: Path
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def get_profiles_dir() -> Path:
    """Return the profiles directory (project_root/profiles/)."""
    # Walk up from this file to find the project root (where pyproject.toml lives)
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "pyproject.toml").exists():
            return current / "profiles"
        current = current.parent
    # Fallback: cwd / profiles
    return Path.cwd() / "profiles"


def load_profile(name: str) -> PipelineProfile:
    """Load a profile by name from the profiles directory.

    Raises FileNotFoundError if no matching YAML file is found.
    """
    profiles_dir = get_profiles_dir()
    yaml_path = profiles_dir / f"{name}.yaml"
    if not yaml_path.exists():
        # Also try .yml extension
        yaml_path = profiles_dir / f"{name}.yml"
    if not yaml_path.exists():
        available = list_profiles()
        raise FileNotFoundError(
            f"Profile '{name}' not found in {profiles_dir}. "
            f"Available: {available or 'none'}"
        )
    return _load_yaml(yaml_path)


def get_default_profile() -> PipelineProfile:
    """Return the default devtools profile.

    Tries to load profiles/devtools.yaml first. If not found, constructs
    from code constants (backward compatible — no YAML file required).
    """
    try:
        return load_profile("devtools")
    except FileNotFoundError:
        pass

    return PipelineProfile(
        name="devtools",
        domain=DEFAULT_DOMAIN_CONTEXT,
        sources=[
            SourceConfig(adapter="hackernews"),
            SourceConfig(
                adapter="reddit",
                params={
                    "subreddits": [
                        "programming",
                        "MachineLearning",
                        "LocalLLaMA",
                        "ChatGPT",
                        "artificial",
                        "devops",
                        "ExperiencedDevs",
                    ]
                },
            ),
            SourceConfig(
                adapter="github",
                params={"topics": ["mcp", "ai-agent", "llm", "developer-tools", "cli"]},
            ),
            SourceConfig(
                adapter="github_issues",
                params={
                    "queries": [
                        '"ai agent" label:enhancement is:open sort:reactions-+1-desc',
                        '"llm" label:bug is:open sort:reactions-+1-desc',
                        '"mcp server" is:issue is:open sort:comments-desc',
                        '"ai agent" is:issue is:open sort:reactions-+1-desc',
                    ]
                },
            ),
            SourceConfig(
                adapter="npm_registry",
                params={"queries": ["mcp server", "ai agent", "llm tool", "claude"]},
            ),
            SourceConfig(
                adapter="pypi_registry",
                params={
                    "keywords": [
                        "ai", "llm", "agent", "mcp", "langchain", "openai", "anthropic",
                        "transformer", "embedding", "rag", "vector", "gpt", "claude",
                        "huggingface", "diffusion", "neural", "deep-learning",
                        "machine-learning", "chatbot", "prompt", "tokenizer", "inference",
                    ]
                },
            ),
            SourceConfig(
                adapter="security_advisories",
                params={"ecosystems": ["pip", "npm", "go"], "severities": ["critical", "high"]},
            ),
            SourceConfig(
                adapter="product_hunt",
                params={"topics": ["developer-tools", "artificial-intelligence"]},
            ),
        ],
        evaluation=EvaluationConfig(weight_profile="default", min_score=50.0),
        output_dir=".max-output",
        signal_limit=30,
        ideation_mode="direct",
    )


def list_profiles() -> list[str]:
    """List available profile names (stems of YAML files in profiles/)."""
    profiles_dir = get_profiles_dir()
    if not profiles_dir.is_dir():
        return []
    names = []
    for path in sorted(profiles_dir.iterdir()):
        if path.suffix in (".yaml", ".yml") and path.stem != "schema":
            names.append(path.stem)
    return names


def get_profile_path(name: str) -> Path:
    """Return the YAML path for a profile name.

    Raises FileNotFoundError if no matching YAML file is found.
    """
    profiles_dir = get_profiles_dir()
    yaml_path = profiles_dir / f"{name}.yaml"
    if not yaml_path.exists():
        yaml_path = profiles_dir / f"{name}.yml"
    if not yaml_path.exists():
        available = list_profiles()
        raise FileNotFoundError(
            f"Profile '{name}' not found in {profiles_dir}. "
            f"Available: {available or 'none'}"
        )
    return yaml_path


def list_profile_paths() -> list[Path]:
    """List all YAML profile files, excluding the JSON schema file."""
    profiles_dir = get_profiles_dir()
    if not profiles_dir.is_dir():
        return []
    return [
        path
        for path in sorted(profiles_dir.iterdir())
        if path.suffix in (".yaml", ".yml") and path.stem != "schema"
    ]


def _load_profile_json_schema() -> dict:
    """Load profiles/schema.yaml as a JSON Schema document."""
    schema_path = get_profiles_dir() / "schema.yaml"
    with open(schema_path) as f:
        schema = yaml.safe_load(f)
    if not isinstance(schema, dict):
        raise ValueError(f"Invalid profile schema YAML (expected dict): {schema_path}")
    try:
        from jsonschema import Draft7Validator
    except ModuleNotFoundError:
        return schema
    Draft7Validator.check_schema(schema)
    return schema


def _format_json_schema_error(error) -> str:
    path = ".".join(str(p) for p in error.path) if error.path else "root"
    return f"{path}: {error.message}"


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _fallback_schema_errors(data: Any, schema: dict, path: str = "root") -> list[str]:
    """Validate the JSON Schema subset used by profiles/schema.yaml."""
    errors: list[str] = []

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _schema_type_matches(data, expected_type):
        errors.append(f"{path}: {data!r} is not of type '{expected_type}'")
        return errors

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: {data!r} is not one of {schema['enum']!r}")

    if isinstance(data, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(data) < min_length:
            errors.append(f"{path}: {data!r} is too short")

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and data < minimum:
            errors.append(f"{path}: {data!r} is less than the minimum of {minimum!r}")
        if isinstance(maximum, (int, float)) and data > maximum:
            errors.append(f"{path}: {data!r} is greater than the maximum of {maximum!r}")

    if isinstance(data, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(data) < min_items:
            errors.append(f"{path}: {data!r} is too short")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(data):
                errors.extend(_fallback_schema_errors(item, item_schema, f"{path}.{index}"))

    if isinstance(data, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in data:
                    errors.append(f"{path}: {key!r} is a required property")
        if isinstance(properties, dict):
            for key, value in data.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    errors.extend(_fallback_schema_errors(value, child_schema, f"{path}.{key}"))
                elif schema.get("additionalProperties") is False:
                    errors.append(
                        f"{path}: Additional properties are not allowed ({key!r} was unexpected)"
                    )
                elif isinstance(schema.get("additionalProperties"), dict):
                    errors.extend(
                        _fallback_schema_errors(
                            value,
                            schema["additionalProperties"],
                            f"{path}.{key}",
                        )
                    )

    return errors


def _validate_against_json_schema(data: dict, schema: dict) -> list[str]:
    try:
        from jsonschema import Draft7Validator
    except ModuleNotFoundError:
        return [
            error.replace("root.", "")
            for error in _fallback_schema_errors(data, schema)
        ]

    validator = Draft7Validator(schema)
    schema_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    return [_format_json_schema_error(error) for error in schema_errors]


def validate_profile_file(path: Path, schema: dict | None = None) -> ProfileFileValidationResult:
    """Validate one profile YAML file against JSON Schema and the profile loader."""
    errors: list[str] = []
    schema_data = schema if schema is not None else _load_profile_json_schema()

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return ProfileFileValidationResult(path.stem, path, [f"YAML: {e}"])

    if not isinstance(data, dict):
        errors.append(f"YAML: expected mapping/object, got {type(data).__name__}")
    else:
        schema_errors = _validate_against_json_schema(data, schema_data)
        errors.extend(f"schema: {error}" for error in schema_errors)

    logger_was_disabled = logger.disabled
    logger.disabled = True
    try:
        try:
            _load_yaml(path)
        except Exception as e:
            errors.append(f"loader: {e}")
    finally:
        logger.disabled = logger_was_disabled

    return ProfileFileValidationResult(path.stem, path, errors)


def validate_profile_files(profile: str | None = None) -> list[ProfileFileValidationResult]:
    """Validate all profile files, or one profile by name."""
    paths = [get_profile_path(profile)] if profile else list_profile_paths()
    schema = _load_profile_json_schema()
    return [validate_profile_file(path, schema=schema) for path in paths]


def validate_profile(profile: PipelineProfile) -> list[str]:
    """Validate a pipeline profile and return a list of issues (errors and warnings).

    Validations performed:
    1. Adapter names exist in the registry (ERROR)
    2. Weight values are numeric and in range 0.0-10.0 (ERROR)
    3. Category names are known (WARNING)

    Returns:
        List of error/warning messages. Errors are prefixed with "ERROR:",
        warnings with "WARNING:".
    """
    issues: list[str] = []

    # Import here to avoid circular dependency
    from max.sources.registry import list_adapters

    # Get available adapters
    try:
        available_adapters = set(list_adapters())
    except Exception as e:
        logger.warning("Failed to load adapter registry: %s", e)
        available_adapters = set()

    # Validate adapter names
    for source in profile.sources:
        if source.adapter not in available_adapters:
            issues.append(
                f"ERROR: Unknown adapter '{source.adapter}'. "
                f"Available adapters: {sorted(available_adapters)}"
            )

    # Validate weight values
    for source in profile.sources:
        weight = source.weight
        if not isinstance(weight, (int, float)):
            issues.append(
                f"ERROR: Invalid weight type for adapter '{source.adapter}': "
                f"{type(weight).__name__} (expected numeric)"
            )
        elif weight < 0.0 or weight > 10.0:
            issues.append(
                f"ERROR: Weight {weight} for adapter '{source.adapter}' is out of range "
                f"(must be between 0.0 and 10.0)"
            )

    # Validate category names (warning only)
    # Use DEFAULT_DOMAIN_CONTEXT categories as reference
    known_categories = set(DEFAULT_DOMAIN_CONTEXT.categories)
    profile_categories = set(profile.domain.categories)
    unknown_categories = profile_categories - known_categories

    if unknown_categories:
        logger.warning(
            "Profile '%s' uses unknown categories: %s. Known categories: %s",
            profile.name,
            sorted(unknown_categories),
            sorted(known_categories),
        )
        issues.append(
            f"WARNING: Unknown categories in profile '{profile.name}': "
            f"{sorted(unknown_categories)}"
        )

    return issues


def _load_yaml(path: Path) -> PipelineProfile:
    """Parse a YAML file into a PipelineProfile."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid profile YAML (expected dict): {path}")

    profile = PipelineProfile(**data)

    # Validate the profile
    issues = validate_profile(profile)

    # Separate errors and warnings
    errors = [issue for issue in issues if issue.startswith("ERROR:")]
    warnings = [issue for issue in issues if issue.startswith("WARNING:")]

    # Log warnings
    for warning in warnings:
        logger.warning(warning.replace("WARNING: ", ""))

    # Raise on errors
    if errors:
        # Remove "ERROR: " prefix for the exception
        error_messages = [e.replace("ERROR: ", "") for e in errors]
        raise ProfileValidationError(error_messages)

    return profile
