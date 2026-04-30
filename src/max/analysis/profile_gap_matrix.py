"""Profile gap matrix analysis across available pipeline profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from max.analysis.profile_coverage import compute_profile_coverage_matrix
from max.profiles import loader as profile_loader
from max.store.db import Store


@dataclass(frozen=True)
class ProfileGapMatrixRow:
    """Coverage status for one configured profile term."""

    profile_name: str
    domain: str
    term: str
    term_type: str
    total_count: int
    status: str
    adapter_counts: dict[str, int]
    recommended_adapters: list[str]
    enabled_adapters: list[str]


@dataclass(frozen=True)
class ProfileGapMatrix:
    """Flattened coverage matrix for all available profile files."""

    profiles_dir: str
    low_coverage_threshold: int
    profile_count: int
    row_count: int
    rows: list[ProfileGapMatrixRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""

        return asdict(self)


def build_profile_gap_matrix(
    store: Store,
    *,
    profiles_dir: str | Path | None = None,
    low_coverage_threshold: int = 1,
) -> ProfileGapMatrix:
    """Build a flattened signal coverage gap matrix for all profile files."""

    if low_coverage_threshold < 1:
        raise ValueError("low_coverage_threshold must be at least 1")

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

    rows: list[ProfileGapMatrixRow] = []
    for profile_path in profile_paths:
        profile = profile_loader._load_yaml(profile_path)
        matrix = compute_profile_coverage_matrix(
            profile,
            store,
            low_coverage_threshold=low_coverage_threshold,
        )
        rows.extend(
            ProfileGapMatrixRow(
                profile_name=matrix.profile_name,
                domain=matrix.domain,
                term=row.term,
                term_type=row.term_type,
                total_count=row.total_count,
                status=row.status,
                adapter_counts=row.adapter_counts,
                recommended_adapters=row.recommended_adapters,
                enabled_adapters=matrix.enabled_adapters,
            )
            for row in matrix.rows
        )

    return ProfileGapMatrix(
        profiles_dir=str(resolved_profiles_dir),
        low_coverage_threshold=low_coverage_threshold,
        profile_count=len(profile_paths),
        row_count=len(rows),
        rows=rows,
    )


def render_profile_gap_matrix_markdown(matrix: ProfileGapMatrix | dict) -> str:
    """Render a profile gap matrix as markdown."""

    payload = matrix.to_dict() if isinstance(matrix, ProfileGapMatrix) else matrix
    lines = [
        "# Profile Gap Matrix",
        "",
        f"Profiles directory: `{payload['profiles_dir']}`",
        f"Profiles: {payload['profile_count']}",
        f"Rows: {payload['row_count']}",
        f"Low coverage threshold: {payload['low_coverage_threshold']}",
        "",
    ]
    rows = payload.get("rows") or []
    if not rows:
        lines.append("No profile coverage rows found.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Profile | Domain | Term | Type | Count | Status | Adapter counts | Recommended adapters |",
            "| --- | --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for row in rows:
        adapter_counts = ", ".join(
            f"{adapter}={count}" for adapter, count in row["adapter_counts"].items()
        )
        recommended = ", ".join(row["recommended_adapters"]) or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(row["profile_name"]),
                    _escape_markdown_cell(row["domain"]),
                    _escape_markdown_cell(row["term"]),
                    _escape_markdown_cell(row["term_type"]),
                    str(row["total_count"]),
                    _escape_markdown_cell(row["status"]),
                    _escape_markdown_cell(adapter_counts or "-"),
                    _escape_markdown_cell(recommended),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _escape_markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
