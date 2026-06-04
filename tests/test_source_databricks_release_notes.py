from __future__ import annotations

from max.sources.databricks_release_notes import parse_databricks_release_notes


def test_databricks_release_note_parsing() -> None:
    signals = parse_databricks_release_notes([{"title": "Model serving release", "url": "https://docs.databricks.com/release-notes/a", "release_area": "Model Serving"}])

    assert signals[0].source_adapter == "databricks_release_notes"
    assert signals[0].metadata["release_area"] == "Model Serving"


def test_databricks_product_tag_extraction() -> None:
    tags = parse_databricks_release_notes([{"title": "SQL update", "url": "https://docs.databricks.com/release-notes/sql", "product": "SQL"}])[0].tags

    assert {"databricks", "data-platform", "ai-infrastructure", "sql"}.issubset(tags)


def test_databricks_empty_results() -> None:
    assert parse_databricks_release_notes(None) == []
