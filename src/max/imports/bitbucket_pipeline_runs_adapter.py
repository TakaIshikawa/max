"""Bitbucket pipeline runs import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
BITBUCKET_API = "https://api.bitbucket.org/2.0"


class BitbucketPipelineRunsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        username: str | None = None,
        app_password: str | None = None,
        token: str | None = None,
        bearer_token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.username = username if username is not None else (
            _optional(self._config.get("username")) or os.getenv("BITBUCKET_USERNAME")
        )
        self.app_password = app_password if app_password is not None else (
            _optional(self._config.get("app_password"))
            or _optional(self._config.get("password"))
            or os.getenv("BITBUCKET_APP_PASSWORD")
        )
        self.token = token if token is not None else (
            bearer_token
            or _optional(self._config.get("token"))
            or _optional(self._config.get("bearer_token"))
            or os.getenv("BITBUCKET_TOKEN")
            or os.getenv("BITBUCKET_BEARER_TOKEN")
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or BITBUCKET_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "bitbucket_pipeline_runs_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def workspace(self) -> str | None:
        return _optional(self._config.get("workspace"))

    @property
    def repositories(self) -> list[str]:
        return _strings(
            self._config.get("repositories")
            or self._config.get("repository")
            or self._config.get("repo_slugs")
            or self._config.get("repo_slug")
            or self._config.get("repos")
            or self._config.get("repo")
        )

    @property
    def branches(self) -> list[str]:
        return _strings(self._config.get("branches") or self._config.get("branch"))

    @property
    def statuses(self) -> list[str]:
        return _strings(self._config.get("statuses") or self._config.get("status") or self._config.get("states"))

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("page_len") or self._config.get("pagelen"),
            default=30,
            maximum=100,
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.token or (self.username and self.app_password))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        targets = self._targets()
        if limit <= 0 or not targets or not self._has_auth:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for target in targets:
                if len(signals) >= limit:
                    break
                runs = await self._fetch_pipeline_runs(
                    client,
                    workspace=target["workspace"],
                    repository=target["repository"],
                    limit=limit - len(signals),
                )
                for run in runs:
                    signal = _pipeline_signal(
                        run,
                        workspace=target["workspace"],
                        repository=target["repository"],
                        adapter_name=self.name,
                        seen=seen,
                    )
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    def _targets(self) -> list[dict[str, str]]:
        configured = self._config.get("targets") or self._config.get("pipeline_targets")
        targets: list[dict[str, str]] = []
        if isinstance(configured, list):
            for item in configured:
                target = _target_from_mapping(item, default_workspace=self.workspace)
                if target:
                    targets.append(target)
        if targets:
            return targets

        workspace = self.workspace
        if not workspace:
            return []
        return [{"workspace": workspace, "repository": repository} for repository in self.repositories]

    async def _fetch_pipeline_runs(
        self,
        client: httpx.AsyncClient,
        *,
        workspace: str,
        repository: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        url: str | None = f"{self.api_url}/repositories/{workspace}/{repository}/pipelines/"
        params: dict[str, Any] | None = {"pagelen": min(self.page_size, limit)}
        if self.branches:
            params["target.ref_name"] = self.branches
        if self.statuses:
            params["status"] = self.statuses

        while url and len(runs) < limit:
            body = await self._get(client, url, params=params)
            values = body.get("values") if isinstance(body.get("values"), list) else []
            if not values:
                break
            runs.extend(item for item in values if isinstance(item, dict))
            url = _optional(body.get("next"))
            params = None
        return runs[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "max-bitbucket-pipeline-runs-import/1"}
        auth = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            auth = httpx.BasicAuth(self.username or "", self.app_password or "")
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Bitbucket pipeline runs fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


BitbucketPipelineRunsAdapter = BitbucketPipelineRunsImportAdapter


def _pipeline_signal(
    run: dict[str, Any],
    *,
    workspace: str,
    repository: str,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    run_id = _optional(run.get("uuid") or run.get("build_number") or run.get("id") or run.get("created_on"))
    if not run_id:
        return None
    external_id = f"bitbucket-pipeline-run:{workspace}:{repository}:{run_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    state = _nested(run.get("state"))
    target = _nested(run.get("target"))
    commit = _nested(target.get("commit") or run.get("commit"))
    creator = _nested(run.get("creator") or run.get("user"))
    status = _status(state, run)
    branch = _optional(target.get("ref_name") or target.get("branch") or run.get("branch"))
    commit_hash = _optional(commit.get("hash") or target.get("commit_hash") or run.get("commit_hash"))
    trigger = _trigger(run)
    duration = _int(run.get("duration_in_seconds") or run.get("duration") or run.get("build_seconds_used"))
    url = _pipeline_url(run)

    return Signal(
        id=external_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{workspace}/{repository} pipeline {status or 'unknown'}",
        content=_content(status=status, branch=branch, commit_hash=commit_hash, trigger=trigger, duration=duration)[:1000],
        url=url,
        author=_optional(creator.get("display_name") or creator.get("nickname") or creator.get("username")),
        published_at=_parse_dt(run.get("created_on") or run.get("started_on")),
        tags=sorted({"bitbucket", "pipeline", (status or "").lower(), (branch or "").lower()} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "failure_data",
            "pipeline_uuid": run.get("uuid") or run.get("id"),
            "build_number": run.get("build_number"),
            "workspace": workspace,
            "repository": repository,
            "state": state,
            "status": status,
            "branch": branch,
            "target": target,
            "commit": commit,
            "commit_hash": commit_hash,
            "trigger": trigger,
            "duration": duration,
            "duration_in_seconds": duration,
            "creator": _summary(creator),
            "created_on": run.get("created_on"),
            "started_on": run.get("started_on"),
            "completed_on": run.get("completed_on"),
            "url": url,
            "links": run.get("links"),
            "raw": run,
        },
    )


def _target_from_mapping(value: object, *, default_workspace: str | None) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    workspace = _optional(value.get("workspace")) or default_workspace
    repository = _optional(
        value.get("repository") or value.get("repo") or value.get("repo_slug") or value.get("slug")
    )
    if repository and "/" in repository:
        workspace = workspace or repository.split("/", 1)[0]
        repository = repository.rsplit("/", 1)[1]
    if not (workspace and repository):
        return None
    return {"workspace": workspace, "repository": repository}


def _status(state: dict[str, Any], run: dict[str, Any]) -> str | None:
    result = state.get("result") if isinstance(state.get("result"), dict) else {}
    return _optional(
        result.get("name")
        or result.get("type")
        or state.get("name")
        or state.get("type")
        or run.get("status")
        or run.get("state")
    )


def _trigger(run: dict[str, Any]) -> str | None:
    trigger = run.get("trigger")
    if isinstance(trigger, dict):
        return _optional(trigger.get("name") or trigger.get("type"))
    return _optional(trigger)


def _content(*, status: str | None, branch: str | None, commit_hash: str | None, trigger: str | None, duration: int) -> str:
    parts = [
        f"status {status}" if status else "",
        f"branch {branch}" if branch else "",
        f"commit {commit_hash[:12]}" if commit_hash else "",
        f"trigger {trigger}" if trigger else "",
        f"duration {duration}s" if duration else "",
    ]
    return ", ".join(part for part in parts if part) or "Bitbucket pipeline run"


def _pipeline_url(run: dict[str, Any]) -> str:
    links = run.get("links") if isinstance(run.get("links"), dict) else {}
    for key in ("html", "self"):
        href = _link_href(links.get(key))
        if href:
            return href
    return ""


def _link_href(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("href"))
    return ""


def _nested(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "uuid": value.get("uuid"),
        "display_name": value.get("display_name"),
        "nickname": value.get("nickname"),
        "username": value.get("username"),
        "links": value.get("links"),
    }


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


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
