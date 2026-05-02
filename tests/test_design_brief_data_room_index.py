"""Tests for design brief data-room index generation."""

from __future__ import annotations

import csv
import io
import json

import pytest

from max.analysis.design_brief_data_room_index import (
    CSV_COLUMNS,
    SCHEMA_VERSION,
    build_design_brief_data_room_index,
    data_room_index_filename,
    render_design_brief_data_room_index,
)
from max.store.db import Store
from tests.test_design_brief_bundle import _seed_design_brief


def test_build_design_brief_data_room_index_advertises_csv_format(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        index = build_design_brief_data_room_index(store, brief_id)
    finally:
        store.close()

    assert index is not None
    assert index["schema_version"] == SCHEMA_VERSION
    assert index["kind"] == "max.design_brief.data_room_index"
    assert index["design_brief"]["id"] == brief_id
    assert index["summary"]["available_formats"] == ["json", "markdown", "csv"]
    assert index["summary"]["artifact_count"] == len(index["artifacts"])
    assert index["summary"]["section_count"] == len(index["sections"])


def test_render_design_brief_data_room_index_csv_headers_rows_and_ordering(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        index = build_design_brief_data_room_index(store, brief_id)
    finally:
        store.close()

    assert index is not None
    csv_text = render_design_brief_data_room_index(index, fmt="csv")
    repeated = render_design_brief_data_room_index(index, fmt="csv")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    assert csv_text == repeated
    assert reader.fieldnames == list(CSV_COLUMNS)
    assert csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert len(rows) == len(index["artifacts"])
    assert [row["section"] for row in rows] == [
        "core",
        "handoff",
        "validation",
        "validation",
        "risk",
        "delivery",
        "delivery",
        "commercial",
        "commercial",
    ]
    assert rows[0] == {
        "design_brief_id": brief_id,
        "design_brief_title": "Bundle Export Brief",
        "section": "core",
        "artifact_key": "design_brief",
        "artifact_title": "Design Brief",
        "description": "Canonical persisted brief and source idea context.",
        "json_url": f"/api/v1/design-briefs/{brief_id}",
        "markdown_url": f"/api/v1/design-briefs/{brief_id}.md",
        "available_formats": "json; markdown",
    }
    bundle = next(row for row in rows if row["artifact_key"] == "bundle")
    assert bundle["json_url"] == f"/api/v1/design-briefs/{brief_id}/bundle"
    assert bundle["markdown_url"] == f"/api/v1/design-briefs/{brief_id}/bundle.md"


def test_data_room_index_filename_supports_csv_extension() -> None:
    design_brief = {"id": "dbf-123:alpha"}

    assert data_room_index_filename(design_brief) == "dbf-123-alpha-data-room-index.md"
    assert (
        data_room_index_filename(design_brief, fmt="json")
        == "dbf-123-alpha-data-room-index.json"
    )
    assert (
        data_room_index_filename(design_brief, fmt="csv")
        == "dbf-123-alpha-data-room-index.csv"
    )


def test_render_design_brief_data_room_index_csv_does_not_change_json_or_markdown(
    tmp_path,
) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        index = build_design_brief_data_room_index(store, brief_id)
    finally:
        store.close()

    assert index is not None
    markdown = render_design_brief_data_room_index(index)
    rendered_json = render_design_brief_data_room_index(index, fmt="json")

    render_design_brief_data_room_index(index, fmt="csv")

    assert render_design_brief_data_room_index(index) == markdown
    assert render_design_brief_data_room_index(index, fmt="json") == rendered_json
    assert json.loads(rendered_json) == index
    assert markdown.startswith("# Data Room Index: Bundle Export Brief")
    assert f"Design brief: `{brief_id}`" in markdown


def test_render_design_brief_data_room_index_invalid_format(tmp_path) -> None:
    store, brief_id = _store_with_brief(tmp_path)
    try:
        index = build_design_brief_data_room_index(store, brief_id)
    finally:
        store.close()

    assert index is not None
    with pytest.raises(ValueError, match="Unsupported data room index format: yaml"):
        render_design_brief_data_room_index(index, fmt="yaml")


def test_build_design_brief_data_room_index_missing_brief_returns_none(tmp_path) -> None:
    store = Store(db_path=str(tmp_path / "missing_data_room_index.db"), wal_mode=True)
    try:
        index = build_design_brief_data_room_index(store, "dbf-missing")
    finally:
        store.close()

    assert index is None


def _store_with_brief(tmp_path) -> tuple[Store, str]:
    store = Store(db_path=str(tmp_path / "design_brief_data_room_index.db"), wal_mode=True)
    return store, _seed_design_brief(store)
