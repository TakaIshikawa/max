"""Tests for profile gap matrix exposed through MCP."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from max.server.mcp_tools import (
    create_mcp_server,
    get_profile_gap_matrix,
    profile_gap_matrix_detail,
    set_store_factory,
)
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_profile_gap_db(tmp_path):
    db_path = str(tmp_path / "mcp_profile_gap_matrix.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def profiles_dir(tmp_path: Path) -> Path:
    path = tmp_path / "profiles"
    path.mkdir()
    _write_profile(path, "devtools", "hackernews", ["workflow automation"], ["mcp"])
    _write_profile(path, "security", "reddit", ["supply chain"], ["dependency risk"])
    return path


def _write_profile(
    profiles_dir: Path,
    name: str,
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


def test_get_profile_gap_matrix_returns_structured_rows(
    mcp_profile_gap_db,
    profiles_dir: Path,
) -> None:
    with Store(db_path=mcp_profile_gap_db, wal_mode=True) as store:
        store.insert_signal(
            Signal(
                id="sig-mcp",
                source_type=SignalSourceType.FORUM,
                source_adapter="hackernews",
                title="MCP coverage",
                content="Profile matrix coverage",
                url="https://example.com/mcp",
            )
        )

    result = get_profile_gap_matrix(profile_dir=str(profiles_dir))

    assert result["profiles_dir"] == str(profiles_dir)
    assert result["profile_count"] == 2
    assert result["row_count"] == 4
    rows = {(row["profile_name"], row["term"]): row for row in result["rows"]}
    assert rows[("devtools", "mcp")]["status"] == "covered"
    assert rows[("security", "dependency risk")]["recommended_adapters"] == ["reddit"]


def test_get_profile_gap_matrix_markdown_mode(
    mcp_profile_gap_db,
    profiles_dir: Path,
) -> None:
    result = get_profile_gap_matrix(
        profile_dir=str(profiles_dir),
        format="markdown",
    )

    assert result["format"] == "markdown"
    assert result["profile_count"] == 2
    assert "# Profile Gap Matrix" in result["markdown"]
    assert "| devtools | devtools-domain | mcp | watchlist | 0 | undercovered |" in result["markdown"]


def test_get_profile_gap_matrix_invalid_profile_dir_returns_tool_error(
    mcp_profile_gap_db,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-profiles"

    result = get_profile_gap_matrix(profile_dir=str(missing))

    assert result["error"] == f"Profile directory not found: {missing}"
    assert result["code"] == 400
    assert result["details"]["field"] == "profile_dir"
    assert result["details"]["expected"] == "existing profiles directory"


def test_profile_gap_matrix_resource_returns_json(
    mcp_profile_gap_db,
    profiles_dir: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("max.profiles.loader.get_profiles_dir", lambda: profiles_dir)

    result = profile_gap_matrix_detail()

    assert '"profile_count": 2' in result
    assert '"row_count": 4' in result


def test_create_mcp_server_registers_profile_gap_matrix(monkeypatch) -> None:
    class FakeMCP:
        latest = None

        def __init__(self, name):
            self.name = name
            self.tools = []
            self.resources = {}
            FakeMCP.latest = self

        def tool(self, fn):
            self.tools.append(fn.__name__)
            return fn

        def resource(self, uri):
            def decorator(fn):
                self.resources[uri] = fn.__name__
                return fn

            return decorator

    monkeypatch.setattr("max.server.mcp_tools.FastMCP", FakeMCP)

    create_mcp_server()

    assert "get_profile_gap_matrix" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["profile-gap-matrix://all"]
        == "profile_gap_matrix_detail"
    )
