"""Docker Hub repository activity source adapter."""

from __future__ import annotations

from max.sources.dockerhub import DockerHubAdapter as _DockerHubAdapter


class DockerHubAdapter(_DockerHubAdapter):
    """Fetch Docker Hub repository popularity and freshness signals."""

    @property
    def name(self) -> str:
        return "docker_hub"
