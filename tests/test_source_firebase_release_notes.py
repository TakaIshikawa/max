from __future__ import annotations

from max.sources.firebase_release_notes import parse_firebase_release_notes
from max.sources.registry import get_adapter_class


def test_firebase_release_notes_parse_metadata_and_dates() -> None:
    signals = parse_firebase_release_notes(
        [
            {
                "title": "Firebase Auth web SDK update",
                "url": "https://firebase.google.com/support/release-notes/js#auth",
                "published_at": "2026-05-03T00:00:00Z",
                "summary": "Auth SDK fixes.",
                "product": "Authentication",
                "platform": "Web",
                "release_note_type": "fix",
            },
            {
                "title": "Firestore Android release",
                "url": "https://firebase.google.com/support/release-notes/android#firestore",
                "content": "Firestore update.",
                "product": "Firestore",
                "platform": "Android",
            },
        ]
    )

    assert signals[0].metadata["product"] == "Authentication"
    assert signals[0].metadata["platform"] == "Web"
    assert signals[0].metadata["release_note_type"] == "fix"
    assert signals[0].published_at is not None
    assert signals[1].content == "Firestore update."


def test_firebase_release_notes_stable_ids_defaults_empty_and_registry() -> None:
    payload = [{"title": "Hosting release", "url": "https://firebase.google.com/support/release-notes/hosting"}]

    assert parse_firebase_release_notes(payload)[0].id == parse_firebase_release_notes(payload)[0].id
    assert parse_firebase_release_notes(payload)[0].metadata == {"source_name": "Firebase Release Notes"}
    assert parse_firebase_release_notes({"entries": []}) == []
    assert get_adapter_class("firebase_release_notes").__name__ == "FirebaseReleaseNotesAdapter"
