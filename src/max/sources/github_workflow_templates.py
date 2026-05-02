"""GitHub Actions workflow template source adapter."""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import yaml

from max.sources.base import SourceAdapter
from max.sources.errors import (
    SourceAuthError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.retry import with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_DEFAULT_REPOSITORIES = ["actions/starter-workflows"]
_DEFAULT_PATHS = ["ci", "deployments", "automation", "code-scanning", "pages"]
_WORKFLOW_EXTENSIONS = (".yml", ".yaml")
_PROPERTIES_SUFFIX = ".properties.json"


class GitHubWorkflowTemplatesAdapter(SourceAdapter):
    """Fetch GitHub Actions workflow templates and starter workflows."""

    @property
    def name(self) -> str:
        return "github_workflow_templates"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def repositories(self) -> list[str]:
        configured = self._config.get("repositories")
        if configured is None:
            configured = self._config.get("repos")
        return _repository_list(configured, _DEFAULT_REPOSITORIES)

    @property
    def paths(self) -> list[str]:
        return _string_list(self._config.get("paths"), _DEFAULT_PATHS)

    @property
    def max_templates_per_repo(self) -> int:
        return _positive_int(self._config.get("max_templates_per_repo"), 50)

    @property
    def api_url(self) -> str:
        value = self._config.get("api_url")
        if isinstance(value, str) and value.strip():
            return value.strip().rstrip("/")
        return GITHUB_API

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return 30.0
        return timeout if timeout > 0 else 30.0

    @property
    def token_env(self) -> str:
        configured = self._config.get("token_env")
        return configured.strip() if isinstance(configured, str) and configured.strip() else "GITHUB_TOKEN"

    @property
    def token(self) -> str | None:
        configured = self._config.get("github_token") or self._config.get("token")
        if configured:
            return str(configured)
        return os.environ.get(self.token_env)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "max-github-workflow-templates-adapter/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        signals: list[Signal] = []
        seen_ids: set[str] = set()
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            for repo in self.repositories:
                if len(signals) >= limit:
                    break
                await self._append_repo_signals(client, repo, signals=signals, seen_ids=seen_ids, limit=limit)

        return signals[:limit]

    async def _append_repo_signals(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        signals: list[Signal],
        seen_ids: set[str],
        limit: int,
    ) -> None:
        inspected = 0
        for path in self.paths:
            if len(signals) >= limit or inspected >= self.max_templates_per_repo:
                break
            entries = await self._fetch_directory(client, repo, path)
            if entries is None:
                continue

            workflows = _workflow_entries(entries)
            properties = _properties_entries(entries)
            for workflow in workflows:
                if len(signals) >= limit or inspected >= self.max_templates_per_repo:
                    break
                inspected += 1
                signal = await self._workflow_entry_to_signal(
                    client,
                    repo,
                    workflow,
                    properties.get(_template_key(workflow)),
                )
                if signal is None or signal.id in seen_ids:
                    continue
                seen_ids.add(signal.id)
                signals.append(signal)

    async def _workflow_entry_to_signal(
        self,
        client: httpx.AsyncClient,
        repo: str,
        workflow_entry: dict,
        properties_entry: dict | None,
    ) -> Signal | None:
        path = _string_or_none(workflow_entry.get("path"))
        if path is None:
            logger.warning("%s: malformed workflow template entry in %s", self.name, repo)
            return None

        workflow_payload = await self._fetch_file(client, repo, path)
        if workflow_payload is None:
            return None
        workflow_data = _parse_workflow(workflow_payload.get("decoded_content"))

        properties: dict[str, Any] = {}
        if properties_entry is not None:
            properties_path = _string_or_none(properties_entry.get("path"))
            if properties_path is not None:
                properties_payload = await self._fetch_file(client, repo, properties_path)
                properties = _parse_properties(properties_payload) if properties_payload is not None else {}

        freshness = await self._fetch_latest_commit(client, repo, path)
        return _to_signal(
            workflow_entry,
            repo=repo,
            adapter_name=self.name,
            workflow_data=workflow_data,
            properties=properties,
            freshness=freshness,
        )

    async def _fetch_directory(
        self,
        client: httpx.AsyncClient,
        repo: str,
        path: str,
    ) -> list[dict] | None:
        try:
            data = await self._fetch_json(client, repo, f"contents/{path.strip('/')}")
        except (SourceRateLimitError, SourceAuthError):
            raise
        except (
            SourceTransientError,
            SourceParseError,
            httpx.RequestError,
            httpx.TimeoutException,
        ):
            logger.warning("%s: failed to fetch workflow template directory %s/%s", self.name, repo, path, exc_info=True)
            return None

        if not isinstance(data, list):
            logger.warning("%s: malformed workflow template directory for %s/%s", self.name, repo, path)
            return None
        return [entry for entry in data if isinstance(entry, dict)]

    async def _fetch_file(self, client: httpx.AsyncClient, repo: str, path: str) -> dict | None:
        try:
            data = await self._fetch_json(client, repo, f"contents/{path.strip('/')}")
        except (SourceRateLimitError, SourceAuthError):
            raise
        except (
            SourceTransientError,
            SourceParseError,
            httpx.RequestError,
            httpx.TimeoutException,
        ):
            logger.warning("%s: failed to fetch workflow template file %s/%s", self.name, repo, path, exc_info=True)
            return None

        if not isinstance(data, dict):
            logger.warning("%s: malformed workflow template file for %s/%s", self.name, repo, path)
            return None
        data["decoded_content"] = _decoded_content(data)
        return data

    async def _fetch_latest_commit(
        self,
        client: httpx.AsyncClient,
        repo: str,
        path: str,
    ) -> dict[str, Any]:
        try:
            data = await self._fetch_json(client, repo, "commits", params={"path": path, "per_page": 1})
        except (SourceRateLimitError, SourceAuthError):
            raise
        except (
            SourceTransientError,
            SourceParseError,
            httpx.RequestError,
            httpx.TimeoutException,
        ):
            logger.warning("%s: failed to fetch workflow template freshness for %s/%s", self.name, repo, path, exc_info=True)
            return {}

        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return {}
        commit = data[0]
        commit_data = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
        author = commit_data.get("author") if isinstance(commit_data.get("author"), dict) else {}
        committer = commit_data.get("committer") if isinstance(commit_data.get("committer"), dict) else {}
        updated_at = _parse_dt(committer.get("date") or author.get("date"))
        return {
            "latest_commit_sha": _string_or_none(commit.get("sha")),
            "latest_commit_url": _string_or_none(commit.get("html_url")),
            "latest_commit_at": updated_at,
            "latest_commit_author": _string_or_none(author.get("name")),
        }

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_workflow_templates")
    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        repo: str,
        endpoint: str,
        *,
        params: dict[str, object] | None = None,
    ) -> Any:
        try:
            resp = await client.get(f"{self.api_url}/repos/{repo}/{endpoint}", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            _raise_http_error(e, f"{endpoint} for repository: {repo}", self.name)
        except ValueError as e:
            raise SourceParseError(
                f"Failed to parse {endpoint} for repository: {repo}",
                adapter_name=self.name,
            ) from e


def _workflow_entries(entries: list[dict]) -> list[dict]:
    workflows: list[dict] = []
    for entry in entries:
        name = _string_or_none(entry.get("name"))
        path = _string_or_none(entry.get("path"))
        entry_type = _string_or_none(entry.get("type"))
        if entry_type != "file" or name is None or path is None:
            continue
        if name.endswith(_WORKFLOW_EXTENSIONS):
            workflows.append(entry)
    return workflows


def _properties_entries(entries: list[dict]) -> dict[str, dict]:
    properties: dict[str, dict] = {}
    for entry in entries:
        name = _string_or_none(entry.get("name"))
        path = _string_or_none(entry.get("path"))
        entry_type = _string_or_none(entry.get("type"))
        if entry_type == "file" and name and path and name.endswith(_PROPERTIES_SUFFIX):
            properties[_strip_properties_suffix(name)] = entry
    return properties


def _to_signal(
    workflow_entry: dict,
    *,
    repo: str,
    adapter_name: str,
    workflow_data: dict[str, Any],
    properties: dict[str, Any],
    freshness: dict[str, Any],
) -> Signal | None:
    path = _string_or_none(workflow_entry.get("path"))
    if path is None:
        return None

    name = _string_or_none(properties.get("name")) or _string_or_none(workflow_data.get("name"))
    template_name = name or _human_name(_template_key(workflow_entry))
    description = _string_or_none(properties.get("description")) or f"GitHub Actions workflow template for {template_name}"
    categories = _string_list(properties.get("categories"), [])
    language = _primary_language(categories, path)
    html_url = _string_or_none(workflow_entry.get("html_url")) or f"https://github.com/{repo}/blob/HEAD/{path}"
    updated_at = freshness.get("latest_commit_at")
    age_days = (datetime.now(timezone.utc) - updated_at).days if isinstance(updated_at, datetime) else None

    metadata = {
        "signal_role": "market",
        "signal_kind": "github_workflow_template",
        "evidence_type": "workflow_template",
        "repository": repo,
        "repo": repo,
        "path": path,
        "template_name": template_name,
        "workflow_name": _string_or_none(workflow_data.get("name")),
        "language": language,
        "category": categories[0] if categories else None,
        "categories": categories,
        "url": html_url,
        "html_url": html_url,
        "download_url": _string_or_none(workflow_entry.get("download_url")),
        "sha": _string_or_none(workflow_entry.get("sha")),
        "events": _workflow_events(workflow_data),
        "job_count": _job_count(workflow_data),
        "freshness_at": updated_at.isoformat() if isinstance(updated_at, datetime) else None,
        "latest_commit_at": updated_at.isoformat() if isinstance(updated_at, datetime) else None,
        "latest_commit_sha": freshness.get("latest_commit_sha"),
        "latest_commit_url": freshness.get("latest_commit_url"),
        "latest_commit_author": freshness.get("latest_commit_author"),
        "freshness_age_days": age_days,
        "source_url": html_url,
    }

    return Signal(
        id=_stable_id(repo, path, workflow_entry),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{repo} workflow template: {template_name}",
        content=_content(repo, path, description, categories=categories, freshness_age_days=age_days),
        url=html_url,
        author=repo.split("/", 1)[0],
        published_at=updated_at if isinstance(updated_at, datetime) else None,
        tags=_build_tags(repo, path, template_name, categories, workflow_data),
        credibility=_credibility(categories=categories, workflow_data=workflow_data, freshness_age_days=age_days),
        metadata=metadata,
    )


def _content(
    repo: str,
    path: str,
    description: str,
    *,
    categories: list[str],
    freshness_age_days: int | None,
) -> str:
    parts = [
        description,
        f"Repository: {repo}",
        f"Path: {path}",
    ]
    if categories:
        parts.append(f"Categories: {', '.join(categories)}")
    if freshness_age_days is not None:
        parts.append(f"Updated {freshness_age_days} days ago")
    return "\n".join(parts)


def _parse_properties(payload: dict) -> dict[str, Any]:
    decoded = payload.get("decoded_content")
    if not isinstance(decoded, str) or not decoded.strip():
        return {}
    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError:
        logger.warning("Malformed GitHub workflow template properties JSON")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_workflow(decoded: object) -> dict[str, Any]:
    if not isinstance(decoded, str) or not decoded.strip():
        return {}
    try:
        parsed = yaml.safe_load(decoded)
    except yaml.YAMLError:
        logger.warning("Malformed GitHub workflow template YAML")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _decoded_content(payload: dict) -> str | None:
    content = payload.get("content")
    if not isinstance(content, str):
        return None
    if payload.get("encoding") != "base64":
        return content
    try:
        return base64.b64decode(content, validate=False).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _workflow_events(workflow_data: dict[str, Any]) -> list[str]:
    events = workflow_data.get("on")
    if events is None and True in workflow_data:
        events = workflow_data.get(True)
    if isinstance(events, str):
        return [events]
    if isinstance(events, list):
        return [event for event in events if isinstance(event, str)]
    if isinstance(events, dict):
        return [event for event in events if isinstance(event, str)]
    return []


def _job_count(workflow_data: dict[str, Any]) -> int:
    jobs = workflow_data.get("jobs")
    return len(jobs) if isinstance(jobs, dict) else 0


def _build_tags(
    repo: str,
    path: str,
    template_name: str,
    categories: list[str],
    workflow_data: dict[str, Any],
) -> list[str]:
    tags: set[str] = {"github", "actions", "workflow-template", "starter-workflow"}
    for category in categories:
        normalized = _tag(category)
        if normalized:
            tags.add(normalized)

    text = " ".join([repo, path, template_name, " ".join(_workflow_events(workflow_data))]).lower()
    keyword_map = {
        "ci": ["ci", "test", "build"],
        "deployment": ["deploy", "release", "publish", "pages"],
        "security": ["security", "codeql", "scan"],
        "automation": ["automation", "cron", "schedule"],
        "python": ["python", "pip", "pytest"],
        "javascript": ["javascript", "node", "npm", "yarn", "pnpm"],
        "container": ["docker", "container"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    return sorted(tags)[:12]


def _credibility(
    *,
    categories: list[str],
    workflow_data: dict[str, Any],
    freshness_age_days: int | None,
) -> float:
    score = 0.55
    if categories:
        score += 0.1
    if _job_count(workflow_data) > 0 or _workflow_events(workflow_data):
        score += 0.1
    if freshness_age_days is not None and freshness_age_days <= 365:
        score += 0.1
    return min(score, 0.85)


def _repository_list(value: object, default: list[str]) -> list[str]:
    if isinstance(value, list):
        raw = [
            item.get("repository") or item.get("repo") if isinstance(item, dict) else item
            for item in value
        ]
    else:
        raw = value
    return _string_list(raw, default)


def _string_list(value: object, default: list[str]) -> list[str]:
    if value is None:
        values = list(default)
    elif isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return list(default)

    seen: set[str] = set()
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _template_key(entry: dict) -> str:
    name = _string_or_none(entry.get("name")) or ""
    for extension in _WORKFLOW_EXTENSIONS:
        if name.endswith(extension):
            return name[: -len(extension)]
    return name


def _strip_properties_suffix(name: str) -> str:
    return name[: -len(_PROPERTIES_SUFFIX)]


def _human_name(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def _primary_language(categories: list[str], path: str) -> str | None:
    if categories:
        return categories[0]
    text = path.lower()
    for language in ("python", "javascript", "typescript", "go", "ruby", "java", "docker"):
        if language in text:
            return language
    return None


def _tag(value: str) -> str:
    return "-".join(value.strip().lower().replace("_", "-").split())


def _stable_id(repo: str, path: str, workflow_entry: dict) -> str:
    sha = _string_or_none(workflow_entry.get("sha"))
    if sha:
        return f"github-workflow-template:{repo}:{path}:{sha}"
    return f"github-workflow-template:{repo}:{path}"


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _raise_http_error(error: httpx.HTTPStatusError, context: str, adapter_name: str) -> None:
    status = error.response.status_code
    if status == 429 or _is_github_rate_limit(error.response):
        raise SourceRateLimitError(
            f"Rate limit exceeded for {context}",
            adapter_name=adapter_name,
            retry_after=_retry_after_seconds(error.response),
        ) from error
    if status in (401, 403):
        raise SourceAuthError(
            f"Authentication failed (HTTP {status}) for {context}",
            adapter_name=adapter_name,
        ) from error
    if 500 <= status < 600:
        raise SourceTransientError(
            f"Server error (HTTP {status}) for {context}",
            adapter_name=adapter_name,
            retry_after=_retry_after_seconds(error.response),
        ) from error
    raise SourceTransientError(
        f"HTTP {status} for {context}",
        adapter_name=adapter_name,
    ) from error


def _retry_after_seconds(response: httpx.Response) -> float | None:
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return float(retry_after)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)


def _is_github_rate_limit(response: httpx.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    return response.status_code == 403 and remaining == "0"
