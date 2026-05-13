"""GitHub check runs import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubCheckRunsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "github_check_runs_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def targets(self) -> list[dict[str, str]]:
        explicit = self._config.get("check_targets") or self._config.get("targets")
        targets = _targets(explicit)
        if targets:
            return targets
        repositories = _strings(self._config.get("repositories") or self._config.get("repos"))
        refs = _strings(self._config.get("refs") or self._config.get("ref")) or ["HEAD"]
        return [{"repository": repository, "ref": ref} for repository in repositories for ref in refs if _owner_repo(repository)]

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.targets:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for target in self.targets:
                if len(signals) >= limit:
                    break
                repository = _owner_repo(target.get("repository", ""))
                ref = _optional(target.get("ref"))
                if not repository or not ref:
                    continue
                runs = await self._fetch_target(client, repository=repository, ref=ref, limit=limit - len(signals))
                signals.extend(_check_run_signal(run, repository=repository, ref=ref, adapter_name=self.name) for run in runs)
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_target(self, client: httpx.AsyncClient, *, repository: str, ref: str, limit: int) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        page = 1
        while len(runs) < limit:
            page_size = min(self.per_page, limit - len(runs))
            body = await self._get(
                client,
                f"{self.api_url}/repos/{repository}/commits/{ref}/check-runs",
                params=self._params(page_size=page_size, page=page),
            )
            page_runs = body.get("check_runs") if isinstance(body, dict) else []
            if not isinstance(page_runs, list) or not page_runs:
                break
            runs.extend(item for item in page_runs if isinstance(item, dict))
            if len(page_runs) < page_size:
                break
            page += 1
        return runs[:limit]

    def _params(self, *, page_size: int, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"per_page": page_size, "page": page}
        for config_key, param_key in (("status", "status"), ("conclusion", "filter"), ("check_name", "check_name")):
            value = _optional(self._config.get(config_key))
            if value:
                params[param_key] = value
        return params

    async def _get(self, client: httpx.AsyncClient, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "max-github-check-runs-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub check runs fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


GitHubCheckRunsImportAdapter = GitHubCheckRunsAdapter


def _check_run_signal(run: dict[str, Any], *, repository: str, ref: str, adapter_name: str) -> Signal:
    app = run.get("app") if isinstance(run.get("app"), dict) else {}
    output = run.get("output") if isinstance(run.get("output"), dict) else {}
    status = _text(run.get("status"))
    conclusion = _text(run.get("conclusion"))
    name = _text(run.get("name"))
    run_id = _text(run.get("id"))
    return Signal(
        id=f"github-check-run:{repository}:{ref}:{run_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{repository} {name or 'check run'} {conclusion or status or 'unknown'}",
        content=_content(name=name, status=status, conclusion=conclusion, output=output),
        url=_text(run.get("html_url")),
        author=_optional(app.get("slug") or app.get("name")),
        published_at=_parse_dt(run.get("started_at") or run.get("created_at")),
        tags=sorted({"github", "check-run", status, conclusion, name} - {""})[:10],
        credibility=0.7,
        metadata={
            "signal_role": "failure_data",
            "check_run_id": run.get("id"),
            "repository": repository,
            "ref": ref,
            "name": name,
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "details_url": run.get("details_url"),
            "html_url": run.get("html_url"),
            "started_at": run.get("started_at"),
            "completed_at": run.get("completed_at"),
            "head_sha": run.get("head_sha"),
            "app": {"id": app.get("id"), "slug": app.get("slug"), "name": app.get("name")},
            "output": output,
        },
    )


def _content(*, name: str, status: str, conclusion: str, output: dict[str, Any]) -> str:
    parts = [name or "GitHub check run"]
    if status:
        parts.append(f"status {status}")
    if conclusion:
        parts.append(f"conclusion {conclusion}")
    summary = _text(output.get("summary") or output.get("title"))
    if summary:
        parts.append(summary)
    return "; ".join(parts)[:1000]


def _targets(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    targets: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        repository = _optional(item.get("repository") or item.get("repo"))
        ref = _optional(item.get("ref") or item.get("sha") or item.get("branch"))
        if repository and ref and _owner_repo(repository):
            targets.append({"repository": repository, "ref": ref})
    return targets


def _owner_repo(value: str) -> str | None:
    text = value.strip()
    if "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    return f"{owner}/{repo}" if owner and repo else None


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


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
