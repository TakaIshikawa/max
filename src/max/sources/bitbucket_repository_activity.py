"""Bitbucket repository activity source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class BitbucketRepositoryActivityAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "bitbucket_repository_activity"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def bitbucket_url(self) -> str:
        return str(self._config.get("bitbucket_url") or "https://api.bitbucket.org/2.0").strip().rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for url, params in _requests(self._config, self.bitbucket_url):
                while url and len(signals) < limit:
                    response = await client.get(url, params=params)
                    params = None
                    if response.status_code >= 400:
                        break
                    payload = response.json()
                    for repo in payload.get("values", []):
                        signals.append(_signal(repo))
                        if len(signals) >= limit:
                            break
                    url = payload.get("next")
        return signals


def _requests(config: dict[str, Any], base: str) -> list[tuple[str, dict[str, Any]]]:
    requests = []
    workspaces = _strings(config.get("workspaces"))
    for workspace in workspaces:
        params: dict[str, Any] = {"pagelen": int(config.get("max_repositories") or 30)}
        queries = _strings(config.get("queries"))
        project_keys = _strings(config.get("project_keys"))
        clauses = []
        clauses.extend(f'project.key="{p}"' for p in project_keys)
        clauses.extend(f'name~"{q}"' for q in queries)
        if clauses:
            params["q"] = " OR ".join(clauses)
        requests.append((f"{base}/repositories/{workspace}", params))
    return requests


def _signal(repo: dict[str, Any]) -> Signal:
    links = repo.get("links") if isinstance(repo.get("links"), dict) else {}
    html = (links.get("html") or {}).get("href") if isinstance(links.get("html"), dict) else repo.get("website") or ""
    full_name = repo.get("full_name") or repo.get("name") or repo.get("uuid")
    return Signal(
        id=_id("bitbucket-repo", repo.get("uuid") or full_name),
        source_type=SignalSourceType.REGISTRY,
        source_adapter="bitbucket_repository_activity",
        title=f"{full_name} Bitbucket repository activity",
        content=f"{full_name} activity updated {repo.get('updated_on') or 'unknown'}.",
        url=str(html),
        published_at=_parse_dt(repo.get("updated_on")),
        tags=["bitbucket", str(repo.get("language") or "").lower()],
        credibility=0.6,
        metadata={"repository_id": repo.get("uuid") or full_name, "repository": full_name, "language": repo.get("language") or "", "updated_on": repo.get("updated_on") or "", "fork_count": repo.get("forks_count") or repo.get("fork_count") or 0, "watcher_count": repo.get("watchers_count") or repo.get("watcher_count") or 0, "has_issues": bool(repo.get("has_issues") or repo.get("issue_tracker")), "links": links, "source_url": html, "signal_role": "market"},
    )


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    return [str(v).strip() for v in values if str(v).strip()]


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]
