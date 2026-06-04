from __future__ import annotations

from max.sources.docker_desktop_release_notes import (
    DockerDesktopReleaseNotesAdapter,
    parse_docker_desktop_release_notes,
)
from max.sources.registry import get_adapter, reload_registry


def test_parse_docker_desktop_release_notes_handles_shapes_and_metadata() -> None:
    payload = {
        "entries": [
            {
                "title": "Docker Desktop 4.40",
                "url": "https://docs.docker.com/desktop/release-notes/#440",
                "version": "4.40",
                "platform": "macOS",
                "channel": "stable",
                "component": "containers",
            }
        ]
    }

    signal = parse_docker_desktop_release_notes(payload)[0]

    assert signal.metadata["version"] == "4.40"
    assert signal.metadata["platform"] == "macOS"
    assert signal.metadata["channel"] == "stable"
    assert signal.metadata["component"] == "containers"
    assert signal.id == parse_docker_desktop_release_notes(payload)[0].id
    assert parse_docker_desktop_release_notes({"items": []}) == []


def test_docker_desktop_release_notes_registry_instantiates_adapter() -> None:
    reload_registry()
    assert isinstance(
        get_adapter("docker_desktop_release_notes"), DockerDesktopReleaseNotesAdapter
    )
