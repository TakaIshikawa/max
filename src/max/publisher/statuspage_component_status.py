"""Statuspage component status publisher."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from max.publisher._tact_spec_publish import (
    DEFAULT_TIMEOUT_SECONDS,
    optional_text,
    quote_path,
    redact_text,
    required_text,
    required_url,
    response_json,
    response_preview,
)

DEFAULT_API_URL = "https://api.statuspage.io"
ALLOWED_STATUSES = {
    "operational",
    "degraded_performance",
    "partial_outage",
    "major_outage",
    "under_maintenance",
}


class StatuspageComponentStatusPublishError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        secrets: list[str | None] | None = None,
    ) -> None:
        super().__init__(redact_text(message, secrets=secrets))
        self.status_code = status_code


@dataclass(frozen=True)
class StatuspageComponentStatusPayload:
    page_id: str
    component_id: str
    status: str
    name: str | None = None
    description: str | None = None
    only_show_if_degraded: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "page_id": self.page_id,
            "component_id": self.component_id,
            "status": self.status,
        }
        if self.name is not None:
            payload["name"] = self.name
        if self.description is not None:
            payload["description"] = self.description
        if self.only_show_if_degraded is not None:
            payload["only_show_if_degraded"] = self.only_show_if_degraded
        return payload

    def to_request(self) -> dict[str, Any]:
        component: dict[str, Any] = {"status": self.status}
        if self.name is not None:
            component["name"] = self.name
        if self.description is not None:
            component["description"] = self.description
        if self.only_show_if_degraded is not None:
            component["only_show_if_degraded"] = self.only_show_if_degraded
        return {"component": component}


@dataclass(frozen=True)
class StatuspageComponentStatusPublishResult:
    status_code: int | None
    page_id: str
    component_id: str
    dry_run: bool
    endpoint: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None


class StatuspageComponentStatusPublisher:
    def __init__(
        self,
        *,
        page_id: str | None = None,
        component_id: str | None = None,
        status: str | None = None,
        name: str | None = None,
        description: str | None = None,
        only_show_if_degraded: bool | None = None,
        api_key: str | None = None,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.page_id = optional_text(page_id)
        self.component_id = optional_text(component_id)
        self.status = _validate_status(status)
        self.name = optional_text(name)
        self.description = optional_text(description)
        self.only_show_if_degraded = only_show_if_degraded
        self.api_key = optional_text(api_key)
        self.api_url = required_url(api_url, "Statuspage api_url must be an absolute http(s) URL")
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(cls, **kwargs: Any) -> StatuspageComponentStatusPublisher:
        return cls(
            page_id=kwargs.pop("page_id", None) or os.getenv("STATUSPAGE_PAGE_ID"),
            component_id=kwargs.pop("component_id", None) or os.getenv("STATUSPAGE_COMPONENT_ID"),
            status=kwargs.pop("status", None) or os.getenv("STATUSPAGE_COMPONENT_STATUS"),
            name=kwargs.pop("name", None) or os.getenv("STATUSPAGE_COMPONENT_NAME"),
            description=kwargs.pop("description", None) or os.getenv("STATUSPAGE_COMPONENT_DESCRIPTION"),
            only_show_if_degraded=(
                kwargs.pop("only_show_if_degraded", None)
                if "only_show_if_degraded" in kwargs
                else _env_bool("STATUSPAGE_ONLY_SHOW_IF_DEGRADED")
            ),
            api_key=kwargs.pop("api_key", None) or os.getenv("STATUSPAGE_API_KEY"),
            api_url=kwargs.pop("api_url", None) or os.getenv("STATUSPAGE_API_URL", DEFAULT_API_URL),
            **kwargs,
        )

    def component_endpoint(
        self,
        *,
        page_id: str | None = None,
        component_id: str | None = None,
    ) -> str:
        page = required_text(optional_text(page_id) or self.page_id, "Statuspage page_id is required; pass page_id or set STATUSPAGE_PAGE_ID")
        component = required_text(optional_text(component_id) or self.component_id, "Statuspage component_id is required; pass component_id or set STATUSPAGE_COMPONENT_ID")
        return f"{self.api_url}/v1/pages/{quote_path(page)}/components/{quote_path(component)}"

    def build_payload(
        self,
        *,
        page_id: str | None = None,
        component_id: str | None = None,
        status: str | None = None,
        name: str | None = None,
        description: str | None = None,
        only_show_if_degraded: bool | None = None,
    ) -> StatuspageComponentStatusPayload:
        page = required_text(optional_text(page_id) or self.page_id, "Statuspage page_id is required; pass page_id or set STATUSPAGE_PAGE_ID")
        component = required_text(optional_text(component_id) or self.component_id, "Statuspage component_id is required; pass component_id or set STATUSPAGE_COMPONENT_ID")
        resolved_status = _validate_status(status) if status is not None else _require_status(self.status)
        return StatuspageComponentStatusPayload(
            page_id=page,
            component_id=component,
            status=resolved_status,
            name=optional_text(name) or self.name,
            description=optional_text(description) or self.description,
            only_show_if_degraded=(
                self.only_show_if_degraded
                if only_show_if_degraded is None
                else only_show_if_degraded
            ),
        )

    def publish(self, *, dry_run: bool = True, **kwargs: Any) -> StatuspageComponentStatusPublishResult:
        payload = self.build_payload(**kwargs)
        endpoint = self.component_endpoint(page_id=payload.page_id, component_id=payload.component_id)
        payload_dict = payload.to_dict()
        if dry_run:
            return StatuspageComponentStatusPublishResult(
                None, payload.page_id, payload.component_id, True, endpoint, payload_dict
            )

        if not self.api_key:
            raise StatuspageComponentStatusPublishError(
                "STATUSPAGE_API_KEY is required for live Statuspage component status publishing; use dry_run to preview",
                secrets=self._secrets(),
            )
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.patch(
                endpoint,
                json=payload.to_request(),
                headers=self._headers(),
                timeout=self.timeout,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            raise StatuspageComponentStatusPublishError(
                f"Statuspage component status publish failed for {endpoint}: {exc}",
                secrets=self._secrets(),
            ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise StatuspageComponentStatusPublishError(
                "Statuspage component status publish failed with HTTP "
                f"{response.status_code}: {response_preview(response, secrets=self._secrets())}",
                status_code=response.status_code,
                secrets=self._secrets(),
            )
        response_body = response_json(
            response,
            StatuspageComponentStatusPublishError,
            "Statuspage component status publish failed: response was not valid JSON",
        )
        return StatuspageComponentStatusPublishResult(
            response.status_code,
            payload.page_id,
            payload.component_id,
            False,
            endpoint,
            payload_dict,
            response_body,
        )

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"OAuth {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "max-statuspage-component-status-publisher/1",
        }

    def _secrets(self) -> list[str | None]:
        return [self.api_key]


StatuspageComponentStatusesPublisher = StatuspageComponentStatusPublisher


def _validate_status(value: str | None) -> str | None:
    status = optional_text(value)
    if status is None:
        return None
    if status not in ALLOWED_STATUSES:
        raise StatuspageComponentStatusPublishError(
            f"Statuspage component status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"
        )
    return status


def _require_status(value: str | None) -> str:
    status = _validate_status(value)
    if status is None:
        raise StatuspageComponentStatusPublishError(
            "Statuspage component status is required; pass status or set STATUSPAGE_COMPONENT_STATUS"
        )
    return status


def _env_bool(name: str) -> bool | None:
    value = optional_text(os.getenv(name))
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "y", "on"}
