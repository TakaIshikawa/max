"""CNCF Landscape source adapter."""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx
import yaml

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class CncfLandscapeAdapter(SourceAdapter):
    """Read CNCF Landscape-style project data as registry adoption signals."""

    @property
    def name(self) -> str:
        return "cncf_landscape"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def landscape_urls(self) -> list[str]:
        return _string_list(self._config.get("landscape_urls"))

    @property
    def local_paths(self) -> list[str]:
        return _string_list(self._config.get("local_paths"))

    @property
    def categories(self) -> list[str]:
        return _normalized_terms(self._config.get("categories"))

    @property
    def maturity_levels(self) -> list[str]:
        return _normalized_terms(self._config.get("maturity_levels"))

    @property
    def include_archived(self) -> bool:
        return bool(self._config.get("include_archived", False))

    @property
    def min_stars(self) -> int:
        value = _int_or_none(self._config.get("min_stars"))
        return max(value or 0, 0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()

        for local_path in self.local_paths:
            if len(signals) >= limit:
                break
            data = self._read_landscape(local_path)
            self._append_signals(signals, data, limit=limit, seen=seen, landscape_url=local_path)

        if len(signals) < limit and self.landscape_urls:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for landscape_url in self.landscape_urls:
                    if len(signals) >= limit:
                        break
                    data = await self._fetch_landscape(landscape_url, client)
                    self._append_signals(
                        signals,
                        data,
                        limit=limit,
                        seen=seen,
                        landscape_url=landscape_url,
                    )

        return signals[:limit]

    def _read_landscape(self, local_path: str) -> object | None:
        try:
            text = Path(local_path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("%s: failed to read landscape file %s: %s", self.name, local_path, exc)
            return None
        return _parse_landscape_text(text, source_label=local_path, adapter_name=self.name)

    async def _fetch_landscape(self, landscape_url: str, client: httpx.AsyncClient) -> object | None:
        try:
            response = await fetch_with_retry(
                landscape_url,
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-cncf-landscape-adapter/0.1"},
            )
        except AdapterFetchError as exc:
            logger.warning("%s: failed to fetch landscape URL %s: %s", self.name, landscape_url, exc)
            return None
        except httpx.RequestError as exc:
            logger.warning("%s: failed to fetch landscape URL %s: %s", self.name, landscape_url, exc)
            return None
        return _parse_landscape_text(response.text, source_label=landscape_url, adapter_name=self.name)

    def _append_signals(
        self,
        signals: list[Signal],
        data: object | None,
        *,
        limit: int,
        seen: set[str],
        landscape_url: str,
    ) -> None:
        if data is None:
            return

        for record in _extract_project_records(data):
            if len(signals) >= limit:
                break
            project_name = _string_or_none(
                record.get("name")
                or record.get("project")
                or record.get("title")
                or record.get("label")
            )
            if project_name is None:
                logger.warning("%s: skipping landscape record without project name", self.name)
                continue
            if not self._passes_filters(record):
                continue

            signal = _record_to_signal(record, adapter_name=self.name, landscape_url=landscape_url)
            dedupe_key = _dedupe_key(record, project_name)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            signals.append(signal)

    def _passes_filters(self, record: dict[str, Any]) -> bool:
        category = _normalize_term(_category(record))
        if self.categories and category not in self.categories:
            return False

        maturity = _normalize_term(_maturity(record))
        if self.maturity_levels and maturity not in self.maturity_levels:
            return False

        if _is_archived(record) and not self.include_archived:
            return False

        if self.min_stars > 0:
            stars = _int_or_none(record.get("stars") or record.get("github_stars") or record.get("star_count"))
            if stars is None or stars < self.min_stars:
                return False

        return True


def _parse_landscape_text(text: str, *, source_label: str, adapter_name: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        logger.warning("%s: malformed landscape data in %s: %s", adapter_name, source_label, exc)
        return None


def _extract_project_records(data: object) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    _collect_records(data, records, inherited_category=None, inherited_subcategory=None)
    return records


def _collect_records(
    data: object,
    records: list[dict[str, Any]],
    *,
    inherited_category: str | None,
    inherited_subcategory: str | None,
) -> None:
    if isinstance(data, list):
        for item in data:
            _collect_records(
                item,
                records,
                inherited_category=inherited_category,
                inherited_subcategory=inherited_subcategory,
            )
        return

    if not isinstance(data, dict):
        return

    category = _string_or_none(data.get("category")) or inherited_category
    subcategory = _string_or_none(data.get("subcategory") or data.get("sub_category"))
    if subcategory is None and inherited_category is not None and "items" in data:
        subcategory = _string_or_none(data.get("name")) or inherited_subcategory
    if category is None:
        category = _string_or_none(data.get("name"))
    if subcategory is None:
        subcategory = inherited_subcategory

    for key in ("projects", "items", "entries", "data", "results"):
        value = data.get(key)
        if isinstance(value, list):
            child_category = inherited_category if key in {"data", "results"} else category
            child_subcategory = inherited_subcategory if key in {"data", "results"} else subcategory
            for item in value:
                _collect_records(
                    item,
                    records,
                    inherited_category=child_category,
                    inherited_subcategory=child_subcategory,
                )
            return

    categories = data.get("categories")
    if isinstance(categories, list):
        for item in categories:
            _collect_records(
                item,
                records,
                inherited_category=inherited_category,
                inherited_subcategory=inherited_subcategory,
            )
        return

    subcategories = data.get("subcategories") or data.get("sub_categories")
    if isinstance(subcategories, list):
        for item in subcategories:
            _collect_records(
                item,
                records,
                inherited_category=category,
                inherited_subcategory=subcategory,
            )
        return

    if _looks_like_project(data):
        record = dict(data)
        record.setdefault("category", inherited_category)
        record.setdefault("subcategory", inherited_subcategory)
        records.append(record)


def _looks_like_project(record: dict[str, Any]) -> bool:
    return any(key in record for key in ("name", "project", "title")) and any(
        key in record
        for key in (
            "homepage",
            "homepage_url",
            "repo_url",
            "repository_url",
            "maturity",
            "description",
            "stars",
            "crunchbase",
            "tags",
        )
    )


def _record_to_signal(
    record: dict[str, Any],
    *,
    adapter_name: str,
    landscape_url: str,
) -> Signal:
    name = _string_or_none(record.get("name") or record.get("project") or record.get("title")) or ""
    description = _string_or_none(record.get("description") or record.get("summary")) or name
    repo_url = _repo_url(record)
    homepage = _string_or_none(record.get("homepage") or record.get("homepage_url") or record.get("website"))
    source_url = repo_url or homepage or landscape_url
    category = _category(record)
    subcategory = _subcategory(record)
    maturity = _maturity(record)
    stars = _int_or_none(record.get("stars") or record.get("github_stars") or record.get("star_count"))
    tags = _tags(record, category=category, subcategory=subcategory, maturity=maturity)

    metadata = {
        "project_name": name,
        "homepage": homepage,
        "category": category,
        "subcategory": subcategory,
        "maturity": maturity,
        "stars": stars,
        "repo_url": repo_url,
        "landscape_url": landscape_url,
        "crunchbase": _string_or_none(record.get("crunchbase")),
        "archived": _is_archived(record),
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=name,
        content=description[:500],
        url=source_url,
        tags=tags,
        credibility=_credibility(maturity=maturity, stars=stars, archived=metadata["archived"]),
        metadata=metadata,
    )


def _repo_url(record: dict[str, Any]) -> str | None:
    repository = record.get("repository") or record.get("repo")
    if isinstance(repository, dict):
        return _string_or_none(repository.get("url") or repository.get("repo_url"))
    return _string_or_none(
        record.get("repo_url")
        or record.get("repository_url")
        or record.get("github_url")
        or repository
    )


def _category(record: dict[str, Any]) -> str | None:
    return _string_or_none(record.get("category") or record.get("category_name"))


def _subcategory(record: dict[str, Any]) -> str | None:
    return _string_or_none(record.get("subcategory") or record.get("sub_category"))


def _maturity(record: dict[str, Any]) -> str | None:
    return _string_or_none(
        record.get("maturity")
        or record.get("maturity_level")
        or record.get("maturityLevel")
        or record.get("cncf_status")
    )


def _tags(
    record: dict[str, Any],
    *,
    category: str | None,
    subcategory: str | None,
    maturity: str | None,
) -> list[str]:
    tags: list[str] = []
    tags.extend(value for value in (category, subcategory, maturity) if value)
    raw_tags = record.get("tags")
    if isinstance(raw_tags, str):
        tags.extend(part.strip() for part in raw_tags.replace(",", " ").split())
    elif isinstance(raw_tags, Iterable):
        tags.extend(str(item).strip() for item in raw_tags if str(item).strip())
    return _dedupe(tags)[:12]


def _is_archived(record: dict[str, Any]) -> bool:
    archived = record.get("archived") or record.get("is_archived")
    if isinstance(archived, bool):
        return archived
    status = _normalize_term(record.get("status") or archived)
    return status in {"archived", "inactive", "deprecated"}


def _credibility(*, maturity: str | None, stars: int | None, archived: bool) -> float:
    maturity_score = {
        "graduated": 0.25,
        "incubating": 0.16,
        "sandbox": 0.07,
    }.get(_normalize_term(maturity), 0.0)
    star_score = min(math.log10((stars or 0) + 1) / 5, 0.25)
    archived_penalty = 0.15 if archived else 0.0
    return min(max(round(0.45 + maturity_score + star_score - archived_penalty, 3), 0.0), 1.0)


def _dedupe_key(record: dict[str, Any], project_name: str) -> str:
    return (_repo_url(record) or project_name).strip().lower()


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalized_terms(value: object) -> list[str]:
    return _dedupe([_normalize_term(item) for item in _string_list(value) if _normalize_term(item)])


def _normalize_term(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("_", "-")


def _int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).replace(",", ""))
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
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


CNCFLandscapeAdapter = CncfLandscapeAdapter
