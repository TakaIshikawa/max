"""GitHub repository environments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubRepositoryEnvironmentsImportAdapter(SourceAdapter):
    """Fetch GitHub repository environments and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        base_url: str | None = None,
        repository: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or os.getenv("GITHUB_TOKEN")
                or os.getenv("GITHUB_ACCESS_TOKEN")
            )
        )
        self.api_url = (
            api_url
            or base_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("base_url"))
            or GITHUB_API
        ).rstrip("/")
        self._repository = repository
        self._owner = owner
        self._repo = repo
        self._client = client

    @property
    def name(self) -> str:
        return "github_repository_environments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def repositories(self) -> list[str]:
        explicit = _owner_repo_from_parts(self._owner, self._repo) or _owner_repo(self._repository)
        if explicit:
            return [explicit]

        configured = (
            self._config.get("repository")
            or self._config.get("repo")
            or self._config.get("repositories")
            or self._config.get("repos")
            or os.getenv("GITHUB_REPOSITORY")
        )
        repositories = _strings(configured)
        from_parts = _owner_repo_from_parts(self._config.get("owner"), self._config.get("repo"))
        if from_parts:
            repositories.insert(0, from_parts)
        return _dedupe([repo for repo in (_owner_repo(item) for item in repositories) if repo])

    @property
    def environment_names(self) -> set[str]:
        return {
            name.lower()
            for name in _strings(
                self._config.get("environment_names")
                or self._config.get("environments")
                or self._config.get("environment")
                or self._config.get("name")
            )
        }

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.repositories:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for repository in self.repositories:
                if len(signals) >= limit:
                    break
                environments = await self._fetch_repository(
                    client,
                    repository=repository,
                    limit=limit - len(signals),
                )
                for environment in environments:
                    signal = _environment_signal(environment, repository, self.name)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        *,
        repository: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        environments: list[dict[str, Any]] = []
        page = 1
        while len(environments) < limit:
            page_size = min(self.per_page, limit - len(environments))
            body = await self._get(
                client,
                f"{self.api_url}/repos/{_encode_repository(repository)}/environments",
                params={"per_page": page_size, "page": page},
            )
            page_environments = body.get("environments") if isinstance(body, dict) else []
            if not isinstance(page_environments, list) or not page_environments:
                break

            environments.extend(self._matching_environments(page_environments))
            if len(page_environments) < page_size:
                break
            page += 1
        return environments[:limit]

    def _matching_environments(self, values: list[object]) -> list[dict[str, Any]]:
        names = self.environment_names
        environments: list[dict[str, Any]] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            if names and _text(value.get("name")).lower() not in names:
                continue
            environments.append(value)
        return environments

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "max-github-repository-environments-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub repository environments fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


GitHubRepositoryEnvironmentsAdapter = GitHubRepositoryEnvironmentsImportAdapter


def _environment_signal(
    environment: dict[str, Any],
    repository: str,
    adapter_name: str,
) -> Signal | None:
    environment_id = _optional(environment.get("id")) or _optional(environment.get("node_id")) or _optional(environment.get("name"))
    if not environment_id:
        return None

    name = _text(environment.get("name")) or "GitHub repository environment"
    protection_rules = _protection_rules(environment.get("protection_rules"))
    branch_policy = _deployment_branch_policy(environment.get("deployment_branch_policy"))
    rule_tags = [_text(rule.get("type")) for rule in protection_rules if isinstance(rule, dict)]
    return Signal(
        id=f"github-repository-environment:{repository}:{environment_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{repository} environment {name}",
        content=_content(name=name, protection_rules=protection_rules, branch_policy=branch_policy),
        url=_text(environment.get("html_url") or environment.get("url")),
        author=None,
        published_at=_parse_dt(environment.get("updated_at") or environment.get("created_at")),
        tags=sorted({"github", "repository-environment", "deployment-gate", name, *rule_tags} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "release_readiness",
            "github_environment_id": environment.get("id"),
            "environment_id": environment.get("id"),
            "node_id": environment.get("node_id"),
            "repository": repository,
            "name": environment.get("name"),
            "url": environment.get("url"),
            "html_url": environment.get("html_url"),
            "created_at": environment.get("created_at"),
            "updated_at": environment.get("updated_at"),
            "protection_rules": protection_rules,
            "deployment_branch_policy": branch_policy,
            "raw": environment,
        },
    )


def _content(
    *,
    name: str,
    protection_rules: list[dict[str, Any]],
    branch_policy: dict[str, Any],
) -> str:
    parts = [f"GitHub repository environment {name}"]
    if protection_rules:
        rule_types = sorted({_text(rule.get("type")) for rule in protection_rules if _text(rule.get("type"))})
        parts.append(f"protection rules {', '.join(rule_types)}")
    protected_branches = _bool_or_none(branch_policy.get("protected_branches"))
    custom_branch_policies = _bool_or_none(branch_policy.get("custom_branch_policies"))
    if protected_branches is not None:
        parts.append(f"protected branches {protected_branches}")
    if custom_branch_policies is not None:
        parts.append(f"custom branch policies {custom_branch_policies}")
    return "; ".join(parts)[:1000]


def _protection_rules(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rules: list[dict[str, Any]] = []
    for rule in value:
        if not isinstance(rule, dict):
            continue
        reviewers = rule.get("reviewers") if isinstance(rule.get("reviewers"), list) else []
        rules.append(
            {
                key: result
                for key, result in {
                    "id": rule.get("id"),
                    "type": rule.get("type"),
                    "wait_timer": rule.get("wait_timer"),
                    "prevent_self_review": rule.get("prevent_self_review"),
                    "reviewers": [_reviewer_summary(reviewer) for reviewer in reviewers if isinstance(reviewer, dict)],
                }.items()
                if result not in (None, "", [])
            }
        )
    return rules


def _reviewer_summary(value: dict[str, Any]) -> dict[str, Any]:
    reviewer = value.get("reviewer") if isinstance(value.get("reviewer"), dict) else {}
    return {
        key: result
        for key, result in {
            "type": value.get("type"),
            "id": reviewer.get("id"),
            "login": reviewer.get("login"),
            "name": reviewer.get("name"),
            "slug": reviewer.get("slug"),
            "html_url": reviewer.get("html_url"),
        }.items()
        if result not in (None, "")
    }


def _deployment_branch_policy(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: result
        for key, result in {
            "protected_branches": _bool_or_none(value.get("protected_branches")),
            "custom_branch_policies": _bool_or_none(value.get("custom_branch_policies")),
        }.items()
        if result is not None
    }


def _owner_repo_from_parts(owner: object, repo: object) -> str | None:
    owner_text = _optional(owner)
    repo_text = _optional(repo)
    return f"{owner_text}/{repo_text}" if owner_text and repo_text else None


def _owner_repo(value: object) -> str | None:
    text = _optional(value)
    if not text or "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    return f"{owner}/{repo}" if owner and repo else None


def _encode_repository(repository: str) -> str:
    owner, repo = repository.split("/", 1)
    return f"{quote(owner, safe='')}/{quote(repo, safe='')}"


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list | tuple | set):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
