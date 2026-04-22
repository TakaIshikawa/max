"""Reusable validation for YAML pipeline profile files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from max.evaluation.weights import DEFAULT_WEIGHTS, WEIGHT_PROFILES
from max.profiles.schema import DEFAULT_DOMAIN_CONTEXT, PipelineProfile

IssueSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class ProfileValidationIssue:
    """A structured validation issue for profile YAML."""

    severity: IssueSeverity
    code: str
    message: str
    path: str = "root"

    def format(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


@dataclass(frozen=True)
class ProfileFileValidationResult:
    """Validation result for a single profile YAML file."""

    name: str
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_issues: list[ProfileValidationIssue] = field(default_factory=list)
    warning_issues: list[ProfileValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @classmethod
    def from_issues(
        cls,
        name: str,
        path: Path,
        issues: list[ProfileValidationIssue],
    ) -> "ProfileFileValidationResult":
        errors = [issue.format() for issue in issues if issue.severity == "error"]
        warnings = [issue.format() for issue in issues if issue.severity == "warning"]
        return cls(
            name=name,
            path=path,
            errors=errors,
            warnings=warnings,
            error_issues=[issue for issue in issues if issue.severity == "error"],
            warning_issues=[issue for issue in issues if issue.severity == "warning"],
        )


def load_profile_json_schema(profiles_dir: Path) -> dict:
    """Load profiles/schema.yaml as a JSON Schema document."""
    schema_path = profiles_dir / "schema.yaml"
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


def validate_profile_file(
    path: Path,
    *,
    schema: dict | None = None,
    profiles_dir: Path | None = None,
) -> ProfileFileValidationResult:
    """Validate one profile YAML file without mutating profile data."""
    issues: list[ProfileValidationIssue] = []
    base_dir = profiles_dir or path.parent

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        issues.append(ProfileValidationIssue("error", "yaml_parse", f"YAML: {e}"))
        return ProfileFileValidationResult.from_issues(path.stem, path, issues)

    if not isinstance(data, dict):
        issues.append(
            ProfileValidationIssue(
                "error",
                "yaml_type",
                f"YAML: expected mapping/object, got {type(data).__name__}",
            )
        )
        return ProfileFileValidationResult.from_issues(path.stem, path, issues)

    schema_data = schema if schema is not None else load_profile_json_schema(base_dir)
    issues.extend(_schema_issues(data, schema_data))
    issues.extend(_required_field_issues(data))
    issues.extend(_profile_semantic_issues(data, path=path))

    try:
        profile = PipelineProfile(**data)
    except ValidationError as e:
        issues.extend(_pydantic_issues(e))
    except Exception as e:
        issues.append(ProfileValidationIssue("error", "profile_parse", f"loader: {e}"))
    else:
        issues.extend(validate_profile_model(profile))

    return ProfileFileValidationResult.from_issues(path.stem, path, _dedupe_issues(issues))


def validate_profile_model(profile: PipelineProfile) -> list[ProfileValidationIssue]:
    """Validate an already parsed profile without mutating it."""
    issues: list[ProfileValidationIssue] = []

    try:
        from max.sources.registry import list_adapters

        available_adapters = set(list_adapters())
    except Exception:
        available_adapters = set()

    for index, source in enumerate(profile.sources):
        if source.adapter not in available_adapters:
            issues.append(
                ProfileValidationIssue(
                    "error",
                    "unknown_source_adapter",
                    (
                        f"Unknown adapter '{source.adapter}'. "
                        f"Available adapters: {sorted(available_adapters)}"
                    ),
                    f"sources.{index}.adapter",
                )
            )

        weight = source.weight
        if not isinstance(weight, (int, float)):
            issues.append(
                ProfileValidationIssue(
                    "error",
                    "invalid_source_weight_type",
                    f"Invalid weight type for adapter '{source.adapter}': {type(weight).__name__} (expected numeric)",
                    f"sources.{index}.weight",
                )
            )
        elif weight < 0.0 or weight > 10.0:
            issues.append(
                ProfileValidationIssue(
                    "error",
                    "invalid_source_weight",
                    (
                        f"Weight {weight} for adapter '{source.adapter}' is out of range "
                        "(must be between 0.0 and 10.0)"
                    ),
                    f"sources.{index}.weight",
                )
            )

    known_categories = set(DEFAULT_DOMAIN_CONTEXT.categories)
    unknown_categories = set(profile.domain.categories) - known_categories
    if unknown_categories:
        issues.append(
            ProfileValidationIssue(
                "warning",
                "unknown_categories",
                f"Unknown categories in profile '{profile.name}': {sorted(unknown_categories)}",
                "domain.categories",
            )
        )
    for category in _duplicates(profile.domain.categories):
        issues.append(
            ProfileValidationIssue(
                "warning",
                "duplicate_category",
                f"Duplicate category '{category}'",
                "domain.categories",
            )
        )

    evaluation = profile.evaluation
    if evaluation.weight_profile not in WEIGHT_PROFILES:
        issues.append(
            ProfileValidationIssue(
                "error",
                "unknown_weight_profile",
                f"Unknown evaluation weight profile '{evaluation.weight_profile}'. Available profiles: {sorted(WEIGHT_PROFILES)}",
                "evaluation.weight_profile",
            )
        )

    if evaluation.custom_weights is not None:
        issues.extend(_custom_weight_issues(evaluation.custom_weights, "evaluation.custom_weights"))

    return issues


def _profile_semantic_issues(data: dict[str, Any], *, path: Path) -> list[ProfileValidationIssue]:
    issues: list[ProfileValidationIssue] = []
    domain = data.get("domain")
    if isinstance(domain, dict):
        categories = domain.get("categories")
        if isinstance(categories, list):
            duplicates = _duplicates([item for item in categories if isinstance(item, str)])
            for category in duplicates:
                issues.append(
                    ProfileValidationIssue(
                        "warning",
                        "duplicate_category",
                        f"Duplicate category '{category}'",
                        "domain.categories",
                    )
                )

    evaluation = data.get("evaluation")
    if isinstance(evaluation, dict):
        custom_weights = evaluation.get("custom_weights")
        if isinstance(custom_weights, dict):
            issues.extend(_custom_weight_issues(custom_weights, "evaluation.custom_weights"))

    issues.extend(_file_reference_issues(data, profile_path=path))
    return issues


def _custom_weight_issues(weights: dict[str, Any], path: str) -> list[ProfileValidationIssue]:
    issues: list[ProfileValidationIssue] = []
    valid_dimensions = set(DEFAULT_WEIGHTS)
    for dimension, value in weights.items():
        dimension_path = f"{path}.{dimension}"
        if dimension not in valid_dimensions:
            issues.append(
                ProfileValidationIssue(
                    "error",
                    "unknown_weight_dimension",
                    f"Unknown evaluation weight dimension '{dimension}'. Valid dimensions: {sorted(valid_dimensions)}",
                    dimension_path,
                )
            )
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            issues.append(
                ProfileValidationIssue(
                    "error",
                    "invalid_weight_value_type",
                    f"Weight for dimension '{dimension}' must be numeric",
                    dimension_path,
                )
            )
        elif value < 0.0 or value > 1.0:
            issues.append(
                ProfileValidationIssue(
                    "error",
                    "invalid_weight_value",
                    f"Weight for dimension '{dimension}' must be between 0.0 and 1.0",
                    dimension_path,
                )
            )

    if weights:
        total = sum(value for value in weights.values() if isinstance(value, (int, float)) and not isinstance(value, bool))
        if abs(total - 1.0) > 0.001:
            issues.append(
                ProfileValidationIssue(
                    "warning",
                    "custom_weight_sum",
                    f"Custom evaluation weights sum to {total:.4f}, expected 1.0",
                    path,
                )
            )
    return issues


def _required_field_issues(data: dict[str, Any]) -> list[ProfileValidationIssue]:
    required_paths = [
        ("name", data),
        ("domain", data),
    ]
    domain = data.get("domain")
    if isinstance(domain, dict):
        required_paths.extend(
            [
                ("domain.name", domain),
                ("domain.description", domain),
                ("domain.categories", domain),
                ("domain.target_user_types", domain),
            ]
        )

    issues: list[ProfileValidationIssue] = []
    for path, container in required_paths:
        key = path.rsplit(".", 1)[-1]
        if key not in container:
            issues.append(
                ProfileValidationIssue(
                    "error",
                    "required_field_missing",
                    f"Missing required field '{path}'",
                    path,
                )
            )
    return issues


def _file_reference_issues(data: Any, *, profile_path: Path) -> list[ProfileValidationIssue]:
    issues: list[ProfileValidationIssue] = []
    profile_dir = profile_path.parent
    for key_path, value in _walk_file_reference_values(data):
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, str) or not item.strip():
                continue
            candidate = Path(item).expanduser()
            if not candidate.is_absolute():
                candidate = profile_dir / candidate
            if not candidate.exists():
                issues.append(
                    ProfileValidationIssue(
                        "warning",
                        "unreachable_file_reference",
                        f"Optional file reference '{item}' does not exist",
                        key_path,
                    )
                )
    return issues


def _walk_file_reference_values(data: Any, path: str = "root") -> list[tuple[str, Any]]:
    if isinstance(data, dict):
        found: list[tuple[str, Any]] = []
        for key, value in data.items():
            key_path = key if path == "root" else f"{path}.{key}"
            if _is_file_reference_key(str(key)):
                found.append((key_path, value))
            found.extend(_walk_file_reference_values(value, key_path))
        return found
    if isinstance(data, list):
        found = []
        for index, value in enumerate(data):
            found.extend(_walk_file_reference_values(value, f"{path}.{index}"))
        return found
    return []


def _is_file_reference_key(key: str) -> bool:
    normalized = key.lower()
    if normalized in {"output_dir", "distribution_path"}:
        return False
    return (
        normalized in {"file", "path", "file_path"}
        or normalized.endswith("_file")
        or normalized.endswith("_path")
    )


def _schema_issues(data: dict[str, Any], schema: dict) -> list[ProfileValidationIssue]:
    return [
        ProfileValidationIssue("error", "schema", f"schema: {path}: {message}", "")
        for path, message in _validate_against_json_schema(data, schema)
    ]


def _format_json_schema_error(error) -> tuple[str, str]:
    path = ".".join(str(p) for p in error.path) if error.path else "root"
    return path, error.message


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


def _fallback_schema_errors(data: Any, schema: dict, path: str = "root") -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []

    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _schema_type_matches(data, expected_type):
        errors.append((path, f"{data!r} is not of type '{expected_type}'"))
        return errors

    if "enum" in schema and data not in schema["enum"]:
        errors.append((path, f"{data!r} is not one of {schema['enum']!r}"))

    if isinstance(data, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(data) < min_length:
            errors.append((path, f"{data!r} is too short"))

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and data < minimum:
            errors.append((path, f"{data!r} is less than the minimum of {minimum!r}"))
        if isinstance(maximum, (int, float)) and data > maximum:
            errors.append((path, f"{data!r} is greater than the maximum of {maximum!r}"))

    if isinstance(data, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(data) < min_items:
            errors.append((path, f"{data!r} is too short"))
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
                    errors.append((path, f"{key!r} is a required property"))
        if isinstance(properties, dict):
            for key, value in data.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    errors.extend(_fallback_schema_errors(value, child_schema, f"{path}.{key}"))
                elif schema.get("additionalProperties") is False:
                    errors.append((path, f"Additional properties are not allowed ({key!r} was unexpected)"))
                elif isinstance(schema.get("additionalProperties"), dict):
                    errors.extend(_fallback_schema_errors(value, schema["additionalProperties"], f"{path}.{key}"))

    return errors


def _validate_against_json_schema(data: dict, schema: dict) -> list[tuple[str, str]]:
    try:
        from jsonschema import Draft7Validator
    except ModuleNotFoundError:
        return [
            (path.removeprefix("root."), message)
            for path, message in _fallback_schema_errors(data, schema)
        ]

    validator = Draft7Validator(schema)
    schema_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    return [_format_json_schema_error(error) for error in schema_errors]


def _pydantic_issues(error: ValidationError) -> list[ProfileValidationIssue]:
    issues: list[ProfileValidationIssue] = []
    for item in error.errors():
        path = ".".join(str(part) for part in item.get("loc", ())) or "root"
        issues.append(
            ProfileValidationIssue(
                "error",
                "profile_model",
                f"loader: {item.get('msg', 'invalid value')}",
                path,
            )
        )
    return issues


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _dedupe_issues(issues: list[ProfileValidationIssue]) -> list[ProfileValidationIssue]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[ProfileValidationIssue] = []
    for issue in issues:
        key = (issue.severity, issue.code, issue.path, issue.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped
