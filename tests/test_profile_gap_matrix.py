"""Tests for profile gap matrix analysis."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from max.analysis import profile_gap_matrix

CSV_COLUMNS = [
    "profile",
    "category",
    "source",
    "gap_type",
    "severity_or_score",
    "observed_count",
    "target_count",
    "recommendation",
    "evidence_or_signal_references",
]


def _write_profile(
    profiles_dir: Path,
    name: str,
    *,
    sources: list[dict],
    custom_weights: dict[str, float] | None = None,
) -> None:
    evaluation: dict[str, object] = {"weight_profile": "default"}
    if custom_weights is not None:
        evaluation = {
            "weight_profile": "custom",
            "custom_weights": custom_weights,
        }
    payload = {
        "name": name,
        "domain": {
            "name": f"{name}-domain",
            "description": f"{name} test domain",
            "categories": ["workflow automation"],
            "target_user_types": ["developers"],
        },
        "sources": sources,
        "evaluation": evaluation,
    }
    (profiles_dir / f"{name}.yaml").write_text(
        yaml.safe_dump(payload),
        encoding="utf-8",
    )


@pytest.fixture
def profiles_dir(tmp_path: Path) -> Path:
    path = tmp_path / "profiles"
    path.mkdir()
    _write_profile(
        path,
        "devtools",
        sources=[
            {"adapter": "hackernews", "enabled": True, "watchlist": ["mcp"]},
            {"adapter": "github_issues", "enabled": False, "watchlist": ["bugs"]},
            {"adapter": "ghost_adapter", "enabled": True, "watchlist": ["unknown"]},
        ],
        custom_weights={
            "pain_severity": 0.40,
            "addressable_scale": 0.20,
            "build_effort": 0.20,
            "composability": 0.10,
            "competitive_density": 0.05,
            "timing_fit": 0.05,
        },
    )
    _write_profile(
        path,
        "security",
        sources=[
            {"adapter": "security_advisories", "enabled": True},
            {"adapter": "reddit", "enabled": False, "watchlist": ["supply chain"]},
        ],
    )
    (path / "schema.yaml").write_text("type: object\n", encoding="utf-8")
    return path


@pytest.fixture
def adapter_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = {
        "hackernews": SimpleNamespace(
            name="hackernews",
            config_keys=["filter_keywords"],
            required_keys=[],
            description="Forum and community posts.",
            source_categories=["forum"],
        ),
        "github_issues": SimpleNamespace(
            name="github_issues",
            config_keys=["queries"],
            required_keys=[],
            description="Code hosting issue threads.",
            source_categories=["code_hosting"],
        ),
        "security_advisories": SimpleNamespace(
            name="security_advisories",
            config_keys=["ecosystems"],
            required_keys=[],
            description="Security advisory feeds.",
            source_categories=["security_feed"],
        ),
        "reddit": SimpleNamespace(
            name="reddit",
            config_keys=["subreddits"],
            required_keys=[],
            description="Forum and community posts.",
            source_categories=["forum"],
        ),
        "product_hunt": SimpleNamespace(
            name="product_hunt",
            config_keys=["topics"],
            required_keys=[],
            description="Product marketplace launches.",
            source_categories=["marketplace"],
        ),
    }
    monkeypatch.setattr(profile_gap_matrix, "get_adapter_metadata", lambda: metadata)


def test_build_profile_gap_matrix_returns_one_row_per_profile_with_gap_fields(
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    matrix = profile_gap_matrix.build_profile_gap_matrix(profiles_dir=profiles_dir)

    rows = {row.profile_name: row for row in matrix.rows}
    assert matrix.profiles_dir == str(profiles_dir)
    assert matrix.profile_count == 2
    assert matrix.row_count == 2
    assert matrix.required_source_categories == [
        "code_hosting",
        "forum",
        "marketplace",
        "security_feed",
    ]

    devtools = rows["devtools"]
    assert devtools.enabled_source_categories == ["forum"]
    assert devtools.missing_source_categories == [
        "code_hosting",
        "marketplace",
        "security_feed",
    ]
    assert devtools.enabled_adapters == ["ghost_adapter", "hackernews"]
    assert devtools.disabled_relevant_adapters == ["github_issues"]
    assert devtools.unknown_adapters == ["ghost_adapter"]
    assert devtools.underweighted_evaluation_dimensions == [
        "competitive_density",
        "compounding_value",
        "timing_fit",
    ]
    assert devtools.recommended_next_adapters == [
        "github_issues",
        "product_hunt",
        "security_advisories",
    ]
    assert devtools.status == "action_required"

    security = rows["security"]
    assert security.enabled_source_categories == ["security_feed"]
    assert security.disabled_relevant_adapters == ["reddit"]
    assert security.unknown_adapters == []
    assert security.status == "gaps"


def test_build_profile_gap_matrix_separates_disabled_relevant_from_missing_adapters(
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    matrix = profile_gap_matrix.build_profile_gap_matrix(
        profiles_dir=profiles_dir,
        required_source_categories=["forum", "code_hosting", "marketplace", "security_feed"],
    )

    devtools = next(row for row in matrix.rows if row.profile_name == "devtools")

    assert devtools.disabled_relevant_adapters == ["github_issues"]
    assert devtools.missing_adapters == ["product_hunt", "security_advisories"]
    assert "ghost_adapter" not in devtools.disabled_relevant_adapters
    assert "ghost_adapter" not in devtools.missing_adapters


def test_render_profile_gap_matrix_markdown_includes_deterministic_table(
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    matrix = profile_gap_matrix.build_profile_gap_matrix(profiles_dir=profiles_dir)

    markdown = profile_gap_matrix.render_profile_gap_matrix_markdown(matrix)

    assert markdown.startswith("# Profile Gap Matrix")
    assert (
        "| Profile | Domain | Status | Enabled categories | Missing categories |"
        in markdown
    )
    assert (
        "| devtools | devtools-domain | action_required | forum | "
        "code_hosting, marketplace, security_feed | ghost_adapter, hackernews | "
        "github_issues | ghost_adapter | competitive_density, compounding_value, timing_fit | "
        "github_issues, product_hunt, security_advisories |"
        in markdown
    )
    assert markdown.index("| devtools |") < markdown.index("| security |")


def test_render_profile_gap_matrix_supports_json_format_without_changing_payload(
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    matrix = profile_gap_matrix.build_profile_gap_matrix(profiles_dir=profiles_dir)

    rendered = profile_gap_matrix.render_profile_gap_matrix(matrix, fmt="json")

    assert json.loads(rendered) == matrix.to_dict()


def test_render_profile_gap_matrix_csv_has_stable_header_and_multiple_gap_rows(
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    matrix = profile_gap_matrix.build_profile_gap_matrix(profiles_dir=profiles_dir)

    csv_text = profile_gap_matrix.render_profile_gap_matrix(matrix, fmt="csv")
    rows = list(csv.DictReader(StringIO(csv_text)))

    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) > matrix.row_count
    assert rows[0] == {
        "profile": "devtools",
        "category": "code_hosting",
        "source": "github_issues",
        "gap_type": "disabled_relevant_adapter",
        "severity_or_score": "medium",
        "observed_count": "0",
        "target_count": "1",
        "recommendation": "Enable adapter github_issues",
        "evidence_or_signal_references": (
            "adapter_categories:code_hosting; enabled_categories:forum"
        ),
    }
    assert {
        "profile": "devtools",
        "category": "code_hosting",
        "source": "github_issues",
        "gap_type": "missing_source_category",
        "severity_or_score": "high",
        "observed_count": "0",
        "target_count": "1",
        "recommendation": "Add or enable source coverage: github_issues",
        "evidence_or_signal_references": (
            "required_category:code_hosting; enabled_categories:forum"
        ),
    } in rows
    assert {
        "profile": "devtools",
        "category": "unknown",
        "source": "ghost_adapter",
        "gap_type": "unknown_adapter",
        "severity_or_score": "high",
        "observed_count": "1",
        "target_count": "0",
        "recommendation": "Register or remove adapter ghost_adapter",
        "evidence_or_signal_references": "configured adapter not found in registry",
    } in rows
    assert {
        "profile": "devtools",
        "category": "evaluation",
        "source": "competitive_density",
        "gap_type": "underweighted_evaluation_dimension",
        "severity_or_score": "0.05",
        "observed_count": "0.05",
        "target_count": "0.10",
        "recommendation": "Raise competitive_density evaluation weight",
        "evidence_or_signal_references": "weight_profile:custom",
    } in rows


def test_render_profile_gap_matrix_csv_is_deterministic(
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    matrix = profile_gap_matrix.build_profile_gap_matrix(profiles_dir=profiles_dir)

    first = profile_gap_matrix.render_profile_gap_matrix_csv(matrix)
    second = profile_gap_matrix.render_profile_gap_matrix(matrix.to_dict(), fmt="csv")

    assert first == second
    assert first.index("devtools,code_hosting,github_issues,disabled_relevant_adapter") < (
        first.index("security,forum,reddit,disabled_relevant_adapter")
    )


def test_render_profile_gap_matrix_rejects_unsupported_format(
    profiles_dir: Path,
    adapter_metadata: None,
) -> None:
    matrix = profile_gap_matrix.build_profile_gap_matrix(profiles_dir=profiles_dir)

    with pytest.raises(ValueError, match="Unsupported profile gap matrix format"):
        profile_gap_matrix.render_profile_gap_matrix(matrix, fmt="yaml")


def test_build_profile_gap_matrix_rejects_invalid_profiles_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Profile directory not found"):
        profile_gap_matrix.build_profile_gap_matrix(profiles_dir=tmp_path / "missing")
