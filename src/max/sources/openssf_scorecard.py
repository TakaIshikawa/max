"""OpenSSF Scorecard source adapter -- repository supply-chain trust signals."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

SCORECARD_API = "https://api.securityscorecards.dev/projects"
SCORECARD_VIEWER = "https://securityscorecards.dev/viewer/"
_DEFAULT_TOKEN_ENV = "SCORECARD_TOKEN"


class OpenSSFScorecardAdapter(SourceAdapter):
    """Fetch OpenSSF Scorecard results and normalize risky checks."""

    @property
    def name(self) -> str:
        return "openssf_scorecard"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"))

    @property
    def checks(self) -> list[str]:
        return _string_list(self._config.get("checks"))

    @property
    def min_risk_score(self) -> float:
        value = _float_or_none(self._config.get("min_risk_score"))
        return max(value or 1.0, 0.0)

    @property
    def local_paths(self) -> list[str]:
        values = _string_list(self._config.get("local_paths"))
        local_path = self._config.get("local_path")
        if isinstance(local_path, str) and local_path.strip():
            values.insert(0, local_path.strip())
        return _dedupe(values)

    @property
    def token_env(self) -> str:
        configured = self._config.get("token_env")
        return configured.strip() if isinstance(configured, str) and configured.strip() else _DEFAULT_TOKEN_ENV

    @property
    def token(self) -> str | None:
        configured = self._config.get("token")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return os.environ.get(self.token_env)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()

        for payload in self._load_local_payloads():
            self._append_payload_signals(signals, payload, limit=limit, seen=seen)
            if len(signals) >= limit:
                return signals[:limit]

        if self.local_paths:
            return signals[:limit]

        headers = {
            "Accept": "application/json",
            "User-Agent": "max-openssf-scorecard-adapter/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for repo in self.repositories:
                if len(signals) >= limit:
                    break
                payload = await self._fetch_scorecard(client, repo)
                if payload is None:
                    continue
                self._append_payload_signals(signals, payload, limit=limit, seen=seen, repo_hint=repo)

        return signals[:limit]

    def _load_local_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for local_path in self.local_paths:
            try:
                data = json.loads(Path(local_path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("%s: failed to read local Scorecard JSON %s: %s", self.name, local_path, e)
                continue
            payloads.extend(_extract_scorecard_results(data))
        return payloads

    async def _fetch_scorecard(
        self,
        client: httpx.AsyncClient,
        repo: str,
    ) -> dict[str, Any] | None:
        try:
            resp = await fetch_with_retry(
                _scorecard_api_url(repo),
                client,
                adapter_name=self.name,
            )
            payload = resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Scorecard for %s: %s", self.name, repo, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse Scorecard response for %s: %s", self.name, repo, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: unexpected Scorecard response for %s", self.name, repo)
            return None
        return payload

    def _append_payload_signals(
        self,
        signals: list[Signal],
        payload: dict[str, Any],
        *,
        limit: int,
        seen: set[str],
        repo_hint: str | None = None,
    ) -> None:
        repo = _repo_name(payload, repo_hint=repo_hint)
        if repo is None or not self._repo_allowed(repo):
            return

        check_names = {check.lower() for check in self.checks}
        for check in _extract_checks(payload):
            if len(signals) >= limit:
                break
            signal = _signal_from_check(
                payload,
                check,
                adapter_name=self.name,
                repo=repo,
                min_risk_score=self.min_risk_score,
                check_names=check_names,
            )
            if signal is None or signal.id in seen:
                continue
            seen.add(signal.id)
            signals.append(signal)

    def _repo_allowed(self, repo: str) -> bool:
        if not self.repositories:
            return True
        normalized_repo = _normalize_repo(repo)
        return any(_normalize_repo(configured) == normalized_repo for configured in self.repositories)


def _signal_from_check(
    payload: dict[str, Any],
    check: dict[str, Any],
    *,
    adapter_name: str,
    repo: str,
    min_risk_score: float,
    check_names: set[str],
) -> Signal | None:
    check_name = _string_or_none(check.get("name"))
    if check_name is None:
        return None
    if check_names and check_name.lower() not in check_names:
        return None

    check_score = _float_or_none(check.get("score"))
    if check_score is None or check_score < 0:
        return None

    risk_score = max(10.0 - check_score, 0.0)
    if risk_score < min_risk_score:
        return None

    date = _string_or_none(payload.get("date"))
    overall_score = _float_or_none(payload.get("score"))
    reason = _string_or_none(check.get("reason")) or "Scorecard check reported elevated risk."
    details_url = _details_url(check, repo)
    published_at = _parse_datetime(date)
    title = f"OpenSSF Scorecard risk: {repo} {check_name} scored {_format_score(check_score)}"
    content = (
        f"Repository {repo} has a low OpenSSF Scorecard result for {check_name}: "
        f"{reason}"
    )

    metadata = {
        "repo": repo,
        "repository": repo,
        "date": date,
        "overall_score": overall_score,
        "check_name": check_name,
        "check_score": check_score,
        "risk_score": risk_score,
        "reason": reason,
        "details_url": details_url,
        "details": _details(check),
        "signal_role": "problem",
    }

    return Signal(
        id=f"{adapter_name}:{_normalize_repo(repo)}:{check_name.lower().replace(' ', '-')}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=title[:240],
        content=content[:500],
        url=details_url,
        published_at=published_at,
        tags=_build_tags(repo, check_name, risk_score),
        credibility=_credibility(check_score),
        metadata=metadata,
    )


def _scorecard_api_url(repo: str) -> str:
    return f"{SCORECARD_API}/{quote(_api_repo_ref(repo), safe='/')}"


def _api_repo_ref(repo: str) -> str:
    normalized = repo.strip().removeprefix("https://").removeprefix("http://").removesuffix("/")
    if normalized.startswith("github.com/"):
        return normalized
    return f"github.com/{normalized}"


def _extract_scorecard_results(data: object) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("checks"), list):
        return [data]
    for key in ("results", "items", "data", "scorecards"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_checks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return []
    return [check for check in checks if isinstance(check, dict)]


def _repo_name(payload: dict[str, Any], *, repo_hint: str | None) -> str | None:
    repo = payload.get("repo")
    if isinstance(repo, dict):
        name = _string_or_none(repo.get("name") or repo.get("url"))
        if name:
            return _normalize_repo(name)
    name = _string_or_none(payload.get("repo") or payload.get("repository") or payload.get("repository_url"))
    if name:
        return _normalize_repo(name)
    return _normalize_repo(repo_hint) if repo_hint else None


def _details_url(check: dict[str, Any], repo: str) -> str:
    for key in ("details_url", "detailsUrl", "url"):
        value = _string_or_none(check.get(key))
        if value:
            return value
    documentation = check.get("documentation")
    if isinstance(documentation, dict):
        value = _string_or_none(documentation.get("url"))
        if value:
            return value
    return f"{SCORECARD_VIEWER}?uri=github.com/{quote(_normalize_repo(repo), safe='/')}"


def _details(check: dict[str, Any]) -> list[str]:
    details = check.get("details")
    if isinstance(details, list):
        return [str(item) for item in details if item is not None][:10]
    if isinstance(details, str) and details.strip():
        return [details.strip()]
    return []


def _build_tags(repo: str, check_name: str, risk_score: float) -> list[str]:
    tags = ["security", "supply-chain", "openssf-scorecard", check_name.lower()]
    owner = _normalize_repo(repo).split("/", 1)[0]
    if owner:
        tags.append(owner)
    if risk_score >= 7:
        tags.append("high-risk")
    elif risk_score >= 4:
        tags.append("medium-risk")
    else:
        tags.append("low-risk")
    return _dedupe(tags)


def _credibility(check_score: float) -> float:
    risk_score = max(10.0 - check_score, 0.0)
    return min(max(round(0.55 + risk_score * 0.04, 3), 0.55), 0.95)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_repo(repo: str | None) -> str:
    if repo is None:
        return ""
    normalized = repo.strip().removeprefix("https://").removeprefix("http://").removesuffix("/")
    normalized = normalized.removeprefix("github.com/")
    return normalized


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


def _format_score(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


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


OpenssfScorecardAdapter = OpenSSFScorecardAdapter
