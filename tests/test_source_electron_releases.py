from __future__ import annotations

from max.sources.electron_releases import ElectronReleasesAdapter, parse_electron_releases
from max.sources.registry import get_adapter, reload_registry


def test_parse_electron_releases_handles_payloads_and_metadata() -> None:
    payload = {
        "results": [
            {
                "title": "Electron 33.0.0",
                "url": "https://releases.electronjs.org/release/v33.0.0",
                "version": "33.0.0",
                "channel": "stable",
                "breaking_changes": ["Node.js version bump"],
                "platform": "desktop",
            }
        ]
    }

    signal = parse_electron_releases(payload)[0]

    assert signal.metadata["version"] == "33.0.0"
    assert signal.metadata["channel"] == "stable"
    assert signal.metadata["breaking_changes"] == ["Node.js version bump"]
    assert signal.metadata["platform"] == "desktop"
    assert signal.id == parse_electron_releases(payload)[0].id
    assert parse_electron_releases([]) == []


def test_electron_releases_registry_instantiates_adapter() -> None:
    reload_registry()
    assert isinstance(get_adapter("electron_releases"), ElectronReleasesAdapter)
