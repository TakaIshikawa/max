"""GitLab epic publisher for generated roadmap artifacts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx


DEFAULT_GITLAB_BASE_URL = "https://gitlab.com"
DEFAULT_TIMEOUT_SECONDS = 10.0


class GitLabEpicPublishError(ValueError):
    """Raised when a GitLab epic publish cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabEpicPayload:
    """GitLab group epic creation payload plus target metadata."""

    provider: str
    group_id: str
    title: str
    description: str
    labels: list[str]
    start_date: str | None
    due_date: str | None
    parent_epic_id: int | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable epic payload preview."""
        return {
            "provider": self.provider,
            "group_id": self.group_id,
            "title": self.title,
            "description": self.description,
            "labels": self.labels,
            "start_date": self.start_date,
            "due_date": self.due_date,
            "parent_epic_id": self.parent_epic_id,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GitLabEpicPublishResult:
    """Summary of a GitLab epic publish or dry run."""

    status_code: int | None
    provider: str
    group_id: str
    target_url: str | None
    epic_id: int | None
    epic_iid: int | None
    dry_run: bool
    payload: dict[str, Any]


class GitLabEpicPublisher:
    """Create GitLab group epics from approved design briefs or generated specs."""

    def __init__(
        self,
        group_id: str | int | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        start_date: str | date | None = None,
        due_date: str | date | None = None,
        parent_epic_id: int | str | None = None,
        private_token: str | None = None,
        token: str | None = None,
        base_url: str = DEFAULT_GITLAB_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.group_id = _required_text(group_id, "GitLab group_id is required")
        self.title = _optional_text(title)
        self.description = _optional_text(description)
        self.labels = _labels(labels or [])
        self.start_date = _optional_date(start_date, "GitLab epic start_date")
        self.due_date = _optional_date(due_date, "GitLab epic due_date")
        self.parent_epic_id = _optional_positive_int(
            parent_epic_id,
            "GitLab parent_epic_id must be a positive integer",
        )
        self.private_token = _optional_text(private_token) or _optional_text(token)
        self.base_url = _required_url(base_url)
        self.timeout = timeout
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        group_id: str | int | None = None,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        start_date: str | date | None = None,
        due_date: str | date | None = None,
        parent_epic_id: int | str | None = None,
        private_token: str | None = None,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> GitLabEpicPublisher:
        """Create a publisher using API values first, then environment variables."""
        resolved_group = (
            group_id
            or os.getenv("GITLAB_GROUP_ID")
            or os.getenv("GITLAB_GROUP_PATH")
            or os.getenv("GITLAB_GROUP")
        )
        return cls(
            resolved_group,
            title=title or os.getenv("GITLAB_EPIC_TITLE"),
            description=description or os.getenv("GITLAB_EPIC_DESCRIPTION"),
            labels=labels or _env_labels("GITLAB_EPIC_LABELS"),
            start_date=start_date or os.getenv("GITLAB_EPIC_START_DATE"),
            due_date=due_date or os.getenv("GITLAB_EPIC_DUE_DATE"),
            parent_epic_id=parent_epic_id or os.getenv("GITLAB_PARENT_EPIC_ID"),
            private_token=(
                private_token
                or token
                or os.getenv("GITLAB_PRIVATE_TOKEN")
                or os.getenv("GITLAB_TOKEN")
            ),
            base_url=base_url or os.getenv("GITLAB_BASE_URL", DEFAULT_GITLAB_BASE_URL),
            timeout=timeout,
            client=client,
        )

    @property
    def epic_endpoint(self) -> str:
        """Return the GitLab REST endpoint used for group epic creation."""
        return f"{self.base_url}/api/v4/groups/{quote(self.group_id, safe='')}/epics"

    def build_epic_payload(
        self,
        artifact: dict[str, Any] | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        start_date: str | date | None = None,
        due_date: str | date | None = None,
        parent_epic_id: int | str | None = None,
    ) -> GitLabEpicPayload:
        """Build a deterministic GitLab epic payload."""
        source_artifact = _source_artifact(artifact)
        resolved_title = _required_text(
            title or self.title or source_artifact.get("title"),
            "GitLab epic title is required",
        )
        resolved_description = _required_text(
            description or self.description or source_artifact.get("description"),
            "GitLab epic description is required",
        )
        resolved_labels = _merge_labels(
            self.labels,
            _labels(labels or []),
            _labels(source_artifact.get("labels") or []),
        )
        resolved_start_date = _optional_date(
            start_date if start_date is not None else self.start_date,
            "GitLab epic start_date",
        )
        resolved_due_date = _optional_date(
            due_date if due_date is not None else self.due_date,
            "GitLab epic due_date",
        )
        resolved_parent_id = _optional_positive_int(
            parent_epic_id if parent_epic_id is not None else self.parent_epic_id,
            "GitLab parent_epic_id must be a positive integer",
        )
        return GitLabEpicPayload(
            provider="gitlab",
            group_id=self.group_id,
            title=resolved_title[:255],
            description=resolved_description,
            labels=resolved_labels,
            start_date=resolved_start_date,
            due_date=resolved_due_date,
            parent_epic_id=resolved_parent_id,
            metadata={
                "publisher": "max.gitlab_epics",
                "provider": "gitlab",
                "group_id": self.group_id,
                "source_type": source_artifact.get("type"),
                "source_id": source_artifact.get("id"),
            },
        )

    def publish(
        self,
        artifact: dict[str, Any] | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
        labels: list[str] | None = None,
        start_date: str | date | None = None,
        due_date: str | date | None = None,
        parent_epic_id: int | str | None = None,
        dry_run: bool = True,
    ) -> GitLabEpicPublishResult:
        """Publish or preview a GitLab group epic."""
        payload = self.build_epic_payload(
            artifact,
            title=title,
            description=description,
            labels=labels,
            start_date=start_date,
            due_date=due_date,
            parent_epic_id=parent_epic_id,
        ).to_dict()
        if dry_run:
            return GitLabEpicPublishResult(
                status_code=None,
                provider="gitlab",
                group_id=self.group_id,
                target_url=None,
                epic_id=None,
                epic_iid=None,
                dry_run=True,
                payload=payload,
            )

        if not self.private_token:
            raise GitLabEpicPublishError(
                "GITLAB_TOKEN or GITLAB_PRIVATE_TOKEN is required for live GitLab epic "
                "publishing; use dry_run to preview"
            )

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            try:
                response = client.post(
                    self.epic_endpoint,
                    json=_gitlab_epic_request(payload),
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                raise GitLabEpicPublishError(
                    f"GitLab epic publish failed for {self.epic_endpoint}: {exc}"
                ) from exc
        finally:
            if close_client:
                client.close()

        if not 200 <= response.status_code < 300:
            raise GitLabEpicPublishError(
                f"GitLab epic publish failed with HTTP {response.status_code}: "
                f"{_response_body_preview(response)}",
                status_code=response.status_code,
            )

        body = _json_response(response)
        epic_id = _int_or_none(body.get("id"))
        epic_iid = _int_or_none(body.get("iid"))
        target_url = _optional_text(body.get("web_url") or body.get("url"))
        if epic_id is None or epic_iid is None or not target_url:
            raise GitLabEpicPublishError(
                "GitLab epic publish failed: response did not include epic id, iid, and web_url",
                status_code=response.status_code,
            )

        return GitLabEpicPublishResult(
            status_code=response.status_code,
            provider="gitlab",
            group_id=self.group_id,
            target_url=target_url,
            epic_id=epic_id,
            epic_iid=epic_iid,
            dry_run=False,
            payload={
                **payload,
                "target_url": target_url,
                "epic_id": epic_id,
                "epic_iid": epic_iid,
                "request": _gitlab_epic_request(payload),
                "metadata": {
                    **payload["metadata"],
                    "gitlab_epic_id": epic_id,
                    "gitlab_epic_iid": epic_iid,
                    "gitlab_epic_url": target_url,
                },
            },
        )

    def _headers(self) -> dict[str, str]:
        assert self.private_token is not None
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "PRIVATE-TOKEN": self.private_token,
            "User-Agent": "max-gitlab-epics-publisher/1",
        }


GitLabEpicsPublisher = GitLabEpicPublisher


def _gitlab_epic_request(payload: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "title": payload["title"],
        "description": payload["description"],
    }
    if payload.get("labels"):
        request["labels"] = ",".join(payload["labels"])
    if payload.get("start_date"):
        request["start_date_is_fixed"] = True
        request["start_date_fixed"] = payload["start_date"]
    if payload.get("due_date"):
        request["due_date_is_fixed"] = True
        request["due_date_fixed"] = payload["due_date"]
    if payload.get("parent_epic_id") is not None:
        request["parent_id"] = payload["parent_epic_id"]
    return request


def _source_artifact(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {"type": "manual", "id": None, "title": None, "description": None, "labels": []}
    source = _dict_value(artifact, "source")
    project = _dict_value(artifact, "project")
    evidence = _dict_value(artifact, "evidence")
    title = project.get("title") or artifact.get("title")
    description = (
        project.get("summary")
        or artifact.get("description")
        or artifact.get("summary")
        or evidence.get("rationale")
    )
    return {
        "type": source.get("type") or artifact.get("kind") or "artifact",
        "id": source.get("design_brief_id") or source.get("idea_id") or artifact.get("id"),
        "title": title,
        "description": description,
        "labels": _artifact_labels(artifact),
    }


def _artifact_labels(artifact: dict[str, Any]) -> list[str]:
    source = _dict_value(artifact, "source")
    labels = artifact.get("labels") if isinstance(artifact.get("labels"), list) else []
    return _labels(
        [
            *labels,
            source.get("status"),
            source.get("domain"),
            source.get("category"),
        ]
    )


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _labels(values: list[object]) -> list[str]:
    labels: list[str] = []
    for value in values:
        text = _optional_text(value)
        if text and text not in labels:
            labels.append(text)
    return labels


def _merge_labels(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for label in group:
            if label and label not in merged:
                merged.append(label)
    return merged


def _env_labels(name: str) -> list[str]:
    value = os.getenv(name)
    if not value:
        return []
    return [label.strip() for label in value.split(",") if label.strip()]


def _required_text(value: object, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise GitLabEpicPublishError(message)
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _required_url(value: object) -> str:
    raw = _required_text(value, "GitLab base_url is required").rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise GitLabEpicPublishError("GitLab base_url must be an absolute http(s) URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _optional_date(value: str | date | None, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = _optional_text(value)
    if text is None:
        return None
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise GitLabEpicPublishError(f"{field_name} must use YYYY-MM-DD format") from exc
    return text


def _optional_positive_int(value: object, message: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise GitLabEpicPublishError(message) from exc
    if parsed < 1:
        raise GitLabEpicPublishError(message)
    return parsed


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise GitLabEpicPublishError(
            "GitLab epic publish failed: response was not valid JSON",
            status_code=response.status_code,
        ) from exc
    return body if isinstance(body, dict) else {}
