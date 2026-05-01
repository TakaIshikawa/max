"""GitHub workflow runs source adapter -- CI failure and latency signals."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
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
_DEFAULT_MAX_RUNS_PER_REPO = 30
_DEFAULT_SLOW_RUN_SECONDS = 20 * 60


class GitHubWorkflowRunsAdapter(SourceAdapter):
    """Fetch GitHub Actions workflow run failures and slow runs."""

    @property
    def name(self) -> str:
        return "github_workflow_runs"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"), [])

    @property
    def statuses(self) -> list[str]:
        return _string_list(self._config.get("statuses", self._config.get("status")), _DEFAULT_STATUSES)

    @property
    def conclusions(self) -> list[str]:
        return _string_list(self._config.get("conclusions"), _DEFAULT_CONCLUSIONS)

    @property
    def max_runs_per_repo(self) -> int:
        return _positive_int(self._config.get("max_runs_per_repo"), _DEFAULT_MAX_RUNS_PER_REPO)

    @property
    def slow_run_seconds(self) -> int:
        return _positive_int(self._config.get("slow_run_seconds"), _DEFAULT_SLOW_RUN_SECONDS)

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

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_workflow_runs")
    async def _fetch_runs_page(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        status: str,
        per_page: int,
        page: int,
    ) -> tuple[list[dict], bool]:
        try:
            resp = await client.get(
                f"{self.api_url}/repos/{repo}/actions/runs",
                params={
                    "status": status,
                    "per_page": per_page,
                    "page": page,
                },
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
        conclusions = {conclusion.lower() for conclusion in self.conclusions}
        per_page = min(max(self.max_runs_per_repo, 1), 100)

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            for repo in self.repositories:
                if len(signals) >= limit:
                    break
                for status in self.statuses:
                    if len(signals) >= limit:
                        break
                    await self._append_repo_status_signals(
                        client,
                        repo,
                        status=status,
                        per_page=per_page,
                        limit=limit,
                        seen_urls=seen_urls,
                        conclusions=conclusions,
                        signals=signals,
                    )

        return signals[:limit]

    async def _append_repo_status_signals(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        status: str,
        per_page: int,
        limit: int,
        seen_urls: set[str],
        conclusions: set[str],
        signals: list[Signal],
    ) -> None:
        page = 1
        has_next = True
        inspected = 0

        while has_next and inspected < self.max_runs_per_repo and len(signals) < limit:
            try:
                runs, has_next = await self._fetch_runs_page(
                    client,
                    repo,
                    status=status,
                    per_page=min(per_page, self.max_runs_per_repo - inspected),
                    page=page,
                )
            except (SourceRateLimitError, SourceAuthError):
                raise
            except (
                SourceTransientError,
                SourceParseError,
                httpx.RequestError,
                httpx.TimeoutException,
            ):
                logger.warning(
                    "GitHub workflow runs fetch failed for repo: %s status: %s",
                    repo,
                    status,
                    exc_info=True,
                )
                return

            inspected += len(runs)
            _append_run_signals(
                signals,
                runs,
                adapter_name=self.name,
                repo=repo,
                status=status,
                limit=limit,
                seen_urls=seen_urls,
                conclusions=conclusions,
                slow_run_seconds=self.slow_run_seconds,
            )
            page += 1


def _append_run_signals(
    signals: list[Signal],
    runs: list[dict],
    *,
    adapter_name: str,
    repo: str,
    status: str,
    limit: int,
    seen_urls: set[str],
    conclusions: set[str],
    slow_run_seconds: int,
) -> None:
    for run in runs:
        if len(signals) >= limit:
            break
        if not isinstance(run, dict) or not _matches_filters(
            run,
            conclusions=conclusions,
            slow_run_seconds=slow_run_seconds,
        ):
            continue

        html_url = str(run.get("html_url") or "")
        if not html_url or html_url in seen_urls:
            continue
        seen_urls.add(html_url)
        signals.append(_to_signal(run, adapter_name=adapter_name, repo=repo, status=status))


def _matches_filters(run: dict, *, conclusions: set[str], slow_run_seconds: int) -> bool:
    conclusion = str(run.get("conclusion") or "").strip().lower()
    if conclusions and conclusion in conclusions:
        return True

    duration_seconds = _duration_seconds(run)
    return duration_seconds is not None and duration_seconds >= slow_run_seconds


def _to_signal(run: dict, *, adapter_name: str, repo: str, status: str) -> Signal:
    workflow_name = str(run.get("name") or run.get("workflow_name") or "GitHub Actions workflow").strip()
    conclusion = str(run.get("conclusion") or "").strip()
    run_status = str(run.get("status") or status).strip()
    run_number = run.get("run_number")
    branch = str(run.get("head_branch") or "").strip()
    event = str(run.get("event") or "").strip()
    duration_seconds = _duration_seconds(run)
    queued_seconds = _queued_seconds(run)
    title = _title(repo, workflow_name, conclusion, run_status, run_number, duration_seconds)
    content_parts = [
        f"Workflow {workflow_name} finished with {conclusion or run_status or 'unknown'}",
        f"Repository: {repo}",
    ]
    if duration_seconds is not None:
        content_parts.append(f"Duration seconds: {duration_seconds}")
    if branch:
        content_parts.append(f"Branch: {branch}")
    if event:
        content_parts.append(f"Event: {event}")

    metadata = {
        "repo": repo,
        "repository": repo,
        "workflow_name": workflow_name,
        "run_id": run.get("id"),
        "run_number": run_number,
        "status": run_status,
        "conclusion": conclusion,
        "duration_seconds": duration_seconds,
        "queued_seconds": queued_seconds,
        "run_url": run.get("html_url"),
        "branch": branch,
        "commit_sha": run.get("head_sha"),
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
        tags=_build_tags(repo, workflow_name, conclusion, run_status, branch, event, duration_seconds),
        credibility=_credibility(conclusion, duration_seconds),
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


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_seconds(run: dict) -> int | None:
    started_at = _parse_dt(run.get("run_started_at") or run.get("created_at"))
    completed_at = _parse_dt(run.get("updated_at"))
    if started_at is None or completed_at is None:
        return None
    return max(int((completed_at - started_at).total_seconds()), 0)


def _queued_seconds(run: dict) -> int | None:
    created_at = _parse_dt(run.get("created_at"))
    started_at = _parse_dt(run.get("run_started_at"))
    if created_at is None or started_at is None:
        return None
    return max(int((started_at - created_at).total_seconds()), 0)


def _has_next_page(response: httpx.Response) -> bool:
    link = response.headers.get("Link", "")
    return 'rel="next"' in link


def _stable_id(run: dict) -> str:
    run_id = run.get("id")
    if run_id is not None:
        return f"github_workflow_runs:{run_id}"
    return f"github_workflow_runs:{run.get('html_url', '')}"


def _author(run: dict) -> str | None:
    actor = run.get("actor")
    if isinstance(actor, dict) and actor.get("login"):
        return str(actor["login"])
    triggering_actor = run.get("triggering_actor")
    if isinstance(triggering_actor, dict) and triggering_actor.get("login"):
        return str(triggering_actor["login"])
    return None


def _title(
    repo: str,
    workflow_name: str,
    conclusion: str,
    status: str,
    run_number: object,
    duration_seconds: int | None,
) -> str:
    number = f" #{run_number}" if run_number is not None else ""
    result = conclusion or status or "workflow run"
    duration = f" ({duration_seconds}s)" if duration_seconds is not None else ""
    return f"{repo} {workflow_name}{number} {result}{duration}"


def _build_tags(
    repo: str,
    workflow_name: str,
    conclusion: str,
    status: str,
    branch: str,
    event: str,
    duration_seconds: int | None,
) -> list[str]:
    tags: set[str] = {"github", "actions", "ci", "workflow-runs"}
    if conclusion:
        tags.add(conclusion)
    if status:
        tags.add(status)
    if duration_seconds is not None:
        tags.add("duration")
        if duration_seconds >= _DEFAULT_SLOW_RUN_SECONDS:
            tags.add("slow")

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


def _credibility(conclusion: str, duration_seconds: int | None) -> float:
    if conclusion == "failure":
        return 0.75
    if conclusion in {"timed_out", "cancelled"}:
        return 0.65
    if duration_seconds is not None and duration_seconds >= _DEFAULT_SLOW_RUN_SECONDS:
        return 0.6
    return 0.5


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
