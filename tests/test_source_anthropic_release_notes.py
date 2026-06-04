from __future__ import annotations

from max.sources.anthropic_release_notes import parse_anthropic_release_notes
from max.sources.registry import get_adapter_class


def test_anthropic_release_notes_parse_entries_with_metadata() -> None:
    signals = parse_anthropic_release_notes(
        [
            {
                "title": "Claude Sonnet 4.5 release",
                "url": "https://docs.anthropic.com/en/release-notes/claude-sonnet-4-5",
                "published_at": "2026-05-01T00:00:00Z",
                "summary": "Updated coding model behavior.",
                "model": "Claude Sonnet 4.5",
                "product": "Claude API",
                "category": "Models",
            },
            {
                "title": "Console usage controls",
                "url": "https://docs.anthropic.com/en/release-notes/console-usage",
                "date": "2026-04-15T00:00:00Z",
                "content": "New workspace controls.",
                "product": "Console",
            },
        ]
    )

    assert [signal.source_adapter for signal in signals] == ["anthropic_release_notes", "anthropic_release_notes"]
    assert signals[0].metadata["model"] == "Claude Sonnet 4.5"
    assert signals[0].metadata["product"] == "Claude API"
    assert signals[0].metadata["category"] == "Models"
    assert signals[0].published_at is not None
    assert signals[1].content == "New workspace controls."


def test_anthropic_release_notes_stable_ids_defaults_and_empty_payload() -> None:
    payload = [{"title": "API release", "url": "https://docs.anthropic.com/release-notes/api"}]

    first = parse_anthropic_release_notes(payload)[0]
    second = parse_anthropic_release_notes(payload)[0]

    assert first.id == second.id
    assert first.metadata == {"source_name": "Anthropic Release Notes"}
    assert parse_anthropic_release_notes({"entries": []}) == []


def test_anthropic_release_notes_registry_mapping() -> None:
    assert get_adapter_class("anthropic_release_notes").__name__ == "AnthropicReleaseNotesAdapter"
