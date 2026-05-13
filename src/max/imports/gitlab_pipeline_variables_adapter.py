"""GitLab pipeline variables import adapter."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote, unquote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITLAB_API = "https://gitlab.com/api/v4"


class GitLabPipelineVariablesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        private_token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            private_token
            if private_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("private_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("GITLAB_PRIVATE_TOKEN")
                    or os.getenv("GITLAB_TOKEN")
                )
            )
        )
        self.api_url = _api_url(
            api_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("gitlab_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        )
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_pipeline_variables_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_ids(self) -> list[str]:
        return _strings(
            self._config.get("project_ids")
            or self._config.get("projects")
            or self._config.get("project_id")
        )

    @property
    def pipeline_ids(self) -> list[str]:
        return _strings(
            self._config.get("pipeline_ids")
            or self._config.get("pipelines")
            or self._config.get("pipeline_id")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    @property
    def per_pipeline_limit(self) -> int | None:
        value = self._config.get("per_pipeline_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_ids or not self.pipeline_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_id in self.project_ids:
                for pipeline_id in self.pipeline_ids:
                    if len(signals) >= limit:
                        break
                    pipeline_limit = min(self.per_pipeline_limit or limit, limit - len(signals))
                    variables = await self._fetch_variables(
                        client,
                        project_id=project_id,
                        pipeline_id=pipeline_id,
                        limit=pipeline_limit,
                    )
                    signals.extend(
                        _variable_signal(
                            variable,
                            project_id=project_id,
                            pipeline_id=pipeline_id,
                            adapter_name=self.name,
                        )
                        for variable in variables
                        if isinstance(variable, dict)
                    )
                if len(signals) >= limit:
                    break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_variables(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        pipeline_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        variables: list[dict[str, Any]] = []
        page = 1
        while len(variables) < limit:
            page_size = min(self.page_size, limit - len(variables))
            page_variables, next_page = await self._fetch_page(
                client,
                project_id=project_id,
                pipeline_id=pipeline_id,
                page=page,
                page_size=page_size,
            )
            if not page_variables:
                break
            variables.extend(page_variables[: limit - len(variables)])
            if next_page:
                page = next_page
            else:
                break
        return variables[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        pipeline_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int | None]:
        url = f"{self.api_url}/projects/{_encode_project(project_id)}/pipelines/{quote(pipeline_id, safe='')}/variables"
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-pipeline-variables-import/1",
                },
                params={"page": page, "per_page": page_size},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab pipeline variables fetch failed for %s pipeline %s", project_id, pipeline_id, exc_info=True)
            return [], None
        variables = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return variables, _next_page(response)


GitLabPipelineVariableAdapter = GitLabPipelineVariablesAdapter


def _variable_signal(
    variable: dict[str, Any],
    *,
    project_id: str,
    pipeline_id: str,
    adapter_name: str,
) -> Signal:
    key = _text(variable.get("key")) or _text(variable.get("id")) or "pipeline-variable"
    variable_type = _text(variable.get("variable_type"))
    protected = variable.get("protected")
    masked = variable.get("masked")
    title = f"GitLab pipeline variable {key}"
    url = f"https://gitlab.com/{project_id}/-/pipelines/{pipeline_id}"
    return Signal(
        id=f"gitlab-pipeline-variable:{project_id}:{pipeline_id}:{key}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=_content(key=key, variable_type=variable_type, protected=protected, masked=masked),
        url=url,
        author=None,
        tags=sorted(
            {
                "gitlab",
                "pipeline-variable",
                project_id,
                f"pipeline:{pipeline_id}",
                variable_type,
                "protected" if protected is True else "",
                "masked" if masked is True else "",
            }
            - {""}
        )[:10],
        credibility=0.65,
        metadata={
            "signal_role": "roadmap",
            "key": key,
            "variable_type": variable.get("variable_type"),
            "project_id": project_id,
            "pipeline_id": pipeline_id,
            "protected": protected,
            "masked": masked,
            "url": url,
            "raw": variable,
        },
    )


def _content(*, key: str, variable_type: str, protected: object, masked: object) -> str:
    parts = [f"GitLab pipeline variable {key}"]
    if variable_type:
        parts.append(f"type {variable_type}")
    if protected is True:
        parts.append("protected")
    if masked is True:
        parts.append("masked")
    return "; ".join(parts)


def _api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.endswith("/api/v4"):
        url = f"{url}/api/v4"
    return url


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _next_page(response: httpx.Response) -> int | None:
    value = _optional(response.headers.get("X-Next-Page"))
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number > 0 else None


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
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, dict):
            item = item.get("id") or item.get("iid") or item.get("path")
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
