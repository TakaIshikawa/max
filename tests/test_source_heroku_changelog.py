from __future__ import annotations

from max.sources.heroku_changelog import parse_heroku_changelog


def test_heroku_changelog_runtime_and_platform_entries() -> None:
    signals = parse_heroku_changelog([{"title": "Runtime update", "url": "https://devcenter.heroku.com/changelog/a", "runtime": "heroku-24", "product_area": "runtime"}])
    assert signals[0].metadata["runtime"] == "heroku-24"
    assert signals[0].metadata["product_area"] == "runtime"


def test_heroku_changelog_missing_summaries() -> None:
    signal = parse_heroku_changelog([{"title": "A", "url": "https://heroku.com/a"}])[0]
    assert signal.content == ""


def test_heroku_changelog_deterministic_ids_and_empty_responses() -> None:
    payload = [{"title": "A", "url": "https://heroku.com/a"}]
    assert parse_heroku_changelog(payload)[0].id == parse_heroku_changelog(payload)[0].id
    assert parse_heroku_changelog("bad") == []
