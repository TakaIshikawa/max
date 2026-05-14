"""CircleCI project pipelines import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
CIRCLECI_API = "https://circleci.com/api/v2"


class CircleCIProjectPipelinesImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (
            _optional(self._config.get("token"))
            or os.getenv("CIRCLECI_TOKEN")
            or os.getenv("CIRCLE_TOKEN")
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or CIRCLECI_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "circleci_project_pipelines_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def project_slugs(self) -> list[str]:
        return _strings(
            self._config.get("project_slugs")
            or self._config.get("project_slug")
            or self._config.get("projects")
        )

    @property
    def statuses(self) -> set[str]:
        return set(_strings(self._config.get("statuses") or self._config.get("status")))

    @property
    def branch(self) -> str | None:
        return _optional(self._config.get("branch"))

    @property
    def mine(self) -> bool | None:
        value = self._config.get("mine")
        return value if isinstance(value, bool) else None

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("limit"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_slugs:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for project_slug in self.project_slugs:
                if len(signals) >= limit:
                    break
                pipelines = await self._fetch_project_pipelines(
                    client,
                    project_slug=project_slug,
                    limit=limit - len(signals),
                )
                if pipelines is None:
                    return []
                for pipeline in pipelines:
                    signal = _pipeline_signal(pipeline, project_slug, self.name, seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_pipelines(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        pipelines: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(pipelines) < limit:
            body = await self._get(
                client,
                f"{self.api_url}/project/{project_slug}/pipeline",
                params=self._params(page_token=page_token),
            )
            if body is None:
                return None
            items = body.get("items") if isinstance(body, dict) else []
            if not isinstance(items, list) or not items:
                break
            for item in items:
                if isinstance(item, dict) and self._matches_status(item):
                    pipelines.append(item)
                if len(pipelines) >= limit:
                    break
            page_token = _optional(body.get("next_page_token"))
            if not page_token:
                break
        return pipelines[:limit]

    def _params(self, *, page_token: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"page-size": self.page_size}
        if page_token:
            params["page-token"] = page_token
        if self.branch:
            params["branch"] = self.branch
        if self.mine is not None:
            params["mine"] = "true" if self.mine else "false"
        return params

    def _matches_status(self, pipeline: dict[str, Any]) -> bool:
        statuses = self.statuses
        if not statuses:
            return True
        return _text(pipeline.get("state") or pipeline.get("status")) in statuses

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        try:
            response = await client.get(
                url,
                headers={"Circle-Token": self.token or "", "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("CircleCI project pipelines fetch failed for %s", url, exc_info=True)
            return None
        return body if isinstance(body, dict) else {}


CircleCIProjectPipelinesAdapter = CircleCIProjectPipelinesImportAdapter


def _pipeline_signal(
    pipeline: dict[str, Any],
    configured_project_slug: str,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    pipeline_id = _optional(pipeline.get("id") or pipeline.get("number") or pipeline.get("created_at"))
    if not pipeline_id:
        return None
    project_slug = _text(pipeline.get("project_slug")) or configured_project_slug
    external_id = f"circleci-project-pipeline:{project_slug}:{pipeline_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    state = _text(pipeline.get("state") or pipeline.get("status"))
    number = pipeline.get("number")
    vcs = pipeline.get("vcs") if isinstance(pipeline.get("vcs"), dict) else {}
    revision = _optional(vcs.get("revision"))
    branch = _optional(vcs.get("branch") or pipeline.get("branch"))
    trigger = pipeline.get("trigger") if isinstance(pipeline.get("trigger"), dict) else {}
    return Signal(
        id=external_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_slug} pipeline #{number or pipeline_id} {state or 'unknown'}",
        content=_content(state=state, branch=branch, revision=revision)[:1000],
        url=_pipeline_url(pipeline),
        author=_optional(trigger.get("received_at") and trigger.get("actor", {}).get("login") if isinstance(trigger.get("actor"), dict) else pipeline.get("created_by")),
        published_at=_parse_dt(pipeline.get("created_at")),
        tags=sorted({"circleci", "pipeline", state, project_slug, branch or ""} - {""})[:10],
        credibility=0.7,
        metadata={
            "pipeline_id": pipeline.get("id"),
            "number": number,
            "project_slug": project_slug,
            "state": state,
            "created_at": pipeline.get("created_at"),
            "updated_at": pipeline.get("updated_at"),
            "vcs": vcs,
            "revision": revision,
            "branch": branch,
            "trigger": trigger,
            "errors": pipeline.get("errors"),
            "url": _pipeline_url(pipeline),
            "raw": pipeline,
        },
    )


def _content(*, state: str, branch: str | None, revision: str | None) -> str:
    parts = [
        f"state {state}" if state else "",
        f"branch {branch}" if branch else "",
        f"revision {revision[:12]}" if revision else "",
    ]
    return ", ".join(part for part in parts if part) or "CircleCI project pipeline"


def _pipeline_url(pipeline: dict[str, Any]) -> str:
    return _text(pipeline.get("web_url") or pipeline.get("url"))


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
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
