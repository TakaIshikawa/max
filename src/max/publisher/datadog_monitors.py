"""Datadog monitor publisher for generated TactSpecs."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


DEFAULT_API_URL = "https://api.datadoghq.com"
DEFAULT_MONITOR_TYPE = "query alert"
DEFAULT_PRIORITY = 3
DEFAULT_TIMEOUT_SECONDS = 10.0
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "application_key",
    "app_key",
    "auth",
    "authorization",
    "client_secret",
    "dd-api-key",
    "dd-application-key",
    "key",
    "password",
    "secret",
    "token",
}


class DatadogMonitorPublishError(RuntimeError):
    """Raised when a Datadog monitor publish cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        secrets: list[str | None] | None = None,
    ) -> None:
        super().__init__(_redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class DatadogMonitorPayload:
    """Datadog monitor creation payload plus Max-specific metadata."""

    name: str
    message: str
    query: str
    tags: list[str]
    priority: int
    metadata: dict[str, Any]
    notify: list[str]
    type: str = DEFAULT_MONITOR_TYPE

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable monitor payload preview."""
        return {
            "name": self.name,
            "type": self.type,
            "query": self.query,
            "message": self.message,
            "tags": self.tags,
            "priority": self.priority,
            "notify": self.notify,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DatadogMonitorPublishResult:
    """Summary of a Datadog monitor publish or dry run."""

    status_code: int | None
    monitor_id: str | None
    monitor_url: str | None
    dry_run: bool
    payload: dict[str, Any]


class DatadogMonitorPublisher:
    """Build and optionally create Datadog monitors from TactSpec previews."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        app_key: str | None = None,
        site: str | None = None,
        api_url: str | None = None,
        tags: list[str] | None = None,
        notify: list[str] | None = None,
        query: str | None = None,
        priority: int = DEFAULT_PRIORITY,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = _optional_text(api_key)
        self.app_key = _optional_text(app_key)
        self.site = _normalize_site(site)
        self.api_url = _normalize_api_url(api_url, site=self.site)
        self.tags = [_tag_value(tag) for tag in tags or [] if _tag_value(tag)]
        self.notify = [_notify_value(handle) for handle in notify or [] if _notify_value(handle)]
        self.query = _optional_text(query)
        self.priority = _required_int(priority, "Datadog monitor priority must be an integer")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        api_key: str | None = None,
        app_key: str | None = None,
        site: str | None = None,
        api_url: str | None = None,
        tags: list[str] | None = None,
        notify: list[str] | None = None,
        query: str | None = None,
        priority: int | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> DatadogMonitorPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_api_url = api_url or os.getenv("DATADOG_API_URL")
        resolved_site = site or os.getenv("DATADOG_SITE")
        return cls(
            api_key=api_key or os.getenv("DATADOG_API_KEY"),
            app_key=app_key or os.getenv("DATADOG_APP_KEY"),
            site=resolved_site,
            api_url=resolved_api_url,
            tags=tags if tags is not None else _env_list("DATADOG_TAGS"),
            notify=notify if notify is not None else _env_list("DATADOG_NOTIFY"),
            query=query,
            priority=priority if priority is not None else DEFAULT_PRIORITY,
            timeout=timeout,
            client=client,
        )

    @property
    def monitor_endpoint(self) -> str:
        """Return the Datadog REST endpoint used for monitor creation."""
        return f"{self.api_url}/api/v1/monitor"

    def build_monitor_payload(self, tact_spec: dict[str, Any]) -> DatadogMonitorPayload:
        """Convert a generated TactSpec preview into a Datadog monitor payload."""
        _validate_tact_spec(tact_spec)
        project = _dict_value(tact_spec, "project")
        source = _dict_value(tact_spec, "source")
        quality = _dict_value(tact_spec, "quality")
        evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

        source_type = str(source.get("type") or "idea")
        source_id = source.get("idea_id") or source.get("design_brief_id")
        metadata = {
            "publisher": "max.datadog_monitors",
            "source_system": source.get("system", "max"),
            "source_type": source_type,
            "source_id": source_id,
            "idea_id": source.get("idea_id"),
            "design_brief_id": source.get("design_brief_id"),
            "schema_version": tact_spec.get("schema_version"),
            "kind": tact_spec.get("kind"),
            "site": self.site,
        }

        return DatadogMonitorPayload(
            name=_monitor_name(project.get("title"), source_id),
            message=_monitor_message(tact_spec, metadata, self.notify),
            query=self.query or _monitor_query(source, source_id),
            tags=_merge_tags(
                _monitor_tags(source=source, quality=quality, evaluation=evaluation),
                self.tags,
            ),
            priority=self.priority,
            metadata=metadata,
            notify=self.notify,
        )

    def publish(
        self,
        tact_spec: dict[str, Any],
        *,
        dry_run: bool = True,
    ) -> DatadogMonitorPublishResult:
        """Build the monitor payload and optionally create it in Datadog."""
        payload = self.build_monitor_payload(tact_spec).to_dict()
        if dry_run:
            return DatadogMonitorPublishResult(
                status_code=None,
                monitor_id=None,
                monitor_url=None,
                dry_run=True,
                payload=payload,
            )

        if not self.api_key or not self.app_key:
            raise DatadogMonitorPublishError(
                "DATADOG_API_KEY and DATADOG_APP_KEY are required for live Datadog monitor "
                "publishing; use dry_run to preview",
                secrets=self._secrets,
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.monitor_endpoint,
                    json=_datadog_monitor_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                message = _redact_text(str(exc), secrets=self._secrets)
                raise DatadogMonitorPublishError(
                    f"Datadog monitor publish failed for "
                    f"{_redact_url(self.monitor_endpoint)}: {message}",
                    secrets=self._secrets,
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise DatadogMonitorPublishError(
                f"Datadog monitor publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response, secrets=self._secrets)}",
                status_code=response.status_code,
                secrets=self._secrets,
            )

        body = _json_response(response, secrets=self._secrets)
        monitor_id = body.get("id")
        if monitor_id is None:
            raise DatadogMonitorPublishError(
                "Datadog monitor publish failed: response did not include created monitor id",
                status_code=response.status_code,
                secrets=self._secrets,
            )

        monitor_url = self.monitor_url(monitor_id)
        return DatadogMonitorPublishResult(
            status_code=response.status_code,
            monitor_id=str(monitor_id),
            monitor_url=monitor_url,
            dry_run=False,
            payload={
                **payload,
                "metadata": {
                    **payload["metadata"],
                    "datadog_monitor_id": str(monitor_id),
                    "datadog_monitor_url": monitor_url,
                },
            },
        )

    def monitor_url(self, monitor_id: object) -> str:
        """Return the Datadog app URL for a monitor id."""
        return f"https://app.{self.site}/monitors/{monitor_id}"

    @property
    def _secrets(self) -> list[str | None]:
        return [self.api_key, self.app_key]

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None and self.app_key is not None
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "DD-API-KEY": self.api_key,
            "DD-APPLICATION-KEY": self.app_key,
            "User-Agent": "max-datadog-monitors-publisher/1",
        }


DatadogMonitorsPublisher = DatadogMonitorPublisher


def _datadog_monitor_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload["name"],
        "type": payload["type"],
        "query": payload["query"],
        "message": payload["message"],
        "tags": payload.get("tags") or [],
        "priority": payload["priority"],
        "options": {
            "include_tags": True,
            "notify_audit": False,
        },
    }


def _validate_tact_spec(tact_spec: dict[str, Any]) -> None:
    if not isinstance(tact_spec, dict):
        raise DatadogMonitorPublishError("Datadog monitor publishing requires a TactSpec dict")
    project = _dict_value(tact_spec, "project")
    source = _dict_value(tact_spec, "source")
    if not _optional_text(project.get("title")) and not (
        _optional_text(source.get("idea_id")) or _optional_text(source.get("design_brief_id"))
    ):
        raise DatadogMonitorPublishError(
            "Datadog monitor publishing requires project.title or a source id"
        )
    if not _optional_text(tact_spec.get("schema_version")):
        raise DatadogMonitorPublishError(
            "Datadog monitor publishing requires schema_version in the TactSpec payload"
        )


def _monitor_name(title: object, source_id: object) -> str:
    base = str(title).strip() if title else str(source_id or "Generated TactSpec").strip()
    return f"[Max] Runtime check: {base}"[:255]


def _monitor_message(
    tact_spec: dict[str, Any],
    metadata: dict[str, Any],
    notify: list[str],
) -> str:
    project = _dict_value(tact_spec, "project")
    problem = _dict_value(tact_spec, "problem")
    solution = _dict_value(tact_spec, "solution")
    execution = _dict_value(tact_spec, "execution")
    source = _dict_value(tact_spec, "source")
    evaluation = tact_spec.get("evaluation") if isinstance(tact_spec.get("evaluation"), dict) else {}

    lines = [
        f"Generated TactSpec runtime monitor for "
        f"{project.get('title') or source.get('idea_id') or source.get('design_brief_id') or 'Generated TactSpec'}.",
        "",
        f"Summary: {_text_or_placeholder(project.get('summary'))}",
        f"Problem: {_text_or_placeholder(problem.get('statement'))}",
        f"Approach: {_text_or_placeholder(solution.get('approach'))}",
        f"Validation: {_text_or_placeholder(execution.get('validation_plan'))}",
        f"Recommendation: {_text_or_placeholder(evaluation.get('recommendation'))}",
        "",
        "Max metadata:",
        "```json",
        json.dumps(metadata, indent=2, sort_keys=True),
        "```",
    ]
    if notify:
        lines.extend(["", " ".join(notify)])
    return "\n".join(lines)


def _monitor_query(source: dict[str, Any], source_id: object) -> str:
    service = _metric_token(source.get("domain")) or "max"
    source_tag = _metric_token(source_id) or _metric_token(source.get("type")) or "generated"
    return f"avg(last_5m):sum:max.tactspec.runtime_check{{service:{service},source:{source_tag}}} < 1"


def _monitor_tags(
    *,
    source: dict[str, Any],
    quality: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[str]:
    tags = [
        "max",
        "tact-spec",
        "publisher:datadog",
        _tag_pair("source_type", source.get("type") or "idea"),
        _tag_pair("source_system", source.get("system") or "max"),
        _tag_pair("domain", source.get("domain")),
        _tag_pair("category", source.get("category")),
        _tag_pair("status", source.get("status")),
        _tag_pair("recommendation", evaluation.get("recommendation")),
    ]
    tags.extend(_tag_pair("quality", tag) for tag in quality.get("rejection_tags") or [])
    return _unique(tags)


def _merge_tags(tags: list[str], extra_tags: list[str]) -> list[str]:
    return _unique([*tags, *(_tag_value(tag) for tag in extra_tags)])


def _unique(tags: list[str]) -> list[str]:
    unique: list[str] = []
    for tag in tags:
        if tag and tag not in unique:
            unique.append(tag)
    return unique


def _tag_pair(key: str, value: object) -> str:
    safe_value = _tag_value(value)
    return f"{key}:{safe_value}" if safe_value else ""


def _tag_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    safe = "".join(ch for ch in text if ch.isalnum() or ch in "-.:/")
    return safe[:255]


def _notify_value(value: object) -> str:
    text = str(value).strip() if value else ""
    return text if text.startswith("@") else f"@{text}" if text else ""


def _metric_token(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    return "".join(ch for ch in text if ch.isalnum() or ch in "-.")[:200]


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _text_or_placeholder(value: object) -> str:
    text = str(value).strip() if value else ""
    return text or "Not specified"


def _required_int(value: object, message: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DatadogMonitorPublishError(message) from exc


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value else ""
    return text or None


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_site(site: str | None) -> str:
    raw = _optional_text(site)
    if not raw:
        return "datadoghq.com"
    if "://" in raw:
        parts = urlsplit(raw)
        raw = parts.netloc or parts.path
    raw = raw.strip().lower().strip("/")
    if raw.startswith("api."):
        raw = raw.removeprefix("api.")
    if raw.startswith("app."):
        raw = raw.removeprefix("app.")
    if "/" in raw or not raw:
        raise DatadogMonitorPublishError("Datadog site must be a site host such as datadoghq.com")
    return raw


def _normalize_api_url(api_url: str | None, *, site: str) -> str:
    raw = _optional_text(api_url)
    if not raw:
        return f"https://api.{site}"
    if "://" not in raw:
        raw = f"https://{raw}"
    raw = raw.rstrip("/")
    if raw.endswith("/api/v1/monitor"):
        raw = raw[: -len("/api/v1/monitor")]
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise DatadogMonitorPublishError("Datadog api_url must be an absolute URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _response_body_preview(
    response: httpx.Response,
    *,
    secrets: list[str | None],
    limit: int = 500,
) -> str:
    text = _redact_text(response.text.strip(), secrets=secrets)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response, *, secrets: list[str | None]) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise DatadogMonitorPublishError(
            "Datadog monitor publish failed: response was not valid JSON",
            status_code=response.status_code,
            secrets=secrets,
        ) from exc
    return body if isinstance(body, dict) else {}


def _redact_text(text: str, *, secrets: list[str | None] | None = None) -> str:
    redacted = text
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    redacted = re.sub(
        r"(?i)\b(token|api_token|api_key|app_key|password|secret|authorization)\b([=:]\s*)"
        r"[^&\s,'\"}]+",
        r"\1\2<redacted>",
        redacted,
    )
    return _redact_url(redacted)


def _redact_url(text: str) -> str:
    words = text.split()
    return " ".join(_redact_url_word(word) for word in words)


def _redact_url_word(word: str) -> str:
    try:
        parts = urlsplit(word)
    except ValueError:
        return word
    if not parts.scheme or not parts.netloc:
        return word
    query = urlencode(
        [
            (key, "<redacted>" if key.lower() in SECRET_QUERY_KEYS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
