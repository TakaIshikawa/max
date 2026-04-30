"""Tests for profile gap matrix analysis."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from max.analysis.profile_gap_matrix import (
    build_profile_gap_matrix,
    render_profile_gap_matrix_markdown,
)
from max.types.signal import Signal, SignalSourceType


def _write_profile(
    profiles_dir: Path,
    name: str,
    *,
    adapter: str,
    categories: list[str],
    watchlist: list[str],
) -> None:
    payload = {
        "name": name,
        "domain": {
            "name": f"{name}-domain",
            "description": f"{name} test domain",
            "categories": categories,
            "target_user_types": ["developers"],
        },
        "sources": [
            {
                "adapter": adapter,
                "enabled": True,
                "watchlist": watchlist,
            }
        ],
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
        adapter="hackernews",
        categories=["workflow automation"],
        watchlist=["mcp"],
    )
    _write_profile(
        path,
        "security",
        adapter="reddit",
        categories=["supply chain"],
        watchlist=["dependency risk"],
    )
    (path / "schema.yaml").write_text("type: object\n", encoding="utf-8")
    return path


def test_build_profile_gap_matrix_returns_rows_for_available_profiles(
    store,
    profiles_dir: Path,
) -> None:
    store.insert_signal(
        Signal(
            id="sig-mcp",
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="MCP workflow automation",
            content="Agents need better tool coverage.",
            url="https://example.com/mcp",
        )
    )

    matrix = build_profile_gap_matrix(store, profiles_dir=profiles_dir)

    rows = {(row.profile_name, row.term): row for row in matrix.rows}
    assert matrix.profiles_dir == str(profiles_dir)
    assert matrix.profile_count == 2
    assert matrix.row_count == 4
    assert ("devtools", "mcp") in rows
    assert ("security", "dependency risk") in rows
    assert rows[("devtools", "mcp")].status == "covered"
    assert rows[("security", "dependency risk")].status == "undercovered"
    assert rows[("security", "dependency risk")].recommended_adapters == ["reddit"]


def test_render_profile_gap_matrix_markdown_includes_matrix_rows(
    store,
    profiles_dir: Path,
) -> None:
    matrix = build_profile_gap_matrix(store, profiles_dir=profiles_dir)

    markdown = render_profile_gap_matrix_markdown(matrix)

    assert markdown.startswith("# Profile Gap Matrix")
    assert "| Profile | Domain | Term | Type | Count | Status |" in markdown
    assert "| devtools | devtools-domain | mcp | watchlist | 0 | undercovered |" in markdown


def test_build_profile_gap_matrix_rejects_invalid_profiles_dir(store, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Profile directory not found"):
        build_profile_gap_matrix(store, profiles_dir=tmp_path / "missing")
