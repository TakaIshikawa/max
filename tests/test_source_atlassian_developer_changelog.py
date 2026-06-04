from __future__ import annotations

from max.sources.atlassian_developer_changelog import parse_atlassian_developer_changelog


def test_atlassian_changelog_extracts_product_area() -> None:
    signals = parse_atlassian_developer_changelog([{"title": "Jira platform update", "url": "https://developer.atlassian.com/changelog/a", "product": "Jira"}])

    assert signals[0].metadata["product_area"] == "Jira"
    assert "jira" in signals[0].tags


def test_atlassian_changelog_successful_parsing() -> None:
    signals = parse_atlassian_developer_changelog([{"title": "Confluence API", "url": "https://developer.atlassian.com/changelog/b", "summary": "API changed."}])

    assert signals[0].source_adapter == "atlassian_developer_changelog"
    assert signals[0].content == "API changed."


def test_atlassian_changelog_ignores_malformed_entries() -> None:
    assert parse_atlassian_developer_changelog([{"title": "missing url"}, object()]) == []
