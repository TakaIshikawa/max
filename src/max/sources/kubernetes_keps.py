"""Kubernetes Enhancement Proposal source adapter."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx
import yaml

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com/kubernetes/enhancements/master"
REPO_WEB_BASE = "https://github.com/kubernetes/enhancements/tree/master"
TREE_URL = f"{GITHUB_API}/repos/kubernetes/enhancements/git/trees/master"

_DEFAULT_AREAS: list[str] = []
_DEFAULT_STAGES: list[str] = []
_ARCHIVED_STATUSES = {"archived", "deferred", "deprecated", "rejected", "replaced", "withdrawn"}
_SUMMARY_HEADINGS = ("summary", "motivation", "goals", "non-goals")
_INDEX_CONTAINER_KEYS = ("keps", "items", "results", "data", "enhancements")
_INDEX_TITLE_KEYS = ("title", "name", "kep", "enhancement")
_INDEX_NUMBER_KEYS = ("kep_number", "kep-number", "number", "id", "kep")
_INDEX_SIG_KEYS = ("sig", "owning_sig", "owning-sig", "area", "owning SIG")
_INDEX_STAGE_KEYS = ("stage", "latest_stage", "latest-stage")
_INDEX_STATUS_KEYS = ("status", "state")
_INDEX_URL_KEYS = ("url", "link", "kep_url", "kep-url")
_INDEX_SUMMARY_KEYS = ("summary", "description", "content", "motivation")


class KubernetesKepsAdapter(SourceAdapter):
    """Discover public Kubernetes Enhancement Proposals from kubernetes/enhancements."""

    config_keys = [
        "index_url",
        "local_path",
        "content",
        "areas",
        "sigs",
        "stages",
        "statuses",
        "keywords",
        "max_results",
        "max_items",
        "github_token",
        "token",
        "token_env",
        "include_archived",
    ]
    required_keys: list[str] = []
    description = "Fetches Kubernetes Enhancement Proposal roadmap metadata from GitHub."

    @property
    def name(self) -> str:
        return "kubernetes_keps"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def areas(self) -> list[str]:
        configured = _string_list(self._config.get("areas")) + _string_list(self._config.get("sigs"))
        return [_normalize_filter(value) for value in (configured or _DEFAULT_AREAS)]

    @property
    def stages(self) -> list[str]:
        configured = _string_list(self._config.get("stages")) + _string_list(self._config.get("statuses"))
        return [_normalize_filter(value) for value in (configured or _DEFAULT_STAGES)]

    @property
    def keywords(self) -> list[str]:
        return [_normalize_filter(value) for value in _string_list(self._config.get("keywords"))]

    @property
    def max_results(self) -> int:
        value = self._config.get("max_items", self._config.get("max_results"))
        return max(_int_or_none(value) or 50, 1)

    @property
    def include_archived(self) -> bool:
        return bool(self._config.get("include_archived", False))

    @property
    def token(self) -> str | None:
        configured = self._config.get("github_token") or self._config.get("token")
        if configured:
            return str(configured)
        token_env = self._config.get("token_env")
        if token_env:
            return os.environ.get(str(token_env))
        return os.environ.get("GITHUB_TOKEN")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(max(limit, 1), self.max_results)

        index_text = await self._load_index_text()
        if index_text is not None:
            return self._signals_from_index(index_text, effective_limit)

        signals: list[Signal] = []
        seen_paths: set[str] = set()
        seen_ids: set[str] = set()

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "max-kubernetes-keps-adapter/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            tree = await self._fetch_tree(client)
            for kep_dir in _kep_directories(tree):
                if len(signals) >= effective_limit:
                    break
                if kep_dir in seen_paths:
                    continue
                seen_paths.add(kep_dir)

                kep_yaml = await self._fetch_text(client, f"{kep_dir}/kep.yaml")
                readme = await self._fetch_text(client, f"{kep_dir}/README.md")
                if kep_yaml is None and readme is None:
                    continue

                signal = _build_signal(
                    kep_dir=kep_dir,
                    kep_yaml=kep_yaml or "",
                    readme=readme or "",
                    adapter_name=self.name,
                )
                if signal is None or not self._passes_filters(signal):
                    continue
                if signal.id in seen_ids:
                    continue

                seen_ids.add(signal.id)
                signals.append(signal)

        return signals[:effective_limit]

    async def _load_index_text(self) -> str | None:
        content = self._config.get("content")
        if isinstance(content, str):
            return content

        local_path = self._config.get("local_path")
        if local_path:
            try:
                return Path(str(local_path)).read_text(encoding="utf-8-sig")
            except OSError as e:
                logger.warning("%s: failed to read Kubernetes KEP index %s: %s", self.name, local_path, e)
                return None

        index_url = self._config.get("index_url")
        if not index_url:
            return None

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                response = await fetch_with_retry(str(index_url), client, adapter_name=self.name)
            except AdapterFetchError as e:
                logger.warning("%s: failed to fetch Kubernetes KEP index %s: %s", self.name, index_url, e)
                return None
            except httpx.RequestError as e:
                logger.warning("%s: failed to fetch Kubernetes KEP index %s: %s", self.name, index_url, e)
                return None
        return response.text

    def _signals_from_index(self, text: str, effective_limit: int) -> list[Signal]:
        try:
            items = _parse_kep_index(text)
        except SourceParseError as e:
            logger.warning("%s: skipping malformed Kubernetes KEP index: %s", self.name, e)
            return []

        signals: list[Signal] = []
        seen: set[str] = set()
        for item in items:
            if len(signals) >= effective_limit:
                break
            signal = _build_signal_from_item(item, adapter_name=self.name)
            if signal is None or signal.id in seen or not self._passes_filters(signal):
                continue
            seen.add(signal.id)
            signals.append(signal)
        return signals

    async def _fetch_tree(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        try:
            response = await fetch_with_retry(
                TREE_URL,
                client,
                adapter_name=self.name,
                params={"recursive": "1"},
            )
            data = response.json()
        except (AdapterFetchError, ValueError, httpx.RequestError) as e:
            logger.warning("%s: failed to fetch Kubernetes KEP tree: %s", self.name, e)
            return []

        tree = data.get("tree") if isinstance(data, dict) else None
        if not isinstance(tree, list):
            return []
        return [item for item in tree if isinstance(item, dict)]

    async def _fetch_text(self, client: httpx.AsyncClient, path: str) -> str | None:
        url = f"{RAW_BASE}/{quote(path, safe='/')}"
        try:
            response = await fetch_with_retry(url, client, adapter_name=self.name)
            return response.text
        except AdapterFetchError as e:
            if e.status_code != 404:
                logger.warning("%s: failed to fetch KEP file %s: %s", self.name, path, e)
        except httpx.RequestError as e:
            logger.warning("%s: failed to fetch KEP file %s: %s", self.name, path, e)
        return None

    def _passes_filters(self, signal: Signal) -> bool:
        area = _normalize_filter(signal.metadata.get("area"))
        stage = _normalize_filter(signal.metadata.get("stage") or signal.metadata.get("status"))
        status = _normalize_filter(signal.metadata.get("status"))

        if self.areas and area not in self.areas:
            return False
        if self.stages and stage not in self.stages and status not in self.stages:
            return False
        if not self.include_archived and status in _ARCHIVED_STATUSES:
            return False
        if self.keywords:
            haystack = " ".join(
                str(value or "")
                for value in (
                    signal.title,
                    signal.content,
                    signal.metadata.get("summary"),
                    signal.metadata.get("area"),
                    signal.metadata.get("stage"),
                    signal.metadata.get("status"),
                )
            ).lower()
            matched = [keyword for keyword in self.keywords if keyword in haystack]
            if not matched:
                return False
            signal.metadata["matched_keywords"] = matched
        return True


def _parse_kep_index(text: str) -> list[dict[str, Any]]:
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped.startswith(("{", "[")):
        return _extract_index_items(_parse_yaml_index(stripped))
    if stripped.startswith("- "):
        return _extract_index_items(_parse_yaml_index(stripped))
    return _parse_markdown_table_index(text)


def _parse_yaml_index(text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SourceParseError("Malformed Kubernetes KEP index", adapter_name="kubernetes_keps") from exc


def _extract_index_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        container = next((data.get(key) for key in _INDEX_CONTAINER_KEYS if key in data), data)
        if isinstance(container, dict):
            candidates = [
                {"kep_number": number, **value} if isinstance(value, dict) else value
                for number, value in container.items()
            ]
        elif isinstance(container, list):
            candidates = container
        else:
            candidates = []
    else:
        candidates = []

    return [_normalize_index_item(item) for item in candidates if isinstance(item, dict)]


def _parse_markdown_table_index(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    headers: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if headers is None:
            headers = [_normalize_header(cell) for cell in cells]
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if len(cells) != len(headers):
            continue
        rows.append(_normalize_index_item(dict(zip(headers, cells, strict=True))))
    return rows


def _normalize_index_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    return {
        "kep_number": _first_string(item, _INDEX_NUMBER_KEYS) or _kep_number_from_text(" ".join(map(str, item.values()))),
        "title": _clean_markdown(_first_string(item, _INDEX_TITLE_KEYS) or ""),
        "area": _first_string(item, _INDEX_SIG_KEYS),
        "stage": _first_string(item, _INDEX_STAGE_KEYS),
        "status": _first_string(item, _INDEX_STATUS_KEYS),
        "url": _extract_markdown_url(_first_string(item, _INDEX_URL_KEYS) or "")
        or _extract_markdown_url(_first_string(item, _INDEX_TITLE_KEYS) or ""),
        "summary": _clean_markdown(_first_string(item, _INDEX_SUMMARY_KEYS) or ""),
        "raw_metadata": row,
    }


def _kep_directories(tree: list[dict[str, Any]]) -> list[str]:
    dirs: set[str] = set()
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        if not path.startswith("keps/"):
            continue
        if path.endswith("/kep.yaml") or path.endswith("/README.md"):
            dirs.add(str(PurePosixPath(path).parent))
    return sorted(dirs)


def _build_signal_from_item(item: dict[str, Any], *, adapter_name: str) -> Signal | None:
    kep_number = _string_or_none(item.get("kep_number"))
    title = _string_or_none(item.get("title"))
    if not kep_number or not title:
        return None

    area = _string_or_none(item.get("area"))
    stage = _string_or_none(item.get("stage"))
    status = _string_or_none(item.get("status")) or stage
    summary = _string_or_none(item.get("summary")) or title
    url = _string_or_none(item.get("url")) or f"{REPO_WEB_BASE}/keps/{kep_number}"
    published_at = _parse_dt(_string_or_none(item.get("last_updated") or item.get("updated") or item.get("created")))

    signal_metadata = {
        "repository": "kubernetes/enhancements",
        "kep_number": kep_number,
        "area": area,
        "stage": stage,
        "status": status,
        "owning_sig": area,
        "summary": summary,
        "summary_sections": {"summary": summary} if summary else {},
        "signal_kind": "kubernetes_enhancement_proposal",
        "signal_role": "solution",
        "raw_metadata": item.get("raw_metadata", item),
    }

    return Signal(
        id=_signal_id("", kep_number),
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_format_title(kep_number, title),
        content=summary[:4000],
        url=url,
        author=area,
        published_at=published_at,
        tags=_build_tags(area=area, stage=stage, status=status, owning_sig=area),
        credibility=0.75 if status and status.lower() in {"implemented", "implementable"} else 0.65,
        metadata=signal_metadata,
    )


def _build_signal(
    *,
    kep_dir: str,
    kep_yaml: str,
    readme: str,
    adapter_name: str,
) -> Signal | None:
    metadata = _parse_kep_yaml(kep_yaml)
    if not metadata and not readme.strip():
        return None

    area = _string_or_none(metadata.get("area")) or _area_from_path(kep_dir)
    kep_number = _string_or_none(
        metadata.get("kep-number") or metadata.get("kep_number") or metadata.get("number")
    ) or _kep_number_from_path(kep_dir)
    title = _string_or_none(metadata.get("title")) or _title_from_readme(readme) or _title_from_path(kep_dir)
    stage = _string_or_none(metadata.get("stage") or metadata.get("latest-stage"))
    status = _string_or_none(metadata.get("status")) or stage
    owning_sig = _string_or_none(metadata.get("owning-sig") or metadata.get("owning_sig"))
    last_updated = _parse_dt(
        _string_or_none(
            metadata.get("last-updated")
            or metadata.get("last_updated")
            or metadata.get("latest-milestone")
            or metadata.get("creation-date")
        )
    )
    summary_sections = _extract_summary_sections(readme)
    summary = summary_sections.get("summary") or summary_sections.get("motivation") or title
    url = f"{REPO_WEB_BASE}/{quote(kep_dir, safe='/')}"

    signal_metadata = {
        "repository": "kubernetes/enhancements",
        "kep_path": kep_dir,
        "kep_number": kep_number,
        "area": area,
        "stage": stage,
        "status": status,
        "owning_sig": owning_sig,
        "summary": summary,
        "summary_sections": summary_sections,
        "signal_kind": "kubernetes_enhancement_proposal",
        "signal_role": "solution",
        "raw_metadata": metadata,
    }

    return Signal(
        id=_signal_id(kep_dir, kep_number),
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_format_title(kep_number, title),
        content=summary[:4000],
        url=url,
        author=owning_sig,
        published_at=last_updated,
        tags=_build_tags(area=area, stage=stage, status=status, owning_sig=owning_sig),
        credibility=0.75 if status and status.lower() in {"implemented", "implementable"} else 0.65,
        metadata=signal_metadata,
    )


def _parse_kep_yaml(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_summary_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []

    for line in markdown.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            if current and lines:
                sections[current] = _clean_markdown("\n".join(lines))
            heading = re.sub(r"\s*\{#.*?\}\s*$", "", match.group(1)).strip().lower()
            current = heading if heading in _SUMMARY_HEADINGS else None
            lines = []
            continue
        if current is not None:
            lines.append(line)

    if current and lines:
        sections[current] = _clean_markdown("\n".join(lines))

    return {key: value for key, value in sections.items() if value}


def _clean_markdown(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_>#-]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _title_from_readme(markdown: str) -> str | None:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def _area_from_path(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    if len(parts) >= 2:
        return parts[1]
    return None


def _kep_number_from_path(path: str) -> str | None:
    name = PurePosixPath(path).name
    match = re.match(r"^(\d+)", name)
    return match.group(1) if match else None


def _title_from_path(path: str) -> str:
    name = PurePosixPath(path).name
    name = re.sub(r"^\d+[-_]*", "", name)
    return name.replace("-", " ").replace("_", " ").strip().title() or path


def _format_title(kep_number: str | None, title: str) -> str:
    return f"KEP-{kep_number}: {title}" if kep_number else title


def _build_tags(
    *,
    area: str | None,
    stage: str | None,
    status: str | None,
    owning_sig: str | None,
) -> list[str]:
    tags = ["kubernetes", "kep", "roadmap", "standards"]
    tags.extend(value for value in (area, stage, status, owning_sig) if value)
    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        normalized = str(tag).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _first_string(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    normalized = {_normalize_header(str(key)): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(_normalize_header(key))
        if value is not None:
            return _string_or_none(value)
    return None


def _extract_markdown_url(value: str) -> str | None:
    match = re.search(r"\[[^\]]+\]\((https?://[^)]+)\)", value)
    if match:
        return match.group(1).strip()
    match = re.search(r"https?://\S+", value)
    if match:
        return match.group(0).rstrip(").,")
    return None


def _kep_number_from_text(value: str) -> str | None:
    match = re.search(r"\b(?:KEP[-\s]*)?(\d{1,5})\b", value, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _signal_id(path: str, kep_number: str | None) -> str:
    key = kep_number or path
    digest = hashlib.sha1(key.strip().lower().encode()).hexdigest()[:12]
    return f"kubernetes_keps:{digest}"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        value = f"{value}T00:00:00+00:00"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_filter(value: object) -> str:
    return str(value or "").strip().lower()


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
