"""GitHub Actions source adapter -- CI failure signals from workflow runs."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

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
_DEFAULT_CONCLUSIONS = ["failure", "cancelled", "timed_out"]
_DEFAULT_STATUSES = ["completed"]


class GitHubActionsAdapter(SourceAdapter):
    """Fetch GitHub Actions workflow failures and normalize them into signals."""

    @property
    def name(self) -> str:
        return "github_actions"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"), [])

    @property
    def workflow_names(self) -> list[str]:
        return _string_list(
            self._config.get("workflow_names", self._config.get("workflows")),
            [],
        )

    @property
    def conclusions(self) -> list[str]:
        return _string_list(self._config.get("conclusions"), _DEFAULT_CONCLUSIONS)

    @property
    def statuses(self) -> list[str]:
        return _string_list(self._config.get("statuses", self._config.get("status")), _DEFAULT_STATUSES)

    @property
    def max_age_days(self) -> int | None:
        value = self._config.get("max_age_days")
        if value is None or isinstance(value, bool):
            return None
        try:
            days = int(value)
        except (TypeError, ValueError):
            return None
        return days if days > 0 else None

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

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_actions")
    async def _fetch_runs_page(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        status: str,
        per_page: int,
        page: int,
        cutoff: datetime | None,
    ) -> tuple[list[dict], bool]:
        try:
            params: dict[str, object] = {
                "status": status,
                "per_page": per_page,
                "page": page,
            }
            if cutoff is not None:
                params["created"] = f">={cutoff.date().isoformat()}"

            resp = await client.get(
                f"{GITHUB_API}/repos/{repo}/actions/runs",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _raise_http_error(e, f"workflow runs for repository: {repo}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse workflow runs for repository: {repo}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
            raise SourceParseError(
                f"Unexpected workflow runs response for repository: {repo}",
                adapter_name=self.name,
            )

        return data["workflow_runs"], _has_next_page(resp)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        workflow_names = {name.lower() for name in self.workflow_names}
        conclusions = {conclusion.lower() for conclusion in self.conclusions}
        cutoff = _cutoff(self.max_age_days)
        per_page = min(max(limit, 5), 100)

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for repo in self.repositories:
                if len(signals) >= limit:
                    break

                for status in self.statuses:
                    page = 1
                    has_next = True
                    while has_next and len(signals) < limit:
                        runs, has_next = await self._fetch_runs_page(
                            client,
                            repo,
                            status=status,
                            per_page=per_page,
                            page=page,
                            cutoff=cutoff,
                        )
                        _append_run_signals(
                            signals,
                            runs,
                            adapter_name=self.name,
                            repo=repo,
                            status=status,
                            limit=limit,
                            seen_urls=seen_urls,
                            workflow_names=workflow_names,
                            conclusions=conclusions,
                            cutoff=cutoff,
                        )
                        page += 1

        return signals[:limit]


def _append_run_signals(
    signals: list[Signal],
    runs: list[dict],
    *,
    adapter_name: str,
    repo: str,
    status: str,
    limit: int,
    seen_urls: set[str],
    workflow_names: set[str],
    conclusions: set[str],
    cutoff: datetime | None,
) -> None:
    for run in runs:
        if len(signals) >= limit:
            break
        if not isinstance(run, dict) or not _matches_filters(
            run,
            workflow_names=workflow_names,
            conclusions=conclusions,
            cutoff=cutoff,
        ):
            continue

        html_url = str(run.get("html_url") or "")
        if not html_url or html_url in seen_urls:
            continue
        seen_urls.add(html_url)
        signals.append(_to_signal(run, adapter_name=adapter_name, repo=repo, status=status))


def _matches_filters(
    run: dict,
    *,
    workflow_names: set[str],
    conclusions: set[str],
    cutoff: datetime | None,
) -> bool:
    conclusion = str(run.get("conclusion") or "").strip().lower()
    if conclusions and conclusion not in conclusions:
        return False

    workflow_name = str(run.get("name") or run.get("workflow_name") or "").strip().lower()
    if workflow_names and workflow_name not in workflow_names:
        return False

    recency_dt = _parse_dt(run.get("updated_at") or run.get("created_at") or run.get("run_started_at"))
    return not (cutoff is not None and recency_dt is not None and recency_dt < cutoff)


def _to_signal(run: dict, *, adapter_name: str, repo: str, status: str) -> Signal:
    workflow_name = str(run.get("name") or run.get("workflow_name") or "GitHub Actions workflow").strip()
    conclusion = str(run.get("conclusion") or "").strip()
    run_number = run.get("run_number")
    branch = str(run.get("head_branch") or "").strip()
    event = str(run.get("event") or "").strip()
    commit_sha = str(run.get("head_sha") or "").strip()
    title = _title(repo, workflow_name, conclusion, run_number)
    content_parts = [
        f"Workflow {workflow_name} concluded with {conclusion or 'unknown'}",
        f"Repository: {repo}",
    ]
    if branch:
        content_parts.append(f"Branch: {branch}")
    if event:
        content_parts.append(f"Event: {event}")
    if commit_sha:
        content_parts.append(f"Commit: {commit_sha}")

    metadata = {
        "repo": repo,
        "repository": repo,
        "workflow_name": workflow_name,
        "run_id": run.get("id"),
        "run_number": run_number,
        "status": run.get("status") or status,
        "conclusion": conclusion,
        "branch": branch,
        "commit_sha": commit_sha,
        "event": event,
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "run_started_at": run.get("run_started_at"),
        "signal_role": "problem",
    }

    return Signal(
        id=_stable_id(run),
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=title,
        content="\n".join(content_parts),
        url=str(run.get("html_url") or ""),
        author=_author(run),
        published_at=_parse_dt(run.get("run_started_at") or run.get("created_at")),
        tags=_build_tags(repo, workflow_name, conclusion, branch, event),
        credibility=_credibility(conclusion),
        metadata=metadata,
    )


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


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cutoff(max_age_days: int | None) -> datetime | None:
    if max_age_days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _has_next_page(response: httpx.Response) -> bool:
    link = response.headers.get("Link", "")
    return 'rel="next"' in link


def _stable_id(run: dict) -> str:
    run_id = run.get("id")
    if run_id is not None:
        return f"github_actions:{run_id}"
    return f"github_actions:{run.get('html_url', '')}"


def _author(run: dict) -> str | None:
    actor = run.get("actor")
    if isinstance(actor, dict):
        login = actor.get("login")
        return str(login) if login else None
    triggering_actor = run.get("triggering_actor")
    if isinstance(triggering_actor, dict):
        login = triggering_actor.get("login")
        return str(login) if login else None
    return None


def _title(repo: str, workflow_name: str, conclusion: str, run_number: object) -> str:
    number = f" #{run_number}" if run_number is not None else ""
    result = conclusion or "failed"
    return f"{repo} {workflow_name}{number} {result}"


def _build_tags(repo: str, workflow_name: str, conclusion: str, branch: str, event: str) -> list[str]:
    tags: set[str] = {"github", "actions", "ci", "failure"}
    if conclusion:
        tags.add(conclusion)
    text = " ".join([repo, workflow_name, branch, event]).lower()
    keyword_map = {
        "python": ["python", "pytest", "tox"],
        "typescript": ["typescript", "javascript", "node", "npm", "pnpm", "yarn"],
        "security": ["security", "audit", "vulnerability"],
        "deployment": ["deploy", "release", "publish"],
        "test": ["test", "pytest", "jest", "vitest", "ci"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    return sorted(tags)[:10]


def _credibility(conclusion: str) -> float:
    if conclusion == "failure":
        return 0.7
    if conclusion in {"timed_out", "cancelled"}:
        return 0.6
    return 0.5


def _raise_http_error(error: httpx.HTTPStatusError, context: str, adapter_name: str) -> None:
    status = error.response.status_code
    if status == 429 or _is_github_rate_limit(error.response):
        retry_after = _retry_after_seconds(error.response)
        raise SourceRateLimitError(
            f"Rate limit exceeded for {context}",
            adapter_name=adapter_name,
            retry_after=retry_after,
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
