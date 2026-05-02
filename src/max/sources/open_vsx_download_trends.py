"""Open VSX download trend source adapter -- extension adoption signals."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

OPEN_VSX_API_URL = "https://open-vsx.org/api"
OPEN_VSX_WEB_URL = "https://open-vsx.org/extension/{namespace}/{name}"


class OpenVsxDownloadTrendsAdapter(SourceAdapter):
    """Fetch Open VSX extension download totals and rating trend signals."""

    @property
    def name(self) -> str:
        return "open_vsx_download_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def extensions(self) -> list[tuple[str, str]]:
        return _extension_pairs(self._config.get("extensions"))

    @property
    def open_vsx_api_url(self) -> str:
        configured = self._config.get("open_vsx_api_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return OPEN_VSX_API_URL

    @property
    def max_results(self) -> int:
        return _positive_int(
            self._config.get("max_results", self._config.get("max_items")),
            default=30,
        )

    @property
    def timeout(self) -> float:
        return _positive_float(self._config.get("timeout"), default=30.0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(min(limit, self.max_results), 0)
        if item_limit == 0 or not self.extensions:
            return []

        signals: list[Signal] = []
        seen: set[str] = set()
        observed_at = datetime.now(timezone.utc)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for namespace, name in self.extensions:
                if len(signals) >= item_limit:
                    break

                identity = _identity(namespace, name)
                if identity in seen:
                    continue
                seen.add(identity)

                data = await self._fetch_extension(client, namespace, name)
                if data is None:
                    continue

                try:
                    signals.append(
                        _extension_to_signal(
                            data,
                            configured_namespace=namespace,
                            configured_name=name,
                            adapter_name=self.name,
                            api_url=self.open_vsx_api_url,
                            observed_at=observed_at,
                        )
                    )
                except (TypeError, ValueError) as e:
                    logger.warning("%s: malformed Open VSX extension record for %s: %s", self.name, identity, e)

        return signals[:item_limit]

    async def _fetch_extension(
        self,
        client: httpx.AsyncClient,
        namespace: str,
        name: str,
    ) -> dict | None:
        url = _api_url(self.open_vsx_api_url, namespace, name)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-open-vsx-download-trends-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Open VSX stats for %s/%s: %s", self.name, namespace, name, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s/%s: %s", self.name, namespace, name, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse Open VSX stats for %s/%s: %s", self.name, namespace, name, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed Open VSX stats for %s/%s", self.name, namespace, name)
            return None
        return payload


def _extension_to_signal(
    extension: dict,
    *,
    configured_namespace: str,
    configured_name: str,
    adapter_name: str,
    api_url: str,
    observed_at: datetime,
) -> Signal:
    namespace = _string_or_none(extension.get("namespace")) or configured_namespace
    name = _string_or_none(extension.get("name")) or configured_name
    if not namespace or not name:
        raise ValueError("extension missing namespace or name")

    downloads = _int_or_none(
        extension.get("downloadCount")
        or extension.get("download_count")
        or extension.get("downloads")
    )
    if downloads is None:
        raise ValueError("extension missing download count")

    average_rating = _float_or_none(
        extension.get("averageRating")
        or extension.get("average_rating")
        or extension.get("rating")
    )
    review_count = _int_or_none(
        extension.get("reviewCount")
        or extension.get("review_count")
        or extension.get("ratingCount")
        or extension.get("rating_count")
    )
    display_name = _string_or_none(extension.get("displayName") or extension.get("display_name"))
    version = _string_or_none(extension.get("version"))
    source_url = _web_url(namespace, name)
    extension_id = _identity(namespace, name)
    rating_text = ""
    if average_rating is not None:
        rating_text = f" with an average rating of {average_rating:g}"
        if review_count is not None:
            rating_text += f" across {review_count:,} reviews"

    return Signal(
        id=_stable_id(extension_id, downloads, average_rating, review_count),
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{display_name or f'{namespace}/{name}'} Open VSX download trend",
        content=(
            f"{namespace}/{name} recorded {downloads:,} total Open VSX downloads"
            f"{rating_text}."
        ),
        url=source_url,
        author=namespace,
        published_at=observed_at,
        fetched_at=observed_at,
        tags=_build_tags(namespace, name),
        credibility=_credibility(downloads, average_rating),
        metadata={
            "signal_role": "market",
            "extension_id": extension_id,
            "namespace": namespace,
            "name": name,
            "version": version,
            "downloads": downloads,
            "download_count": downloads,
            "average_rating": average_rating,
            "review_count": review_count,
            "source_url": source_url,
            "api_url": _api_url(api_url, namespace, name),
            "observed_at": observed_at.isoformat(),
        },
    )


def _extension_pairs(value: object) -> list[tuple[str, str]]:
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value is None:
        values = []
    else:
        values = [value]

    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for item in values:
        pair = _extension_pair(item)
        if pair is None:
            continue
        namespace, name = pair
        identity = _identity(namespace, name)
        if identity in seen:
            continue
        seen.add(identity)
        pairs.append((namespace, name))
    return pairs


def _extension_pair(value: object) -> tuple[str, str] | None:
    if isinstance(value, dict):
        namespace = _string_or_none(value.get("namespace"))
        name = _string_or_none(value.get("name") or value.get("extension"))
        if namespace and name:
            return namespace, name
        return None

    if not isinstance(value, str):
        return None

    text = value.strip().strip("/")
    if not text:
        return None

    separator = "/" if "/" in text else "."
    namespace, sep, name = text.partition(separator)
    if not sep or not namespace or not name or separator in name:
        return None
    return namespace.strip(), name.strip()


def _api_url(api_url: str, namespace: str, name: str) -> str:
    return (
        f"{api_url}/{quote(namespace, safe='')}/{quote(name, safe='')}"
    )


def _web_url(namespace: str, name: str) -> str:
    return OPEN_VSX_WEB_URL.format(
        namespace=quote(namespace, safe=""),
        name=quote(name, safe=""),
    )


def _identity(namespace: str, name: str) -> str:
    return f"{namespace}/{name}".lower()


def _stable_id(
    extension_id: str,
    downloads: int,
    average_rating: float | None,
    review_count: int | None,
) -> str:
    raw = f"{extension_id}\x1f{downloads}\x1f{average_rating}\x1f{review_count}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"open_vsx_download_trends:{extension_id}:{digest}"


def _build_tags(namespace: str, name: str) -> list[str]:
    tags = ["open-vsx", "vscode-extension", "downloads"]
    tags.extend(part for part in re.split(r"[/@._-]+", _identity(namespace, name)) if part)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(downloads: int, average_rating: float | None) -> float:
    download_score = min(math.log10(downloads + 1) / 7, 0.75)
    rating_score = 0.0
    if average_rating is not None:
        rating_score = min(max(average_rating, 0.0) / 5, 1.0) * 0.15
    return min(round(0.15 + download_score + rating_score, 3), 1.0)


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _positive_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


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
