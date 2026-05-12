"""GitLab merge request approvals import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITLAB_API = "https://gitlab.com/api/v4"


class GitLabMergeRequestApprovalsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or os.getenv("GITLAB_PRIVATE_TOKEN")
                or os.getenv("GITLAB_TOKEN")
            )
        )
        self.api_url = (
            api_url
            or _optional(self._config.get("api_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_merge_request_approvals_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def merge_requests(self) -> list[dict[str, str]]:
        configured = self._config.get("merge_requests")
        if configured is not None:
            return _configured_merge_requests(configured)

        project_ids = _strings(
            self._config.get("project_ids")
            or self._config.get("projects")
            or self._config.get("project_id")
        )
        iids = _strings(
            self._config.get("merge_request_iids")
            or self._config.get("merge_requests_iids")
            or self._config.get("iids")
            or self._config.get("iid")
        )
        return [{"project_id": project_id, "iid": iid} for project_id in project_ids for iid in iids]

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.merge_requests:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for merge_request in self.merge_requests:
                if len(signals) >= limit:
                    break
                approval = await self._fetch_approval(client, merge_request)
                if not isinstance(approval, dict) or not approval:
                    continue
                signals.append(_approval_signal(approval, merge_request, self.name))
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_approval(
        self,
        client: httpx.AsyncClient,
        merge_request: dict[str, str],
    ) -> dict[str, Any]:
        project_id = merge_request["project_id"]
        iid = merge_request["iid"]
        url = (
            f"{self.api_url}/projects/{quote(project_id, safe='')}"
            f"/merge_requests/{quote(iid, safe='')}/approvals"
        )
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-merge-request-approvals-import/1",
                },
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning(
                "GitLab merge request approvals fetch failed for %s !%s",
                project_id,
                iid,
                exc_info=True,
            )
            return {}
        return body if isinstance(body, dict) else {}


GitLabMergeRequestApprovalAdapter = GitLabMergeRequestApprovalsAdapter


def _approval_signal(
    approval: dict[str, Any],
    configured: dict[str, str],
    adapter_name: str,
) -> Signal:
    project_id = _text(approval.get("project_id")) or configured["project_id"]
    iid = _text(approval.get("iid")) or configured["iid"]
    title = _text(approval.get("title")) or _text(configured.get("title")) or f"Merge request !{iid}"
    approved = bool(approval.get("approved"))
    state = "approved" if approved else "unapproved"
    approvals_required = _int(approval.get("approvals_required"))
    approvals_left = _int(approval.get("approvals_left"))
    approvers = _approvers(approval.get("approved_by"))
    author = _author(approval, approvers)
    url = _text(approval.get("web_url") or configured.get("url"))

    return Signal(
        id=f"gitlab-mr-approval:{project_id}:{iid}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_id} !{iid} {state}: {title}",
        content=_content(
            title=title,
            state=state,
            approvals_required=approvals_required,
            approvals_left=approvals_left,
            approvers=approvers,
        ),
        url=url,
        author=author,
        published_at=_parse_dt(approval.get("updated_at") or approval.get("created_at")),
        tags=sorted({"gitlab", "merge-request", "approval", state} - {""})[:10],
        credibility=0.7,
        metadata={
            "project_id": project_id,
            "merge_request_iid": iid,
            "merge_request_id": approval.get("id"),
            "title": title,
            "url": url,
            "approved": approved,
            "state": state,
            "approvals_required": approvals_required,
            "approvals_left": approvals_left,
            "approved_by": approvers,
            "approver_usernames": [approver["username"] for approver in approvers if approver.get("username")],
            "user_has_approved": approval.get("user_has_approved"),
            "user_can_approve": approval.get("user_can_approve"),
            "approval_rules_overwritten": approval.get("approval_rules_overwritten"),
            "created_at": approval.get("created_at"),
            "updated_at": approval.get("updated_at"),
            "raw": approval,
        },
    )


def _content(
    *,
    title: str,
    state: str,
    approvals_required: int,
    approvals_left: int,
    approvers: list[dict[str, Any]],
) -> str:
    parts = [f"GitLab merge request approval state is {state} for {title}."]
    if approvals_required:
        parts.append(f"{approvals_required} approvals required.")
    if approvals_left:
        parts.append(f"{approvals_left} approvals remaining.")
    if approvers:
        names = ", ".join(
            _text(approver.get("username") or approver.get("name")) for approver in approvers
        )
        if names:
            parts.append(f"Approved by {names}.")
    return " ".join(parts)


def _author(approval: dict[str, Any], approvers: list[dict[str, Any]]) -> str | None:
    if approvers:
        return _optional(approvers[0].get("username") or approvers[0].get("name"))
    author = approval.get("author")
    if isinstance(author, dict):
        return _optional(author.get("username") or author.get("name"))
    return None


def _approvers(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    approvers: list[dict[str, Any]] = []
    for item in value:
        user = item.get("user") if isinstance(item, dict) else None
        if not isinstance(user, dict):
            continue
        approvers.append(
            {
                "id": user.get("id"),
                "username": _text(user.get("username")),
                "name": _text(user.get("name")),
                "web_url": user.get("web_url"),
                "avatar_url": user.get("avatar_url"),
            }
        )
    return approvers


def _configured_merge_requests(value: object) -> list[dict[str, str]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []

    merge_requests: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        project_id = _optional(item.get("project_id") or item.get("project"))
        iid = _optional(item.get("iid") or item.get("merge_request_iid"))
        if not project_id or not iid:
            continue
        merge_request = {"project_id": project_id, "iid": iid}
        for key in ("title", "url"):
            text = _optional(item.get(key))
            if text:
                merge_request[key] = text
        merge_requests.append(merge_request)
    return merge_requests


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
