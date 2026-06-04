from __future__ import annotations

import pytest

from max.sources.django_weblog import DjangoWeblogAdapter, parse_django_weblog
from max.sources.registry import get_adapter, reload_registry


def test_parse_django_weblog_accepts_payload_shapes_and_preserves_metadata() -> None:
    payload = {
        "items": [
            {
                "title": "Django 6.0 alpha released",
                "url": "https://www.djangoproject.com/weblog/2026/may/01/django-60-alpha/",
                "category": "releases",
                "author": "Django Software Foundation",
                "tags": ["release", "async"],
            }
        ]
    }

    signal = parse_django_weblog(payload)[0]

    assert signal.source_adapter == "django_weblog"
    assert signal.metadata["category"] == "releases"
    assert signal.metadata["author"] == "Django Software Foundation"
    assert signal.metadata["tags"] == ["release", "async"]
    assert signal.author == "Django Software Foundation"
    assert signal.id == parse_django_weblog(payload)[0].id
    assert parse_django_weblog({"entries": []}) == []
    assert parse_django_weblog({"results": [{"title": "A", "link": "https://djangoproject.com/a"}]})


@pytest.mark.asyncio
async def test_django_weblog_fetch_caps_limit() -> None:
    adapter = DjangoWeblogAdapter(
        config={
            "entries": [
                {"title": "One", "url": "https://www.djangoproject.com/weblog/one/"},
                {"title": "Two", "url": "https://www.djangoproject.com/weblog/two/"},
            ]
        }
    )

    assert [signal.title for signal in await adapter.fetch(limit=1)] == ["One"]


def test_django_weblog_registry_instantiates_adapter() -> None:
    reload_registry()
    assert isinstance(get_adapter("django_weblog"), DjangoWeblogAdapter)
