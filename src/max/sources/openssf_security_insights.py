"""OpenSSF Security Insights source adapter."""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import yaml

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_ENV = "GITHUB_TOKEN"
_RAW_GITHUB_BASE = "https://raw.githubusercontent.com"
_DEFAULT_MAX_ITEMS = 30
_DEFAULT_REQUIRED_FIELDS = [
    "header.schema-version",
    "header.project-url",
    "project-lifecycle.stage",
    "security-contacts",
    "vulnerability-reporting",
]
_POSTURE_FIELDS = [
    "self_assessment",
    "security_contacts",
    "vulnerability_reporting",
    "dependencies",
    "fuzzing",
    "audits",
    "release_integrity",
]
_INSIGHTS_FILENAMES = [
    "SECURITY-INSIGHTS.yml",
    "SECURITY-INSIGHTS.yaml",
    "security-insights.yml",
    "security-insights.yaml",
]
_INSIGHTS_DIRS = ["", ".github"]


class OpenSSFSecurityInsightsAdapter(SourceAdapter):
    """Read OpenSSF Security Insights YAML as supply-chain posture signals."""

    config_keys = [
        "repositories",
        "insight_urls",
        "local_paths",
        "github_token",
        "token",
        "token_env",
        "min_score",
        "required_fields",
        "max_items",
    ]
    required_keys: list[str] = []
    description = "Reads OpenSSF Security Insights YAML as security posture evidence."

    @property
    def name(self) -> str:
        return "openssf_security_insights"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"))

    @property
    def insight_urls(self) -> list[str]:
        return _string_list(self._config.get("insight_urls"))

    @property
    def local_paths(self) -> list[str]:
        return _string_list(self._config.get("local_paths"))

    @property
    def token_env(self) -> str:
        configured = self._config.get("token_env")
        return configured.strip() if isinstance(configured, str) and configured.strip() else _DEFAULT_TOKEN_ENV

    @property
    def token(self) -> str | None:
        for key in ("github_token", "token"):
            value = self._config.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return os.environ.get(self.token_env)

    @property
    def min_score(self) -> float | None:
        value = _float_or_none(self._config.get("min_score"))
        if value is None:
            return None
        if value > 1:
            value = value / 100
        return min(max(value, 0.0), 1.0)

    @property
    def required_fields(self) -> list[str]:
        configured = _string_list(self._config.get("required_fields"))
        if configured:
            return configured
        if self._config.get("required_fields") is False:
            return []
        return list(_DEFAULT_REQUIRED_FIELDS)

    @property
    def max_items(self) -> int:
        value = _int_or_none(self._config.get("max_items"))
        return max(value or _DEFAULT_MAX_ITEMS, 1)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = min(limit, self.max_items)
        signals: list[Signal] = []
        seen: set[str] = set()

        for local_path in self.local_paths:
            if len(signals) >= item_limit:
                break
            payload = self._read_local_insights(local_path)
            self._append_signal(
                signals,
                payload,
                source_label=local_path,
                source_url=local_path,
                repo_hint=None,
                limit=item_limit,
                seen=seen,
            )

        if len(signals) >= item_limit:
            return signals[:item_limit]

        headers = {
            "Accept": "application/x-yaml,text/yaml,text/plain,*/*",
            "User-Agent": "max-openssf-security-insights-adapter/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
            for insight_url in self.insight_urls:
                if len(signals) >= item_limit:
                    break
                payload = await self._fetch_url(insight_url, client)
                self._append_signal(
                    signals,
                    payload,
                    source_label=insight_url,
                    source_url=insight_url,
                    repo_hint=None,
                    limit=item_limit,
                    seen=seen,
                )

            for repo in self.repositories:
                if len(signals) >= item_limit:
                    break
                payload, source_url = await self._fetch_repository(repo, client)
                self._append_signal(
                    signals,
                    payload,
                    source_label=repo,
                    source_url=source_url or _github_repo_url(repo),
                    repo_hint=repo,
                    limit=item_limit,
                    seen=seen,
                )

        return signals[:item_limit]

    def _read_local_insights(self, local_path: str) -> dict[str, Any] | None:
        try:
            text = Path(local_path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("%s: failed to read Security Insights file %s: %s", self.name, local_path, exc)
            return None
        return _parse_yaml(text, source_label=local_path, adapter_name=self.name)

    async def _fetch_url(self, url: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
        try:
            response = await fetch_with_retry(url, client, adapter_name=self.name)
        except AdapterFetchError as exc:
            logger.warning("%s: failed to fetch Security Insights URL %s: %s", self.name, url, exc)
            return None
        except httpx.RequestError as exc:
            logger.warning("%s: failed to fetch Security Insights URL %s: %s", self.name, url, exc)
            return None
        return _parse_yaml(response.text, source_label=url, adapter_name=self.name)

    async def _fetch_repository(
        self,
        repo: str,
        client: httpx.AsyncClient,
    ) -> tuple[dict[str, Any] | None, str | None]:
        for url in _candidate_github_urls(repo):
            try:
                response = await client.request("GET", url)
            except httpx.RequestError as exc:
                logger.warning("%s: failed to fetch Security Insights for %s: %s", self.name, repo, exc)
                continue
            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                logger.warning(
                    "%s: failed to fetch Security Insights for %s: HTTP %s",
                    self.name,
                    repo,
                    response.status_code,
                )
                continue
            payload = _parse_yaml(response.text, source_label=url, adapter_name=self.name)
            if payload is not None:
                return payload, url
        return None, None

    def _append_signal(
        self,
        signals: list[Signal],
        payload: dict[str, Any] | None,
        *,
        source_label: str,
        source_url: str,
        repo_hint: str | None,
        limit: int,
        seen: set[str],
    ) -> None:
        if payload is None or len(signals) >= limit:
            return

        normalized = _normalize_security_insights(payload, source_label=source_label, repo_hint=repo_hint)
        missing = _missing_required_fields(payload, self.required_fields)
        normalized["missing_required_fields"] = missing
        if missing:
            logger.warning(
                "%s: skipping Security Insights file %s missing required fields: %s",
                self.name,
                source_label,
                ", ".join(missing),
            )
            return

        score = _posture_score(normalized)
        if self.min_score is not None and score < self.min_score:
            return

        signal = _signal_from_insights(
            payload,
            normalized,
            adapter_name=self.name,
            source_url=source_url,
            score=score,
        )
        if signal.id in seen:
            return
        seen.add(signal.id)
        signals.append(signal)


def _parse_yaml(text: str, *, source_label: str, adapter_name: str) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        logger.warning("%s: malformed Security Insights YAML in %s: %s", adapter_name, source_label, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("%s: Security Insights YAML in %s is not a mapping", adapter_name, source_label)
        return None
    return data


def _normalize_security_insights(
    payload: dict[str, Any],
    *,
    source_label: str,
    repo_hint: str | None,
) -> dict[str, Any]:
    header = _mapping(payload.get("header"))
    project_url = _string_or_none(
        _lookup(header, "project-url", "project_url")
        or _lookup(payload, "project-url", "project_url", "repository", "repo")
    )
    repo = _normalize_repo(project_url or repo_hint or source_label)

    vulnerability_reporting = _mapping(_lookup(payload, "vulnerability-reporting", "vulnerability_reporting"))
    dependencies = _lookup(payload, "dependencies", "dependency-management", "dependency_management")
    release_integrity = _lookup(
        payload,
        "release-integrity",
        "release_integrity",
        "artifact-integrity",
        "artifact_integrity",
    )

    normalized = {
        "schema_version": _string_or_none(_lookup(header, "schema-version", "schema_version")),
        "expiration_date": _string_or_none(_lookup(header, "expiration-date", "expiration_date")),
        "project_url": project_url,
        "repo": repo,
        "project_lifecycle": _mapping(_lookup(payload, "project-lifecycle", "project_lifecycle")),
        "self_assessment": _lookup(payload, "self-assessment", "self_assessment", "self-assessments"),
        "security_contacts": _as_list(_lookup(payload, "security-contacts", "security_contacts")),
        "vulnerability_reporting": vulnerability_reporting,
        "dependencies": dependencies,
        "fuzzing": _lookup(payload, "fuzzing", "fuzz-testing", "fuzz_testing"),
        "audits": _lookup(payload, "audits", "security-audits", "security_audits"),
        "release_integrity": release_integrity,
    }
    normalized["has_vulnerability_reporting"] = bool(vulnerability_reporting)
    normalized["accepts_vulnerability_reports"] = _bool_or_none(
        _lookup(
            vulnerability_reporting,
            "accepts-vulnerability-reports",
            "accepts_vulnerability_reports",
        )
    )
    return normalized


def _signal_from_insights(
    payload: dict[str, Any],
    normalized: dict[str, Any],
    *,
    adapter_name: str,
    source_url: str,
    score: float,
) -> Signal:
    repo = normalized["repo"] or _source_slug(source_url)
    contacts_count = len(normalized["security_contacts"])
    present_fields = [
        label.replace("_", "-")
        for label in _POSTURE_FIELDS
        if _has_value(normalized.get(label))
    ]
    title = f"OpenSSF Security Insights posture: {repo}"
    content = (
        f"{repo} declares Security Insights security posture fields covering "
        f"{', '.join(present_fields) if present_fields else 'limited security posture fields'}."
    )
    if contacts_count:
        content += f" It lists {contacts_count} security contact(s)."
    if normalized["accepts_vulnerability_reports"] is not None:
        content += (
            " Vulnerability reports are accepted."
            if normalized["accepts_vulnerability_reports"]
            else " Vulnerability reports are not accepted."
        )

    metadata = {
        "repo": repo,
        "repository": repo,
        "source_url": source_url,
        "schema_version": normalized["schema_version"],
        "expiration_date": normalized["expiration_date"],
        "project_url": normalized["project_url"],
        "posture_score": score,
        "posture_fields_present": present_fields,
        "missing_required_fields": normalized["missing_required_fields"],
        "security_contacts": normalized["security_contacts"],
        "vulnerability_reporting": normalized["vulnerability_reporting"],
        "dependencies": normalized["dependencies"],
        "fuzzing": normalized["fuzzing"],
        "audits": normalized["audits"],
        "release_integrity": normalized["release_integrity"],
        "self_assessment": normalized["self_assessment"],
        "security_insights": payload,
        "signal_role": "solution",
    }

    return Signal(
        id=f"{adapter_name}:{_source_slug(repo)}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=title[:240],
        content=content[:500],
        url=source_url,
        tags=_build_tags(repo, present_fields),
        credibility=round(0.55 + (score * 0.35), 3),
        metadata=metadata,
    )


def _missing_required_fields(payload: dict[str, Any], required_fields: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for field in required_fields:
        if not _has_value(_get_path(payload, field)):
            missing.append(field)
    return missing


def _get_path(payload: dict[str, Any], dotted_path: str) -> object:
    current: object = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = _lookup(current, part, part.replace("-", "_"), part.replace("_", "-"))
    return current


def _posture_score(normalized: dict[str, Any]) -> float:
    present = sum(1 for field in _POSTURE_FIELDS if _has_value(normalized.get(field)))
    return round(present / len(_POSTURE_FIELDS), 3)


def _candidate_github_urls(repo: str) -> list[str]:
    normalized = _normalize_repo(repo)
    urls: list[str] = []
    for branch in ("main", "master"):
        for directory in _INSIGHTS_DIRS:
            for filename in _INSIGHTS_FILENAMES:
                path = f"{directory}/{filename}" if directory else filename
                urls.append(f"{_RAW_GITHUB_BASE}/{quote(normalized, safe='/:')}/{branch}/{path}")
    return urls


def _github_repo_url(repo: str) -> str:
    return f"https://github.com/{_normalize_repo(repo)}"


def _normalize_repo(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip().removeprefix("https://").removeprefix("http://").removesuffix("/")
    normalized = normalized.removeprefix("www.").removeprefix("github.com/")
    if normalized.startswith("raw.githubusercontent.com/"):
        parts = normalized.split("/")
        if len(parts) >= 4:
            return f"{parts[1]}/{parts[2]}"
    return normalized


def _source_slug(value: str) -> str:
    normalized = value.strip().lower().removeprefix("https://").removeprefix("http://")
    normalized = normalized.removeprefix("github.com/").removesuffix("/")
    slug = "/".join(part for part in normalized.replace(":", "/").split("/") if part)
    if slug:
        return slug
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _build_tags(repo: str, present_fields: list[str]) -> list[str]:
    tags = ["security", "supply-chain", "openssf", "security-insights", *present_fields]
    owner = repo.split("/", 1)[0]
    if owner:
        tags.append(owner.lower())
    return _dedupe(tags)


def _lookup(mapping: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    raw_values = value if isinstance(value, list) else [value]
    values: list[str] = []
    for item in raw_values:
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
    return _dedupe(values)


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _float_or_none(value: object) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
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


OpenssfSecurityInsightsAdapter = OpenSSFSecurityInsightsAdapter
