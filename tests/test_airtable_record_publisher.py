"""Compatibility tests for Airtable record publishing."""

from __future__ import annotations

from max.publisher.airtable_records import AirtableRecordPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-airtable-custom001",
            "domain": "design-tools",
        },
        "project": {
            "title": "Airtable Custom Fields",
            "summary": "Override default Airtable field names.",
        },
        "quality": {"quality_score": 8.0},
    }


def test_airtable_table_id_or_name_env_and_custom_field_mapping(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIRTABLE_BASE_ID", "app-env")
    monkeypatch.setenv("AIRTABLE_TABLE_ID_OR_NAME", "tbl-env")
    monkeypatch.setenv("AIRTABLE_FIELD_MAPPING", '{"Title":"Name","Source ID":"External ID"}')

    publisher = AirtableRecordPublisher.from_env()
    payload = publisher.build_idea_payload(_tact_spec()).to_dict()

    assert publisher.table == "tbl-env"
    assert payload["fields"]["Name"] == "Airtable Custom Fields"
    assert payload["fields"]["External ID"] == "bu-airtable-custom001"
    assert "Title" not in payload["fields"]
    assert "Source ID" not in payload["fields"]
