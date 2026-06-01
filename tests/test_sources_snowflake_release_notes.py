from __future__ import annotations

import pytest

from max.sources.snowflake_release_notes import SnowflakeReleaseNotesAdapter, parse_snowflake_release_notes


def test_snowflake_release_notes_normal_parsing() -> None:
    signals = parse_snowflake_release_notes([{"title": "Warehouse update", "url": "https://docs.snowflake.com/release/warehouse", "summary": "Faster", "published_at": "2026-05-01T00:00:00Z"}])
    assert signals[0].source_adapter == "snowflake_release_notes"
    assert signals[0].content == "Faster"


def test_snowflake_release_notes_product_area_metadata() -> None:
    signal = parse_snowflake_release_notes([{"title": "Snowpark", "url": "https://docs.snowflake.com/release/snowpark", "product_area": "snowpark"}])[0]
    assert signal.metadata["product_area"] == "snowpark"


def test_snowflake_release_notes_missing_optional_fields_and_empty() -> None:
    signal = parse_snowflake_release_notes([{"title": "No summary", "url": "https://docs.snowflake.com/release/no-summary"}])[0]
    assert signal.content == ""
    assert parse_snowflake_release_notes([]) == []


@pytest.mark.asyncio
async def test_snowflake_release_notes_client_fetch_and_error_handling() -> None:
    class Client:
        def fetch_release_notes(self) -> list[dict[str, str]]:
            return [{"title": "A", "url": "https://snowflake/a"}]

    class BrokenClient:
        def fetch_release_notes(self) -> list[dict[str, str]]:
            raise RuntimeError("boom")

    assert len(await SnowflakeReleaseNotesAdapter(config={"client": Client()}).fetch()) == 1
    assert await SnowflakeReleaseNotesAdapter(config={"client": BrokenClient()}).fetch() == []
