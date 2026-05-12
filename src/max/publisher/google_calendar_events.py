"""Google Calendar event publisher for generated TactSpec previews."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from max.publisher._tact_spec_publish import DEFAULT_TIMEOUT_SECONDS, add_minutes, iso_datetime, markdown_summary, metadata, optional_text, quote_path, required_text, required_url, response_json, response_preview, title, validate_tact_spec

DEFAULT_API_URL = "https://www.googleapis.com"


class GoogleCalendarEventPublishError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GoogleCalendarEventPayload:
    calendar_id: str
    event: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"calendar_id": self.calendar_id, "event": self.event, "metadata": self.metadata}


@dataclass(frozen=True)
class GoogleCalendarEventPublishResult:
    status_code: int | None
    event_id: str | None
    event_link: str | None
    dry_run: bool
    payload: dict[str, Any]


class GoogleCalendarEventPublisher:
    def __init__(self, *, calendar_id: str | None = None, access_token: str | None = None, api_url: str = DEFAULT_API_URL, default_duration_minutes: int = 30, timezone: str = "UTC", timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> None:
        self.calendar_id = optional_text(calendar_id)
        self.access_token = optional_text(access_token)
        self.api_url = required_url(api_url, "Google Calendar api_url must be an absolute http(s) URL")
        self.default_duration_minutes = int(default_duration_minutes)
        self.timezone = optional_text(timezone) or "UTC"
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, *, calendar_id: str | None = None, access_token: str | None = None, api_url: str | None = None, default_duration_minutes: int | None = None, timezone: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS, client: httpx.Client | None = None) -> GoogleCalendarEventPublisher:
        return cls(calendar_id=calendar_id or os.getenv("GOOGLE_CALENDAR_ID"), access_token=access_token or os.getenv("GOOGLE_CALENDAR_ACCESS_TOKEN"), api_url=api_url or os.getenv("GOOGLE_CALENDAR_API_URL", DEFAULT_API_URL), default_duration_minutes=default_duration_minutes or int(os.getenv("GOOGLE_CALENDAR_DEFAULT_DURATION_MINUTES", "30")), timezone=timezone or os.getenv("GOOGLE_CALENDAR_TIMEZONE", "UTC"), timeout=timeout, client=client)

    @property
    def events_endpoint(self) -> str:
        cid = required_text(self.calendar_id, "GOOGLE_CALENDAR_ID is required for Google Calendar event publishing")
        return f"{self.api_url}/calendar/v3/calendars/{quote_path(cid)}/events"

    def build_event_payload(self, tact_spec: dict[str, Any], *, start: datetime | None = None, end: datetime | None = None, calendar_id: str | None = None) -> GoogleCalendarEventPayload:
        try:
            validate_tact_spec(tact_spec, label="Google Calendar event")
            resolved_calendar_id = required_text(optional_text(calendar_id) or self.calendar_id, "GOOGLE_CALENDAR_ID is required for Google Calendar event publishing")
        except ValueError as exc:
            raise GoogleCalendarEventPublishError(str(exc)) from exc
        meta = metadata(tact_spec, publisher="max.google_calendar_events")
        event: dict[str, Any] = {"summary": title(tact_spec), "description": markdown_summary(tact_spec, meta), "extendedProperties": {"private": {k: str(v) for k, v in meta.items() if v is not None}}}
        if start is not None:
            event["start"] = {"dateTime": iso_datetime(start), "timeZone": self.timezone}
            event["end"] = {"dateTime": iso_datetime(end or add_minutes(start, self.default_duration_minutes)), "timeZone": self.timezone}
        return GoogleCalendarEventPayload(resolved_calendar_id, event, meta)

    def publish(self, tact_spec: dict[str, Any], *, dry_run: bool = True, start: datetime | None = None, end: datetime | None = None, calendar_id: str | None = None) -> GoogleCalendarEventPublishResult:
        payload = self.build_event_payload(tact_spec, start=start, end=end, calendar_id=calendar_id).to_dict()
        if dry_run:
            return GoogleCalendarEventPublishResult(None, None, None, True, payload)
        if not self.access_token:
            raise GoogleCalendarEventPublishError("GOOGLE_CALENDAR_ACCESS_TOKEN is required for live Google Calendar event publishing; use dry_run to preview")
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(self.events_endpoint, json=payload["event"], headers={"Authorization": f"Bearer {self.access_token}", "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "max-google-calendar-events-publisher/1"}, timeout=self.timeout)
        finally:
            if close_client:
                client.close()
        if not 200 <= response.status_code < 300:
            raise GoogleCalendarEventPublishError(f"Google Calendar event publish failed with HTTP {response.status_code}: {response_preview(response, secrets=[self.access_token])}", status_code=response.status_code)
        body = response_json(response, GoogleCalendarEventPublishError, "Google Calendar event publish failed: response was not valid JSON")
        return GoogleCalendarEventPublishResult(response.status_code, optional_text(body.get("id")), optional_text(body.get("htmlLink")), False, payload)


GoogleCalendarEventsPublisher = GoogleCalendarEventPublisher
