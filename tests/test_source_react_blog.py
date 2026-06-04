from __future__ import annotations

from max.sources.react_blog import ReactBlogAdapter, parse_react_blog
from max.sources.registry import get_adapter, reload_registry


def test_parse_react_blog_preserves_release_metadata_and_stable_ids() -> None:
    payload = [
        {
            "title": "React Compiler RC",
            "url": "https://react.dev/blog/compiler-rc",
            "release_channel": "rc",
            "react_version": "19.2",
            "tags": ["compiler"],
            "author": "React Team",
        }
    ]

    signal = parse_react_blog(payload)[0]

    assert signal.source_adapter == "react_blog"
    assert signal.metadata["release_channel"] == "rc"
    assert signal.metadata["react_version"] == "19.2"
    assert signal.metadata["tags"] == ["compiler"]
    assert signal.metadata["author"] == "React Team"
    assert signal.id == parse_react_blog(payload)[0].id


def test_react_blog_registry_instantiates_adapter() -> None:
    reload_registry()
    assert isinstance(get_adapter("react_blog"), ReactBlogAdapter)
