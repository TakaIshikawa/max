from __future__ import annotations

from max.sources.google_cloud_release_notes import parse_google_cloud_release_notes


def test_google_cloud_release_notes_product_extraction_and_dates() -> None:
    signals = parse_google_cloud_release_notes([{"title": "Cloud Run release", "url": "https://cloud.google.com/run/docs/release-notes#1", "date": "2026-02-01T00:00:00Z", "product": "Cloud Run"}])
    assert signals[0].metadata["product"] == "Cloud Run"
    assert signals[0].published_at is not None


def test_google_cloud_release_notes_multiple_products_and_empty() -> None:
    signals = parse_google_cloud_release_notes([{"title": "A", "url": "https://cloud.google.com/a", "product": "A"}, {"title": "B", "url": "https://cloud.google.com/b", "product": "B"}])
    assert [signal.metadata["product"] for signal in signals] == ["A", "B"]
    assert parse_google_cloud_release_notes({"entries": []}) == []


def test_google_cloud_release_notes_stable_ids() -> None:
    payload = [{"title": "A", "url": "https://cloud.google.com/a"}]
    assert parse_google_cloud_release_notes(payload)[0].id == parse_google_cloud_release_notes(payload)[0].id
