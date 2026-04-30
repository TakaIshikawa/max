"""Docker Hub tag velocity source adapter -- recent container tag activity."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.dockerhub import (
    DOCKERHUB_TAGS,
    _dockerhub_url,
    _parse_datetime,
    _parse_repository_ref,
)
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_REPOSITORIES = ["library/nginx", "library/postgres", "library/redis"]


class DockerHubTagVelocityAdapter(SourceAdapter):
    """Fetch recent Docker Hub tag updates for configured repositories."""

    @property
    def name(self) -> str:
        return "dockerhub_tag_velocity"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def repositories(self) -> list[str]:
        return self._configured_terms("repositories", _DEFAULT_REPOSITORIES)

    @property
    def max_tags_per_repository(self) -> int:
        value = self._config.get("max_tags_per_repository", self._config.get("max_items", 10))
        return max(int(value), 1)

    @property
    def page_size(self) -> int:
        return min(max(int(self._config.get("page_size", 25)), 1), 100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(limit, 0)
        if item_limit == 0:
            return []

        signals: list[Signal] = []
        seen_tag_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for repository_ref in self.repositories:
                if len(signals) >= item_limit:
                    break

                repo_id = _parse_repository_ref(repository_ref)
                if repo_id is None:
                    logger.warning("%s: invalid repository reference: %s", self.name, repository_ref)
                    continue

                remaining = item_limit - len(signals)
                tags = await self._fetch_recent_tags(
                    client,
                    repo_id,
                    limit=min(self.max_tags_per_repository, remaining),
                )

                for tag in tags:
                    if len(signals) >= item_limit:
                        break
                    signal = _tag_to_signal(tag, repo_id=repo_id, adapter_name=self.name)
                    if signal.id in seen_tag_ids:
                        continue
                    seen_tag_ids.add(signal.id)
                    signals.append(signal)

        return signals[:item_limit]

    async def _fetch_recent_tags(
        self,
        client: httpx.AsyncClient,
        repo_id: tuple[str, str],
        *,
        limit: int,
    ) -> list[dict]:
        namespace, repository = repo_id
        tags: list[dict] = []
        url = DOCKERHUB_TAGS.format(
            namespace=quote(namespace, safe=""),
            repository=quote(repository, safe=""),
        )
        params: dict[str, object] | None = {"page_size": min(self.page_size, limit)}

        while len(tags) < limit and url:
            data = await self._fetch_json(
                client,
                url,
                context=f"tags for '{namespace}/{repository}'",
                params=params or {},
            )
            if data is None:
                break

            results = data.get("results")
            if not isinstance(results, list) or not results:
                break

            for tag in results:
                if len(tags) >= limit:
                    break
                if isinstance(tag, dict) and _tag_name(tag):
                    tags.append(tag)

            next_url = data.get("next")
            url = next_url if isinstance(next_url, str) and next_url else ""
            params = None

        return tags

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | None:
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                params=params,
                headers={"User-Agent": "max-dockerhub-tag-velocity-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Docker Hub data for %s: %s", self.name, context, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, context, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed Docker Hub response for %s", self.name, context)
            return None
        return payload


def _tag_to_signal(
    tag: dict,
    *,
    repo_id: tuple[str, str],
    adapter_name: str,
) -> Signal:
    namespace, repository = repo_id
    full_name = f"{namespace}/{repository}"
    tag_name = _tag_name(tag) or "unknown"
    last_updated = _parse_datetime(
        tag.get("last_updated")
        or tag.get("tag_last_pushed")
        or tag.get("last_pushed")
        or tag.get("last_modified")
    )
    digest = _tag_digest(tag)
    image_id = _tag_image_id(tag)
    source_url = _tag_url(namespace, repository, tag_name)
    digest_or_image = digest or image_id
    identifier_fragment = f" with digest/image {digest_or_image}" if digest_or_image else ""

    metadata = {
        "signal_role": "solution",
        "repository_name": full_name,
        "namespace": namespace,
        "name": repository,
        "tag_name": tag_name,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "digest": digest,
        "image_id": image_id,
        "source_url": source_url,
        "api_url": DOCKERHUB_TAGS.format(
            namespace=quote(namespace, safe=""),
            repository=quote(repository, safe=""),
        ),
        "full_size": _int_or_none(tag.get("full_size") or tag.get("size")),
        "creator": _int_or_none(tag.get("creator")),
        "last_updater": _int_or_none(tag.get("last_updater")),
    }

    return Signal(
        id=f"{adapter_name}:{full_name}:{tag_name}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{full_name}:{tag_name} Docker Hub tag update",
        content=(
            f"{full_name}:{tag_name} was last updated"
            f"{f' at {last_updated.isoformat()}' if last_updated else ''}{identifier_fragment}."
        ),
        url=source_url,
        published_at=last_updated,
        tags=_build_tags(full_name, tag_name),
        credibility=_credibility(last_updated),
        metadata=metadata,
    )


def _tag_name(tag: dict) -> str | None:
    value = tag.get("name")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _tag_digest(tag: dict) -> str | None:
    for key in ("digest", "tag_digest"):
        value = tag.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    images = tag.get("images")
    if not isinstance(images, list):
        return None
    for image in images:
        if not isinstance(image, dict):
            continue
        digest = image.get("digest")
        if isinstance(digest, str) and digest.strip():
            return digest.strip()
    return None


def _tag_image_id(tag: dict) -> str | None:
    for key in ("image_id", "id"):
        value = tag.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    images = tag.get("images")
    if not isinstance(images, list):
        return None
    for image in images:
        if not isinstance(image, dict):
            continue
        image_id = image.get("image_id") or image.get("id")
        if isinstance(image_id, str) and image_id.strip():
            return image_id.strip()
    return None


def _tag_url(namespace: str, repository: str, tag_name: str) -> str:
    if namespace == "library":
        return f"{_dockerhub_url(namespace, repository)}/tags?name={quote(tag_name, safe='')}"
    return f"{_dockerhub_url(namespace, repository)}/tags?name={quote(tag_name, safe='')}"


def _build_tags(repository: str, tag_name: str) -> list[str]:
    parts = ["docker", "dockerhub", "container", "tag", "release", repository, tag_name]
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = part.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(last_updated: datetime | None) -> float:
    if last_updated is None:
        return 0.45

    age_days = (datetime.now(timezone.utc) - last_updated).days
    freshness_score = 0.0
    if age_days <= 7:
        freshness_score = 0.35
    elif age_days <= 30:
        freshness_score = 0.25
    elif age_days <= 180:
        freshness_score = 0.15
    elif age_days <= 365:
        freshness_score = 0.05

    return min(round(0.4 + freshness_score + math.log10(max(1, 365 - age_days)) / 20, 3), 1.0)


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
