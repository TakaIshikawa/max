"""Crates.io dependents source adapter - reverse-dependency adoption signals."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

CRATES_API_URL = "https://crates.io/api/v1"
CRATES_PACKAGE_URL = "https://crates.io/crates/{crate_name}"


class CratesDependentsAdapter(SourceAdapter):
    """Fetch crates.io reverse-dependency metadata for configured Rust crates."""

    @property
    def name(self) -> str:
        return "crates_dependents"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def crate_names(self) -> list[str]:
        configured = self._configured_terms("crate_names", [])
        if configured:
            return configured
        configured = self._configured_terms("crates", [])
        if configured:
            return configured
        return self._configured_terms("packages", [])

    @property
    def max_dependents_per_crate(self) -> int:
        value = self._config.get("max_dependents_per_crate", self._config.get("max_items", 30))
        return max(int(value), 1)

    @property
    def page_size(self) -> int:
        return max(min(int(self._config.get("page_size", 100)), 100), 1)

    @property
    def crates_api_url(self) -> str:
        configured = str(self._config.get("crates_api_url", CRATES_API_URL)).strip()
        return (configured or CRATES_API_URL).rstrip("/")

    @property
    def timeout(self) -> float:
        return float(self._config.get("timeout", 30))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_pairs: set[tuple[str, str]] = set()
        item_limit = max(limit, 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for source_crate in self.crate_names:
                if len(signals) >= item_limit:
                    break

                normalized_source = _normalize_crate_name(source_crate)
                if not normalized_source:
                    continue

                per_crate_remaining = min(
                    self.max_dependents_per_crate,
                    item_limit - len(signals),
                )
                page = 1
                fetched_for_crate = 0

                while fetched_for_crate < per_crate_remaining and len(signals) < item_limit:
                    current_page_size = min(self.page_size, per_crate_remaining - fetched_for_crate)
                    payload = await self._fetch_dependents_page(
                        client,
                        normalized_source,
                        page=page,
                        per_page=current_page_size,
                    )
                    if payload is None:
                        break

                    rows = _iter_dependent_rows(payload)
                    if not rows:
                        break

                    added_this_page = 0
                    for row in rows:
                        if fetched_for_crate >= per_crate_remaining or len(signals) >= item_limit:
                            break

                        signal = _dependent_to_signal(
                            row,
                            source_crate=normalized_source,
                            adapter_name=self.name,
                            api_url=_dependents_api_url(
                                normalized_source,
                                page=page,
                                per_page=current_page_size,
                                base_url=self.crates_api_url,
                            ),
                        )
                        if signal is None:
                            logger.warning(
                                "%s: malformed dependent row for %s",
                                self.name,
                                normalized_source,
                            )
                            continue

                        key = (
                            signal.metadata["source_crate"],
                            signal.metadata["dependent_crate"],
                        )
                        if key in seen_pairs:
                            continue

                        seen_pairs.add(key)
                        signals.append(signal)
                        fetched_for_crate += 1
                        added_this_page += 1

                    if _is_last_page(payload, page=page, per_page=current_page_size) or added_this_page == 0:
                        break
                    page += 1

        return signals[:item_limit]

    async def _fetch_dependents_page(
        self,
        client: httpx.AsyncClient,
        crate_name: str,
        *,
        page: int,
        per_page: int,
    ) -> dict | list | None:
        url = _dependents_api_url(
            crate_name,
            page=page,
            per_page=per_page,
            base_url=self.crates_api_url,
        )
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-crates-dependents-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch dependents for %s: %s", self.name, crate_name, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, crate_name, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse dependents for %s: %s", self.name, crate_name, e)
            return None

        if not isinstance(payload, (dict, list)):
            logger.warning("%s: malformed dependents response for %s", self.name, crate_name)
            return None
        return payload


def _dependents_api_url(crate_name: str, *, page: int, per_page: int, base_url: str) -> str:
    if any(token in base_url for token in ("{crate_name}", "{crate}", "{page}", "{per_page}", "{limit}")):
        return base_url.format(
            crate_name=quote(crate_name, safe=""),
            crate=quote(crate_name, safe=""),
            page=page,
            per_page=per_page,
            limit=per_page,
        )

    return (
        f"{base_url}/crates/{quote(crate_name, safe='')}/reverse_dependencies"
        f"?page={page}&per_page={per_page}"
    )


def _iter_dependent_rows(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    for key in ("dependencies", "reverse_dependencies", "dependents", "crates", "data", "rows"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _is_last_page(payload: dict | list, *, page: int, per_page: int) -> bool:
    if isinstance(payload, list):
        return len(payload) < per_page

    rows = _iter_dependent_rows(payload)
    if len(rows) < per_page:
        return True

    meta = payload.get("meta")
    if isinstance(meta, dict):
        total = _int_or_none(meta.get("total") or meta.get("total_count"))
        if total is not None and page * per_page >= total:
            return True

    return False


def _dependent_to_signal(
    row: dict,
    *,
    source_crate: str,
    adapter_name: str,
    api_url: str,
) -> Signal | None:
    crate = _crate_payload(row)
    dependent_crate = _normalize_crate_name(
        crate.get("name") or crate.get("id") or crate.get("crate_name")
    )
    if not dependent_crate:
        return None

    version = _string_or_none(
        crate.get("max_version") or crate.get("newest_version") or crate.get("version")
    )
    description = _string_or_none(crate.get("description")) or dependent_crate
    downloads = _int_or_none(crate.get("downloads"))
    recent_downloads = _int_or_none(crate.get("recent_downloads"))
    dependent_url = _package_url(dependent_crate)
    source_url = _package_url(source_crate)
    published_at = _parse_datetime(crate.get("updated_at") or crate.get("created_at"))
    dependency_req = _string_or_none(row.get("req") or row.get("requirement") or row.get("version_req"))
    dependency_kind = _string_or_none(row.get("kind"))

    metadata = {
        "signal_role": "market",
        "signal_kind": "reverse_dependency",
        "evidence_type": "ecosystem_adoption",
        "package_ecosystem": "crates.io",
        "source_crate": source_crate,
        "source_crate_url": source_url,
        "source_package": source_crate,
        "source_package_url": source_url,
        "dependent_crate": dependent_crate,
        "dependent_crate_url": dependent_url,
        "dependent_package": dependent_crate,
        "dependent_package_url": dependent_url,
        "crate_name": dependent_crate,
        "package_name": dependent_crate,
        "version": version,
        "latest_version": version,
        "downloads": downloads,
        "recent_downloads": recent_downloads,
        "repository": _string_or_none(crate.get("repository")),
        "homepage": _string_or_none(crate.get("homepage")),
        "documentation": _string_or_none(crate.get("documentation")),
        "dependency_requirement": dependency_req,
        "dependency_kind": dependency_kind,
        "optional": _bool_or_none(row.get("optional")),
        "default_features": _bool_or_none(row.get("default_features")),
        "api_url": api_url,
        "source_url": dependent_url,
    }

    return Signal(
        id=_signal_id(source_crate, dependent_crate),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{dependent_crate} depends on {source_crate}",
        content=_content(
            dependent_crate,
            source_crate=source_crate,
            description=description,
            version=version,
            downloads=downloads,
            dependency_req=dependency_req,
        ),
        url=dependent_url,
        author=_string_or_none(crate.get("owners") or crate.get("owner_user")),
        published_at=published_at,
        tags=_build_tags(source_crate, dependent_crate, keywords=_string_list(crate.get("keywords"))),
        credibility=_credibility(downloads=downloads, recent_downloads=recent_downloads),
        metadata=metadata,
    )


def _crate_payload(row: dict) -> dict:
    for key in ("crate", "dependent", "package", "metadata"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return row


def _package_url(crate_name: str) -> str:
    return CRATES_PACKAGE_URL.format(crate_name=quote(crate_name, safe=""))


def _signal_id(source_crate: str, dependent_crate: str) -> str:
    return f"crates-dependents:{source_crate}:{dependent_crate}"


def _content(
    dependent_crate: str,
    *,
    source_crate: str,
    description: str,
    version: str | None,
    downloads: int | None,
    dependency_req: str | None,
) -> str:
    details = f"{dependent_crate} depends on {source_crate}."
    if dependency_req:
        details += f" Requirement: {dependency_req}."
    if version:
        details += f" Latest version: {version}."
    if downloads is not None:
        details += f" Downloads: {downloads:,}."
    if description and description != dependent_crate:
        details += f" {description}"
    return details


def _build_tags(source_crate: str, dependent_crate: str, *, keywords: list[str]) -> list[str]:
    tags = [
        "rust",
        "crates.io",
        "registry",
        "reverse-dependency",
        "ecosystem-adoption",
    ]
    tags.extend(_crate_parts(source_crate))
    tags.extend(_crate_parts(dependent_crate))
    tags.extend(keywords)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _crate_parts(crate_name: str) -> list[str]:
    return [part for part in re.split(r"[-_.]+", crate_name.lower()) if part]


def _credibility(*, downloads: int | None, recent_downloads: int | None) -> float:
    if downloads is None and recent_downloads is None:
        return 0.35
    download_score = min(math.log10((downloads or 0) + 1) / 10, 0.5)
    recent_score = min(math.log10((recent_downloads or 0) + 1) / 8, 0.15)
    return min(round(0.35 + download_score + recent_score, 3), 1.0)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_crate_name(value: object) -> str:
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


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None
