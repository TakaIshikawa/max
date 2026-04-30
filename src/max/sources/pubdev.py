"""Pub.dev source adapter - Dart and Flutter package trend signals."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

PUBDEV_BASE_URL = "https://pub.dev"


class PubDevAdapter(SourceAdapter):
    """Fetch configured Pub.dev package metadata and score metrics."""

    @property
    def name(self) -> str:
        return "pubdev"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", [])

    @property
    def max_results(self) -> int:
        return max(int(self._config.get("max_results", self._config.get("max_items", 30))), 1)

    @property
    def base_url(self) -> str:
        configured = str(self._config.get("base_url", PUBDEV_BASE_URL)).strip()
        return (configured or PUBDEV_BASE_URL).rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[str] = set()
        item_limit = max(min(limit, self.max_results), 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for package in self.packages:
                if len(signals) >= item_limit:
                    break

                normalized = _normalize_package_name(package)
                if not normalized or normalized in seen_packages:
                    continue
                seen_packages.add(normalized)

                metadata = await self._fetch_json(client, _package_api_url(normalized, base_url=self.base_url))
                if metadata is None:
                    continue

                score = await self._fetch_json(
                    client,
                    _score_api_url(normalized, base_url=self.base_url),
                    required=False,
                )
                signal = _package_to_signal(
                    metadata,
                    score=score,
                    fallback_name=normalized,
                    base_url=self.base_url,
                    adapter_name=self.name,
                )
                if signal is None:
                    logger.warning("%s: malformed Pub.dev package metadata for %s", self.name, normalized)
                    continue

                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        required: bool = True,
    ) -> dict | None:
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-pubdev-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            if required:
                logger.warning("%s: failed to fetch Pub.dev package metadata from %s: %s", self.name, url, e)
            else:
                logger.warning("%s: failed to fetch Pub.dev score from %s: %s", self.name, url, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, url, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse Pub.dev response from %s: %s", self.name, url, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed Pub.dev response from %s", self.name, url)
            return None
        return payload


def _package_to_signal(
    package: dict,
    *,
    score: dict | None,
    fallback_name: str,
    base_url: str,
    adapter_name: str,
) -> Signal | None:
    package_name = _normalize_package_name(package.get("name")) or fallback_name
    if not package_name:
        return None

    latest = package.get("latest") if isinstance(package.get("latest"), dict) else {}
    pubspec = latest.get("pubspec") if isinstance(latest.get("pubspec"), dict) else {}
    latest_version = _string_or_none(latest.get("version")) or ""
    published_at = _parse_datetime(latest.get("published"))
    description = _string_or_none(pubspec.get("description")) or package_name
    repository_url = _string_or_none(pubspec.get("repository"))
    homepage = _string_or_none(pubspec.get("homepage"))
    documentation = _string_or_none(pubspec.get("documentation"))
    score = score if isinstance(score, dict) else {}
    popularity = _float_or_none(score.get("popularityScore"))
    likes = _int_or_none(score.get("likeCount"))
    granted_points = _int_or_none(score.get("grantedPoints"))
    max_points = _int_or_none(score.get("maxPoints"))
    package_url = _package_page_url(package_name, base_url=base_url)
    api_url = _package_api_url(package_name, base_url=base_url)
    score_api_url = _score_api_url(package_name, base_url=base_url)

    metadata = {
        "signal_role": "market",
        "signal_kind": "package_metadata",
        "package_ecosystem": "pubdev",
        "package_name": package_name,
        "pubdev_name": package_name,
        "latest_version": latest_version,
        "version": latest_version,
        "popularity": popularity,
        "popularity_score": popularity,
        "likes": likes,
        "like_count": likes,
        "pub_points": granted_points,
        "granted_points": granted_points,
        "max_points": max_points,
        "updated_at": published_at.isoformat() if published_at else None,
        "repository_url": repository_url,
        "homepage": homepage,
        "documentation": documentation,
        "platforms": _string_list(score.get("tags"), prefix="platform:"),
        "publisher": _string_or_none(package.get("publisher")),
        "package_url": package_url,
        "source_url": package_url,
        "api_url": api_url,
        "score_api_url": score_api_url,
    }

    return Signal(
        id=_signal_id(package_name, latest_version),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_name}@{latest_version}" if latest_version else package_name,
        content=_content(
            package_name,
            description=description,
            popularity=popularity,
            likes=likes,
            granted_points=granted_points,
            max_points=max_points,
        ),
        url=package_url,
        published_at=published_at,
        tags=_build_tags(package_name, score=score, pubspec=pubspec),
        credibility=_credibility(popularity=popularity, likes=likes, granted_points=granted_points),
        metadata=metadata,
    )


def _package_api_url(package_name: str, *, base_url: str) -> str:
    return f"{base_url}/api/packages/{quote(package_name, safe='')}"


def _score_api_url(package_name: str, *, base_url: str) -> str:
    return f"{base_url}/api/packages/{quote(package_name, safe='')}/score"


def _package_page_url(package_name: str, *, base_url: str) -> str:
    return f"{base_url}/packages/{quote(package_name, safe='')}"


def _signal_id(package_name: str, version: str) -> str:
    normalized_version = version.strip().lower() or "unknown"
    return f"pubdev:{package_name}:{normalized_version}"


def _content(
    package_name: str,
    *,
    description: str,
    popularity: float | None,
    likes: int | None,
    granted_points: int | None,
    max_points: int | None,
) -> str:
    parts = [description[:350]]
    metrics: list[str] = []
    if popularity is not None:
        metrics.append(f"{popularity:.1%} popularity")
    if likes is not None:
        metrics.append(f"{likes:,} likes")
    if granted_points is not None:
        if max_points is not None:
            metrics.append(f"{granted_points}/{max_points} pub points")
        else:
            metrics.append(f"{granted_points} pub points")
    if metrics:
        parts.append(f"Pub.dev reports {', '.join(metrics)} for {package_name}.")
    return " ".join(parts)[:500]


def _build_tags(package_name: str, *, score: dict, pubspec: dict) -> list[str]:
    tags = ["dart", "flutter", "pubdev", "package"]
    tags.extend(_string_list(pubspec.get("topics")))
    tags.extend(_string_list(score.get("tags"), prefix="platform:"))
    tags.extend(part for part in re.split(r"[-_.]+", package_name.lower()) if part)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(
    *,
    popularity: float | None,
    likes: int | None,
    granted_points: int | None,
) -> float:
    popularity_score = min(max(popularity or 0.0, 0.0), 1.0) * 0.35
    likes_score = min(math.log10((likes or 0) + 1) / 5, 0.35)
    points_score = min((granted_points or 0) / 160, 0.2)
    return min(round(0.1 + popularity_score + likes_score + points_score, 3), 1.0)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_package_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: object, *, prefix: str | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in value:
        text = _string_or_none(item)
        if text is None:
            continue
        if prefix is not None:
            if not text.startswith(prefix):
                continue
            text = text.removeprefix(prefix)
        strings.append(text)
    return strings
