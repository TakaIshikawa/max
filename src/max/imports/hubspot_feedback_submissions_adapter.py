"""HubSpot feedback submissions import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
HUBSPOT_API = "https://api.hubapi.com"
DEFAULT_FEEDBACK_SUBMISSION_PROPERTIES = [
    "hs_createdate",
    "hs_lastmodifieddate",
    "hs_submission_name",
    "hs_feedback_submission_name",
    "hs_feedback_rating",
    "hs_feedback_sentiment",
    "hs_feedback_source",
    "hs_content",
    "createdate",
]


class HubSpotFeedbackSubmissionsAdapter(SourceAdapter):
    """Fetch HubSpot feedback submissions and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        access_token: str | None = None,
        private_app_token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            or access_token
            or private_app_token
            or _optional(self._config.get("token"))
            or _optional(self._config.get("access_token"))
            or _optional(self._config.get("private_app_token"))
            or os.getenv("HUBSPOT_ACCESS_TOKEN")
            or os.getenv("HUBSPOT_PRIVATE_APP_TOKEN")
            or os.getenv("HUBSPOT_TOKEN")
        )
        self.api_url = (
            api_url
            or _optional(self._config.get("api_url"))
            or os.getenv("HUBSPOT_API_URL")
            or HUBSPOT_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_feedback_submissions_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def properties(self) -> list[str]:
        return _strings(self._config.get("properties")) or DEFAULT_FEEDBACK_SUBMISSION_PROPERTIES

    @property
    def associations(self) -> list[str]:
        return _strings(self._config.get("associations") or self._config.get("association_types"))

    @property
    def archived(self) -> bool | None:
        return _bool_or_none_config(self._config.get("archived"))

    @property
    def after(self) -> str | None:
        return _optional(self._config.get("after"))

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("per_page") or self._config.get("limit"),
            default=100,
            maximum=100,
        )

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            submissions = await self._fetch_submissions(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for submission in submissions:
            signal = _submission_signal(submission, adapter_name=self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_submissions(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        submissions: list[dict[str, Any]] = []
        after = self.after
        while len(submissions) < limit:
            page_size = min(self.page_size, limit - len(submissions))
            body = await self._get(client, limit=page_size, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            submissions.extend(item for item in results if isinstance(item, dict))
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return submissions[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "properties": self.properties}
        if self.associations:
            params["associations"] = self.associations
        if self.archived is not None:
            params["archived"] = str(self.archived).lower()
        if after:
            params["after"] = after

        try:
            response = await client.get(
                f"{self.api_url}/crm/v3/objects/feedback_submissions",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-hubspot-feedback-submissions-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot feedback submissions fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


HubSpotFeedbackSubmissionAdapter = HubSpotFeedbackSubmissionsAdapter


def _submission_signal(
    submission: dict[str, Any],
    *,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    submission_id = _optional(submission.get("id"))
    if not submission_id:
        return None
    signal_id = f"hubspot-feedback-submission:{submission_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    props = submission.get("properties") if isinstance(submission.get("properties"), dict) else {}
    associations = submission.get("associations") if isinstance(submission.get("associations"), dict) else {}
    created_at = (
        props.get("hs_createdate")
        or props.get("createdate")
        or submission.get("createdAt")
        or submission.get("created_at")
    )
    updated_at = props.get("hs_lastmodifieddate") or submission.get("updatedAt") or submission.get("updated_at")
    title = (
        _text(props.get("hs_submission_name"))
        or _text(props.get("hs_feedback_submission_name"))
        or f"HubSpot feedback submission {submission_id}"
    )
    content = _content(props=props, title=title)
    rating = _text(props.get("hs_feedback_rating"))
    sentiment = _text(props.get("hs_feedback_sentiment"))
    source = _text(props.get("hs_feedback_source"))
    signal_role = "problem" if sentiment.lower() in {"negative", "detractor", "poor", "bad"} else "market"

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content=content,
        url=_submission_url(submission, submission_id=submission_id),
        author=_text(props.get("hubspot_owner_id")) or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"hubspot", "feedback-submission", rating.lower(), sentiment.lower(), source.lower()} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": signal_role,
            "hubspot_feedback_submission_id": submission.get("id"),
            "feedback_submission_id": submission.get("id"),
            "properties": props,
            "associations": associations,
            "created_at": created_at,
            "updated_at": updated_at,
            "archived": submission.get("archived"),
            "raw": submission,
        },
    )


def _content(*, props: dict[str, Any], title: str) -> str:
    body = _text(props.get("hs_content") or props.get("content") or props.get("body"))
    if body:
        return body
    parts = ["HubSpot feedback submission"]
    if title and not title.startswith("HubSpot feedback submission "):
        parts.append(title)
    rating = _text(props.get("hs_feedback_rating"))
    if rating:
        parts.append(f"rating {rating}")
    sentiment = _text(props.get("hs_feedback_sentiment"))
    if sentiment:
        parts.append(sentiment.lower())
    source = _text(props.get("hs_feedback_source"))
    if source:
        parts.append(f"source {source}")
    return "; ".join(parts)


def _submission_url(submission: dict[str, Any], *, submission_id: str) -> str:
    return _text(submission.get("url") or submission.get("webUrl")) or (
        f"https://app.hubspot.com/contacts/feedback-submission/{submission_id}" if submission_id else ""
    )


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


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


def _bool_or_none_config(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [item.strip() for item in str(value).split(",")]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
