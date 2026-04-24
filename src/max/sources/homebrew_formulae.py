"""Homebrew Formulae source adapter — package popularity and update signals."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Iterable

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

HOMEBREW_FORMULAE_URL = "https://formulae.brew.sh/api/formula.json"
HOMEBREW_CASKS_URL = "https://formulae.brew.sh/api/cask.json"

_DEFAULT_QUERIES: list[str] = []
_DEFAULT_CATEGORIES: list[str] = []


class HomebrewFormulaeAdapter(SourceAdapter):
    """Fetch Homebrew formula and cask popularity signals."""

    @property
    def name(self) -> str:
        return "homebrew_formulae"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def formulae_url(self) -> str:
        return str(self._config.get("formulae_url") or HOMEBREW_FORMULAE_URL)

    @property
    def casks_url(self) -> str:
        return str(self._config.get("casks_url") or HOMEBREW_CASKS_URL)

    @property
    def include_casks(self) -> bool:
        return bool(self._config.get("include_casks", True))

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    @property
    def min_install_count(self) -> int:
        return max(_int_or_none(self._config.get("min_install_count")) or 0, 0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            formulae = await self._fetch_payload(client, self.formulae_url, context="formulae")
            self._append_payload_signals(
                formulae,
                signals,
                seen,
                artifact_type="formula",
                source_url=self.formulae_url,
                limit=limit,
            )

            if self.include_casks and len(signals) < limit:
                casks = await self._fetch_payload(client, self.casks_url, context="casks")
                self._append_payload_signals(
                    casks,
                    signals,
                    seen,
                    artifact_type="cask",
                    source_url=self.casks_url,
                    limit=limit,
                )

        return signals[:limit]

    async def _fetch_payload(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
    ) -> list[dict]:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-homebrew-formulae-adapter/0.1"},
            )
            data = resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Homebrew %s: %s", self.name, context, e)
            return []
        except httpx.RequestError as e:
            logger.warning("%s: request failed for Homebrew %s: %s", self.name, context, e)
            return []
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for Homebrew %s: %s", self.name, context, e)
            return []

        if not isinstance(data, list):
            logger.warning("%s: malformed Homebrew %s payload: expected list", self.name, context)
            return []

        return [item for item in data if isinstance(item, dict)]

    def _append_payload_signals(
        self,
        payload: list[dict],
        signals: list[Signal],
        seen: set[str],
        *,
        artifact_type: str,
        source_url: str,
        limit: int,
    ) -> None:
        for item in payload:
            if len(signals) >= limit:
                return

            key = _dedupe_key(item, artifact_type)
            if key is None or key in seen:
                continue

            install_count = _install_count(item.get("analytics"))
            if install_count < self.min_install_count:
                continue

            if not _matches_filters(
                item,
                artifact_type=artifact_type,
                queries=self.queries,
                categories=self.categories,
            ):
                continue

            try:
                signal = _item_to_signal(
                    item,
                    adapter_name=self.name,
                    artifact_type=artifact_type,
                    source_url=source_url,
                    install_count=install_count,
                )
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Homebrew %s object: %s", self.name, artifact_type, e)
                continue

            seen.add(key)
            signals.append(signal)


def _item_to_signal(
    item: dict,
    *,
    adapter_name: str,
    artifact_type: str,
    source_url: str,
    install_count: int,
) -> Signal:
    token = _item_token(item)
    if token is None:
        raise ValueError("missing token/name")

    description = (
        _string_or_none(item.get("desc"))
        or _string_or_none(item.get("description"))
        or _display_name(item)
        or token
    )
    tap = _string_or_none(item.get("tap"))
    homepage = _string_or_none(item.get("homepage"))
    versions = _versions(item, artifact_type)
    updated_at = _parse_datetime(item.get("updated_at") or item.get("generated_date"))
    tags = _build_tags(item, artifact_type=artifact_type)
    title = f"{token}@{versions['stable']}" if versions.get("stable") else token

    metadata = {
        "name": _display_name(item) or token,
        "token": token,
        "tap": tap,
        "homepage": homepage,
        "description": description,
        "versions": versions,
        "analytics": item.get("analytics") if isinstance(item.get("analytics"), dict) else {},
        "artifact_type": artifact_type,
        "source_url": source_url,
        "install_count": install_count,
    }

    return Signal(
        id=f"{adapter_name}:{artifact_type}:{token.lower()}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=title,
        content=description[:500],
        url=_homebrew_url(token, artifact_type),
        published_at=updated_at,
        tags=tags,
        credibility=_credibility(install_count),
        metadata=metadata,
    )


def _matches_filters(
    item: dict,
    *,
    artifact_type: str,
    queries: list[str],
    categories: list[str],
) -> bool:
    if not queries and not categories:
        return True

    haystack = " ".join(_filter_values(item, artifact_type)).lower()
    query_match = not queries or any(term.lower() in haystack for term in queries)
    category_match = not categories or any(term.lower() in haystack for term in categories)
    return query_match and category_match


def _filter_values(item: dict, artifact_type: str) -> list[str]:
    values = [
        artifact_type,
        *_names(item),
        *(_build_tags(item, artifact_type=artifact_type)),
        _string_or_none(item.get("desc")),
        _string_or_none(item.get("description")),
        _string_or_none(item.get("tap")),
        _string_or_none(item.get("homepage")),
    ]
    return [value for value in values if isinstance(value, str) and value]


def _build_tags(item: dict, *, artifact_type: str) -> list[str]:
    tags = [artifact_type]
    tap = _string_or_none(item.get("tap"))
    if tap:
        tags.append(tap)

    for key in ("dependencies", "build_dependencies", "uses_from_macos", "conflicts_with"):
        tags.extend(_string_list(item.get(key)))

    if artifact_type == "cask":
        tags.extend(_cask_artifact_tags(item.get("artifacts")))
        depends_on = item.get("depends_on")
        if isinstance(depends_on, dict):
            for value in depends_on.values():
                tags.extend(_string_list(value))

    return _dedupe(tags)[:10]


def _dedupe_key(item: dict, artifact_type: str) -> str | None:
    token = _item_token(item)
    if token is None:
        return None
    return token.lower()


def _item_token(item: dict) -> str | None:
    return (
        _string_or_none(item.get("token"))
        or _string_or_none(item.get("name"))
        or _string_or_none(item.get("full_name"))
    )


def _display_name(item: dict) -> str | None:
    name = item.get("name")
    if isinstance(name, list):
        return _string_or_none(name[0]) if name else None
    return _string_or_none(name)


def _names(item: dict) -> list[str]:
    values: list[str] = []
    for key in ("token", "name", "full_name", "oldname"):
        value = item.get(key)
        if isinstance(value, list):
            values.extend(_string_list(value))
        else:
            string_value = _string_or_none(value)
            if string_value:
                values.append(string_value)
    values.extend(_string_list(item.get("aliases")))
    values.extend(_string_list(item.get("oldnames")))
    values.extend(_string_list(item.get("old_tokens")))
    return _dedupe(values)


def _versions(item: dict, artifact_type: str) -> dict:
    raw_versions = item.get("versions")
    if isinstance(raw_versions, dict):
        return dict(raw_versions)

    version = _string_or_none(item.get("version"))
    if version:
        return {"stable": version} if artifact_type == "formula" else {"version": version}
    return {}


def _homebrew_url(token: str, artifact_type: str) -> str:
    path = "cask" if artifact_type == "cask" else "formula"
    return f"https://formulae.brew.sh/{path}/{token}"


def _install_count(analytics: object) -> int:
    if not isinstance(analytics, dict):
        return 0

    counts: list[int] = []
    for key in ("install_on_request", "install"):
        bucket = analytics.get(key)
        if isinstance(bucket, dict):
            counts.extend(_collect_ints(bucket))

    return max(counts, default=0)


def _collect_ints(value: object) -> list[int]:
    if isinstance(value, dict):
        ints: list[int] = []
        for nested in value.values():
            ints.extend(_collect_ints(nested))
        return ints
    parsed = _int_or_none(value)
    return [parsed] if parsed is not None else []


def _credibility(install_count: int) -> float:
    install_score = min(math.log10(install_count + 1) / 7, 0.9)
    return min(round(0.1 + install_score, 3), 1.0)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _cask_artifact_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    tags: list[str] = []
    for artifact in value:
        if isinstance(artifact, dict):
            tags.extend(str(key) for key in artifact if isinstance(key, str))
        elif isinstance(artifact, list) and artifact:
            first = artifact[0]
            if isinstance(first, str):
                tags.append(first)
    return tags


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, Iterable) or isinstance(value, dict):
        return []

    values: list[str] = []
    for item in value:
        string_value = _string_or_none(item)
        if string_value:
            values.append(string_value)
    return values


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped
