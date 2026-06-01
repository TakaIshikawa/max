from __future__ import annotations

from max.sources.azure_updates import parse_azure_updates


def test_azure_updates_preserves_ga_preview_and_category_metadata() -> None:
    signals = parse_azure_updates([{"title": "AKS GA", "url": "https://azure.microsoft.com/updates/a", "status": "GA", "update_type": "generally available", "category": "containers"}])
    assert signals[0].metadata["status"] == "GA"
    assert signals[0].metadata["category"] == "containers"


def test_azure_updates_missing_dates_and_stable_ids() -> None:
    payload = [{"title": "Preview", "url": "https://azure.microsoft.com/updates/p", "status": "preview"}]
    signal = parse_azure_updates(payload)[0]
    assert signal.published_at is None
    assert signal.id == parse_azure_updates(payload)[0].id


def test_azure_updates_empty_payloads() -> None:
    assert parse_azure_updates([]) == []
