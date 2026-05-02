"""Profile gap matrix analysis across available pipeline profiles."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

import yaml

from max.analysis.profile_source_mix import _adapter_category, _adapter_source_type
from max.evaluation.weights import DEFAULT_WEIGHTS, get_weights
from max.profiles import loader as profile_loader
from max.profiles.schema import PipelineProfile, SourceConfig
from max.sources.registry import AdapterMetadata, get_adapter_metadata
from max.store.db import Store

DEFAULT_MIN_EVALUATION_WEIGHT = 0.10
DEFAULT_MAX_RECOMMENDED_ADAPTERS = 5
CSV_COLUMNS: tuple[str, ...] = (
    "profile",
    "category",
    "source",
    "gap_type",
    "severity_or_score",
    "observed_count",
    "target_count",
    "recommendation",
    "evidence_or_signal_references",
)


@dataclass(frozen=True)
class ProfileGapMatrixRow:
    """Profile-level source, adapter, and evaluation coverage gaps."""

    profile_name: str
    domain: str
    enabled_source_categories: list[str]
    missing_source_categories: list[str]
    enabled_adapters: list[str]
    disabled_relevant_adapters: list[str]
    unknown_adapters: list[str]
    missing_adapters: list[str]
    evaluation_weight_profile: str
    evaluation_weights: dict[str, float]
    underweighted_evaluation_dimensions: list[str]
    recommended_next_adapters: list[str]
    status: str


@dataclass(frozen=True)
class ProfileGapMatrix:
    """Coverage gap matrix for all available profile files."""

    profiles_dir: str
    profile_count: int
    row_count: int
    required_source_categories: list[str]
    min_evaluation_weight: float
    rows: list[ProfileGapMatrixRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


def build_profile_gap_matrix(
    store: Store | None = None,
    *,
    profiles_dir: str | Path | None = None,
    required_source_categories: list[str] | None = None,
    min_evaluation_weight: float = DEFAULT_MIN_EVALUATION_WEIGHT,
    max_recommended_adapters: int = DEFAULT_MAX_RECOMMENDED_ADAPTERS,
) -> ProfileGapMatrix:
    """Compare profile YAML files against adapter and evaluation coverage.

    The ``store`` argument is accepted for compatibility with older callers; this
    matrix is based on static profile and registry metadata only.
    """

    del store
    if min_evaluation_weight < 0:
        raise ValueError("min_evaluation_weight must be non-negative")
    if max_recommended_adapters < 1:
        raise ValueError("max_recommended_adapters must be at least 1")

    resolved_profiles_dir = (
        Path(profiles_dir).expanduser()
        if profiles_dir is not None
        else profile_loader.get_profiles_dir()
    )
    if not resolved_profiles_dir.exists():
        raise FileNotFoundError(f"Profile directory not found: {resolved_profiles_dir}")
    if not resolved_profiles_dir.is_dir():
        raise NotADirectoryError(f"Profile path is not a directory: {resolved_profiles_dir}")

    profile_paths = [
        path
        for path in sorted(resolved_profiles_dir.iterdir())
        if path.suffix in (".yaml", ".yml") and path.stem != "schema"
    ]
    metadata = get_adapter_metadata()
    source_categories = sorted(
        required_source_categories
        if required_source_categories is not None
        else _registered_source_categories(metadata)
    )

    rows = [
        _build_row(
            _load_profile_yaml(profile_path),
            metadata=metadata,
            required_source_categories=source_categories,
            min_evaluation_weight=min_evaluation_weight,
            max_recommended_adapters=max_recommended_adapters,
        )
        for profile_path in profile_paths
    ]

    return ProfileGapMatrix(
        profiles_dir=str(resolved_profiles_dir),
        profile_count=len(profile_paths),
        row_count=len(rows),
        required_source_categories=source_categories,
        min_evaluation_weight=min_evaluation_weight,
        rows=rows,
    )


def render_profile_gap_matrix(
    matrix: ProfileGapMatrix | dict[str, Any],
    fmt: str = "markdown",
) -> str:
    """Render a profile gap matrix as Markdown, CSV, or deterministic JSON."""

    payload = matrix.to_dict() if isinstance(matrix, ProfileGapMatrix) else matrix
    if fmt == "json":
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_profile_gap_matrix_csv(payload)
    if fmt != "markdown":
        raise ValueError(f"Unsupported profile gap matrix format: {fmt}")
    return render_profile_gap_matrix_markdown(payload)


def render_profile_gap_matrix_markdown(matrix: ProfileGapMatrix | dict[str, Any]) -> str:
    """Render a profile gap matrix as markdown."""

    payload = matrix.to_dict() if isinstance(matrix, ProfileGapMatrix) else matrix
    lines = [
        "# Profile Gap Matrix",
        "",
        f"Profiles directory: `{payload['profiles_dir']}`",
        f"Profiles: {payload['profile_count']}",
        f"Rows: {payload['row_count']}",
        f"Required source categories: {_join(payload.get('required_source_categories', []))}",
        f"Minimum evaluation weight: {payload['min_evaluation_weight']}",
        "",
    ]
    rows = payload.get("rows") or []
    if not rows:
        lines.append("No profiles found.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Profile | Domain | Status | Enabled categories | Missing categories | "
            "Enabled adapters | Disabled relevant adapters | Unknown adapters | "
            "Underweighted dimensions | Recommended adapters |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sorted(rows, key=lambda item: (item["profile_name"], item["domain"])):
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(row["profile_name"]),
                    _escape_markdown_cell(row["domain"]),
                    _escape_markdown_cell(row["status"]),
                    _escape_markdown_cell(_join(row["enabled_source_categories"])),
                    _escape_markdown_cell(_join(row["missing_source_categories"])),
                    _escape_markdown_cell(_join(row["enabled_adapters"])),
                    _escape_markdown_cell(_join(row["disabled_relevant_adapters"])),
                    _escape_markdown_cell(_join(row["unknown_adapters"])),
                    _escape_markdown_cell(_join(row["underweighted_evaluation_dimensions"])),
                    _escape_markdown_cell(_join(row["recommended_next_adapters"])),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def render_profile_gap_matrix_csv(matrix: ProfileGapMatrix | dict[str, Any]) -> str:
    """Render a profile gap matrix as deterministic CSV gap rows."""

    payload = matrix.to_dict() if isinstance(matrix, ProfileGapMatrix) else matrix
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(payload):
        writer.writerow(row)
    return output.getvalue()


def _load_profile_yaml(path: Path) -> PipelineProfile:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid profile YAML (expected dict): {path}")
    return PipelineProfile(**data)


def _build_row(
    profile: PipelineProfile,
    *,
    metadata: dict[str, AdapterMetadata],
    required_source_categories: list[str],
    min_evaluation_weight: float,
    max_recommended_adapters: int,
) -> ProfileGapMatrixRow:
    enabled_sources = [source for source in profile.sources if source.enabled]
    disabled_sources = [source for source in profile.sources if not source.enabled]
    enabled_adapters = sorted(_dedupe(source.adapter for source in enabled_sources))
    configured_adapters = {source.adapter for source in profile.sources}
    unknown_adapters = sorted(adapter for adapter in configured_adapters if adapter not in metadata)

    enabled_source_categories = sorted(
        {
            category
            for source in enabled_sources
            for category in _source_categories(source.adapter, metadata.get(source.adapter))
        }
    )
    disabled_relevant_adapters = sorted(
        source.adapter
        for source in disabled_sources
        if source.adapter in metadata
        and _is_relevant_disabled_source(
            source,
            metadata=metadata,
            enabled_source_categories=enabled_source_categories,
            profile=profile,
        )
    )
    missing_source_categories = sorted(
        category
        for category in required_source_categories
        if category not in enabled_source_categories
    )
    missing_adapters = _missing_adapters(
        metadata,
        missing_source_categories=missing_source_categories,
        configured_adapters=configured_adapters,
    )

    evaluation_weights = _evaluation_weights(profile)
    underweighted_dimensions = sorted(
        dimension
        for dimension in DEFAULT_WEIGHTS
        if float(evaluation_weights.get(dimension, 0.0)) < min_evaluation_weight
    )
    recommended = _recommended_next_adapters(
        disabled_relevant_adapters=disabled_relevant_adapters,
        missing_adapters=missing_adapters,
        max_recommended_adapters=max_recommended_adapters,
    )
    status = "ok"
    if missing_source_categories or unknown_adapters or underweighted_dimensions:
        status = "gaps"
    if unknown_adapters:
        status = "action_required"

    return ProfileGapMatrixRow(
        profile_name=profile.name,
        domain=profile.domain.name,
        enabled_source_categories=enabled_source_categories,
        missing_source_categories=missing_source_categories,
        enabled_adapters=enabled_adapters,
        disabled_relevant_adapters=disabled_relevant_adapters,
        unknown_adapters=unknown_adapters,
        missing_adapters=missing_adapters,
        evaluation_weight_profile=profile.evaluation.weight_profile,
        evaluation_weights=dict(sorted(evaluation_weights.items())),
        underweighted_evaluation_dimensions=underweighted_dimensions,
        recommended_next_adapters=recommended,
        status=status,
    )


def _registered_source_categories(metadata: dict[str, AdapterMetadata]) -> list[str]:
    categories: set[str] = set()
    for adapter, adapter_metadata in metadata.items():
        categories.update(_source_categories(adapter, adapter_metadata))
    return sorted(category for category in categories if category and category != "unknown")


def _source_categories(adapter: str, metadata: AdapterMetadata | None) -> list[str]:
    if metadata is None:
        return []
    explicit = _metadata_values(
        metadata,
        "source_categories",
        "categories",
        "source_category",
        "category",
    )
    if explicit:
        return explicit
    source_type = _metadata_value(metadata, "source_type") or _adapter_source_type(adapter)
    return [_adapter_category(adapter, metadata, source_type)]


def _csv_rows(matrix: dict[str, Any]) -> list[dict[str, str]]:
    metadata = get_adapter_metadata()
    rows: list[dict[str, str]] = []
    for profile_row in sorted(
        matrix.get("rows") or [],
        key=lambda item: (str(item.get("profile_name") or ""), str(item.get("domain") or "")),
    ):
        rows.extend(_profile_gap_csv_rows(profile_row, matrix, metadata))
    return rows


def _profile_gap_csv_rows(
    row: dict[str, Any],
    matrix: dict[str, Any],
    metadata: dict[str, AdapterMetadata],
) -> list[dict[str, str]]:
    csv_rows: list[dict[str, str]] = []
    enabled_categories = _string_list(row.get("enabled_source_categories"))
    min_weight = matrix.get("min_evaluation_weight", DEFAULT_MIN_EVALUATION_WEIGHT)

    for category in _string_list(row.get("missing_source_categories")):
        recommendations = _recommended_adapters_for_category(row, category, metadata)
        csv_rows.append(
            _csv_row(
                profile=row.get("profile_name"),
                category=category,
                source=_csv_join(recommendations),
                gap_type="missing_source_category",
                severity_or_score="high",
                observed_count="0",
                target_count="1",
                recommendation=_recommendation_text(
                    "Add or enable source coverage",
                    recommendations or [category],
                ),
                evidence_or_signal_references=_csv_join(
                    [
                        f"required_category:{category}",
                        f"enabled_categories:{_csv_join(enabled_categories)}",
                    ]
                ),
            )
        )

    for adapter in _string_list(row.get("disabled_relevant_adapters")):
        categories = _source_categories(adapter, metadata.get(adapter))
        csv_rows.append(
            _csv_row(
                profile=row.get("profile_name"),
                category=_csv_join(categories),
                source=adapter,
                gap_type="disabled_relevant_adapter",
                severity_or_score="medium",
                observed_count="0",
                target_count="1",
                recommendation=f"Enable adapter {adapter}",
                evidence_or_signal_references=_csv_join(
                    [
                        f"adapter_categories:{_csv_join(categories)}",
                        f"enabled_categories:{_csv_join(enabled_categories)}",
                    ]
                ),
            )
        )

    for adapter in _string_list(row.get("missing_adapters")):
        categories = _source_categories(adapter, metadata.get(adapter))
        csv_rows.append(
            _csv_row(
                profile=row.get("profile_name"),
                category=_csv_join(categories),
                source=adapter,
                gap_type="missing_adapter",
                severity_or_score="medium",
                observed_count="0",
                target_count="1",
                recommendation=f"Configure adapter {adapter}",
                evidence_or_signal_references=_csv_join(
                    [f"adapter_categories:{_csv_join(categories)}"]
                ),
            )
        )

    for adapter in _string_list(row.get("unknown_adapters")):
        csv_rows.append(
            _csv_row(
                profile=row.get("profile_name"),
                category="unknown",
                source=adapter,
                gap_type="unknown_adapter",
                severity_or_score="high",
                observed_count="1",
                target_count="0",
                recommendation=f"Register or remove adapter {adapter}",
                evidence_or_signal_references="configured adapter not found in registry",
            )
        )

    weights = row.get("evaluation_weights") or {}
    for dimension in _string_list(row.get("underweighted_evaluation_dimensions")):
        score = _float_text(weights.get(dimension, 0.0))
        csv_rows.append(
            _csv_row(
                profile=row.get("profile_name"),
                category="evaluation",
                source=dimension,
                gap_type="underweighted_evaluation_dimension",
                severity_or_score=score,
                observed_count=score,
                target_count=_float_text(min_weight),
                recommendation=f"Raise {dimension} evaluation weight",
                evidence_or_signal_references=f"weight_profile:{row.get('evaluation_weight_profile')}",
            )
        )

    return sorted(
        csv_rows,
        key=lambda item: (
            item["profile"],
            item["category"],
            item["source"],
            item["gap_type"],
        ),
    )


def _recommended_adapters_for_category(
    row: dict[str, Any],
    category: str,
    metadata: dict[str, AdapterMetadata],
) -> list[str]:
    candidates = _dedupe(
        [
            *_string_list(row.get("recommended_next_adapters")),
            *_string_list(row.get("disabled_relevant_adapters")),
            *_string_list(row.get("missing_adapters")),
        ]
    )
    return sorted(
        adapter
        for adapter in candidates
        if category in _source_categories(adapter, metadata.get(adapter))
    )


def _csv_row(**values: Any) -> dict[str, str]:
    return {column: _csv_text(values.get(column)) for column in CSV_COLUMNS}


def _recommendation_text(action: str, targets: list[str]) -> str:
    target_text = _csv_join(targets)
    return f"{action}: {target_text}" if target_text else action


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list | tuple | set):
        return _csv_join(_csv_text(item) for item in value)
    return str(value)


def _csv_join(values) -> str:
    return "; ".join(text for value in values if (text := _csv_text(value)))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple | set):
        return sorted(str(item) for item in value if str(item))
    return [str(value)]


def _float_text(value: Any) -> str:
    return f"{float(value):.2f}"


def _metadata_values(metadata: AdapterMetadata | None, *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        value = _metadata_value(metadata, name)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list | tuple | set):
            values.extend(item for item in value if isinstance(item, str))
    return sorted(_dedupe(item.strip() for item in values if item.strip()))


def _metadata_value(metadata: AdapterMetadata | None, name: str) -> Any:
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        return metadata.get(name)
    return getattr(metadata, name, None)


def _is_relevant_disabled_source(
    source: SourceConfig,
    *,
    metadata: dict[str, AdapterMetadata],
    enabled_source_categories: list[str],
    profile: PipelineProfile,
) -> bool:
    categories = set(_source_categories(source.adapter, metadata.get(source.adapter)))
    if categories - set(enabled_source_categories):
        return True
    searchable = " ".join(
        [
            source.adapter,
            " ".join(source.watchlist),
            str(source.params),
            profile.domain.name,
            " ".join(profile.domain.categories),
        ]
    ).casefold()
    description = str(_metadata_value(metadata.get(source.adapter), "description") or "").casefold()
    return any(term and term in description for term in _terms(searchable))


def _missing_adapters(
    metadata: dict[str, AdapterMetadata],
    *,
    missing_source_categories: list[str],
    configured_adapters: set[str],
) -> list[str]:
    missing_categories = set(missing_source_categories)
    candidates: list[str] = []
    for adapter, adapter_metadata in metadata.items():
        if adapter in configured_adapters:
            continue
        if missing_categories & set(_source_categories(adapter, adapter_metadata)):
            candidates.append(adapter)
    return sorted(candidates)


def _evaluation_weights(profile: PipelineProfile) -> dict[str, float]:
    if profile.evaluation.custom_weights:
        return dict(profile.evaluation.custom_weights)
    return dict(get_weights(profile.evaluation.weight_profile))


def _recommended_next_adapters(
    *,
    disabled_relevant_adapters: list[str],
    missing_adapters: list[str],
    max_recommended_adapters: int,
) -> list[str]:
    ordered = _dedupe([*disabled_relevant_adapters, *missing_adapters])
    return ordered[:max_recommended_adapters]


def _terms(value: str) -> list[str]:
    return [term for term in value.replace("_", " ").replace("-", " ").split() if len(term) >= 4]


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = str(value).casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(str(value))
    return deduped


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def _escape_markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
