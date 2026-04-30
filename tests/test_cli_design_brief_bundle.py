"""CLI tests for persisted design brief bundle export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from max.analysis.design_brief_bundle import SCHEMA_VERSION
from max.cli import main
from max.store.db import Store
from tests.test_design_brief_bundle import _seed_design_brief


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def design_brief_bundle_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "cli_design_brief_bundle.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        brief_id = _seed_design_brief(store)
    return db_path, brief_id


@pytest.fixture
def persisted_store(
    monkeypatch: pytest.MonkeyPatch,
    design_brief_bundle_db: tuple[str, str],
) -> tuple[str, str]:
    db_path, brief_id = design_brief_bundle_db
    monkeypatch.setattr("max.store.db.Store", lambda: Store(db_path=db_path, wal_mode=True))
    return db_path, brief_id


def test_design_brief_bundle_prints_markdown_by_default(
    runner: CliRunner,
    persisted_store: tuple[str, str],
) -> None:
    _db_path, brief_id = persisted_store

    result = runner.invoke(main, ["design-brief-bundle", brief_id])

    assert result.exit_code == 0, result.output
    assert result.output.startswith("# Design Brief Bundle: Bundle Export Brief")
    assert "## Artifact Status" in result.output
    assert "## PRD" in result.output
    assert "## Competitive Landscape" in result.output


def test_design_brief_bundle_prints_json(
    runner: CliRunner,
    persisted_store: tuple[str, str],
) -> None:
    _db_path, brief_id = persisted_store

    result = runner.invoke(main, ["design-brief-bundle", brief_id, "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["design_brief"]["id"] == brief_id
    assert payload["blueprint_source_brief"]["design_brief"]["id"] == brief_id
    assert payload["artifact_status"]["prd"]["status"] == "generated"


def test_design_brief_bundle_output_writes_rendered_bundle_and_reports_path(
    runner: CliRunner,
    persisted_store: tuple[str, str],
    tmp_path: Path,
) -> None:
    _db_path, brief_id = persisted_store
    output_path = tmp_path / "out" / "design-brief-bundle.md"

    result = runner.invoke(
        main,
        [
            "design-brief-bundle",
            brief_id,
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == f"Wrote design brief bundle to {output_path}\n"
    rendered = output_path.read_text(encoding="utf-8")
    assert rendered.startswith("# Design Brief Bundle: Bundle Export Brief")
    assert "## Validation Plan" in rendered


def test_design_brief_bundle_missing_brief_exits_nonzero(
    runner: CliRunner,
    persisted_store: tuple[str, str],
) -> None:
    result = runner.invoke(main, ["design-brief-bundle", "dbf-missing"])

    assert result.exit_code != 0
    assert "Design brief not found: dbf-missing" in result.output

