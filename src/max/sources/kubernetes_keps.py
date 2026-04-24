"""Kubernetes Enhancement Proposal source adapter."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx
import yaml

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
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


class KubernetesKepsAdapter(SourceAdapter):
    """Discover public Kubernetes Enhancement Proposals from kubernetes/enhancements."""

    config_keys = ["areas", "stages", "max_results", "github_token", "token", "token_env", "include_archived"]
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
        return [_normalize_filter(value) for value in self._config.get("areas", _DEFAULT_AREAS)]

    @property
    def stages(self) -> list[str]:
        return [_normalize_filter(value) for value in self._config.get("stages", _DEFAULT_STAGES)]

    @property
    def max_results(self) -> int:
        return max(_int_or_none(self._config.get("max_results")) or 50, 1)

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
        signals: list[Signal] = []
        seen_paths: set[str] = set()

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

                signals.append(signal)

        return signals[:effective_limit]

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
        return True


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
        "signal_role": "market",
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
