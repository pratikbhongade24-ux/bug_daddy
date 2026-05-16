from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from strands import tool


def native_jira_tools_enabled() -> bool:
    return bool(_base_url() and _email() and _api_token())


def native_jira_diagnostics() -> dict[str, Any]:
    configured = native_jira_tools_enabled()
    return {
        "status": "loaded" if configured else "disabled",
        "tool_count": len(get_native_jira_tools()) if configured else 0,
        "base_url": _base_url(),
        "project_key": _project_key(),
        "missing": _missing_config(),
    }


def get_native_jira_tools() -> list[Any]:
    if not native_jira_tools_enabled():
        return []
    return [
        jira_create_issue,
        jira_assign_issue,
        jira_update_issue,
        jira_add_comment,
        jira_assign_to_reviewer,
    ]


@tool
def jira_create_issue(
    summary: str,
    description: str,
    issue_type: str = "Task",
    project_key: str | None = None,
    assignee_account_id: str | None = None,
    priority: str | None = None,
    labels: list[str] | None = None,
    sprint_id: int | None = 36,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a Jira issue in the configured Atlassian project."""
    fields: dict[str, Any] = {
        "project": {"key": project_key or _project_key()},
        "summary": summary,
        "description": _adf(description),
        "issuetype": {"name": issue_type},
    }
    if sprint_id is not None:
        fields["customfield_10020"] = sprint_id
    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}
    if priority:
        fields["priority"] = {"name": priority}
    if labels:
        fields["labels"] = labels
    if extra_fields:
        fields.update(extra_fields)

    result = _request("POST", "/rest/api/3/issue", {"fields": fields})
    key = result.get("key")
    return {
        **result,
        "browse_url": f"{_base_url()}/browse/{key}" if key else None,
    }


@tool
def jira_assign_issue(
    issue_key: str,
    account_id: str | None = None,
    email: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Assign a Jira issue to a user by account id, email, or display name."""
    resolved_account_id = account_id or _find_user_account_id(email=email, display_name=display_name)
    if not resolved_account_id:
        raise ValueError("Provide account_id or a resolvable email/display_name.")

    _request(
        "PUT",
        f"/rest/api/3/issue/{urllib.parse.quote(issue_key)}/assignee",
        {"accountId": resolved_account_id},
    )
    return {
        "issue_key": issue_key,
        "assigned_account_id": resolved_account_id,
        "browse_url": f"{_base_url()}/browse/{issue_key}",
    }


@tool
def jira_update_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    issue_type: str | None = None,
    priority: str | None = None,
    labels: list[str] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Edit common Jira issue fields such as summary, description, type, priority, and labels."""
    fields: dict[str, Any] = {}
    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = _adf(description)
    if issue_type is not None:
        fields["issuetype"] = {"name": issue_type}
    if priority is not None:
        fields["priority"] = {"name": priority}
    if labels is not None:
        fields["labels"] = labels
    if extra_fields:
        fields.update(extra_fields)
    if not fields:
        return {"issue_key": issue_key, "updated": False, "reason": "No fields provided."}

    _request("PUT", f"/rest/api/3/issue/{urllib.parse.quote(issue_key)}", {"fields": fields})
    return {
        "issue_key": issue_key,
        "updated": True,
        "fields": sorted(fields.keys()),
        "browse_url": f"{_base_url()}/browse/{issue_key}",
    }


@tool
def jira_add_comment(issue_key: str, comment: str) -> dict[str, Any]:
    """Add a comment to a Jira issue."""
    result = _request(
        "POST",
        f"/rest/api/3/issue/{urllib.parse.quote(issue_key)}/comment",
        {"body": _adf(comment)},
    )
    return {
        **result,
        "issue_key": issue_key,
        "browse_url": f"{_base_url()}/browse/{issue_key}",
    }


@tool
def jira_assign_to_reviewer(
    issue_key: str,
    reviewer_account_id: str | None = None,
    reviewer_email: str | None = None,
    reviewer_display_name: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    """Assign a Jira issue to the configured reviewer and optionally add a handoff comment."""
    account_id = (
        reviewer_account_id
        or os.getenv("JIRA_REVIEWER_ACCOUNT_ID")
        or _find_user_account_id(
            email=reviewer_email or os.getenv("JIRA_REVIEWER_EMAIL"),
            display_name=reviewer_display_name or os.getenv("JIRA_REVIEWER_DISPLAY_NAME"),
        )
    )
    if not account_id:
        raise ValueError(
            "No reviewer configured. Set JIRA_REVIEWER_ACCOUNT_ID, "
            "JIRA_REVIEWER_EMAIL, or JIRA_REVIEWER_DISPLAY_NAME."
        )

    assignment = jira_assign_issue(issue_key=issue_key, account_id=account_id)
    comment_result = None
    if comment:
        comment_result = jira_add_comment(issue_key=issue_key, comment=comment)
    return {
        "issue_key": issue_key,
        "reviewer_account_id": account_id,
        "assignment": assignment,
        "comment": comment_result,
        "browse_url": f"{_base_url()}/browse/{issue_key}",
    }


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _base_url().rstrip("/") + path
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": "Basic " + _basic_auth(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_timeout_seconds()) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Jira API {method} {path} failed with {exc.code}: {detail}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _find_user_account_id(email: str | None = None, display_name: str | None = None) -> str | None:
    query = email or display_name
    if not query:
        return None
    users = _request(
        "GET",
        "/rest/api/3/user/search?query=" + urllib.parse.quote(query),
    )
    if not isinstance(users, list):
        return None
    lowered_email = email.lower() if email else None
    lowered_name = display_name.lower() if display_name else None
    for user in users:
        if lowered_email and str(user.get("emailAddress", "")).lower() == lowered_email:
            return user.get("accountId")
        if lowered_name and lowered_name in str(user.get("displayName", "")).lower():
            return user.get("accountId")
    return users[0].get("accountId") if users else None


def _adf(text: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(text, dict):
        return text
    paragraphs = []
    for line in text.splitlines() or [""]:
        paragraphs.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}] if line else [],
            }
        )
    return {"type": "doc", "version": 1, "content": paragraphs}


def _basic_auth() -> str:
    token = f"{_email()}:{_api_token()}".encode("utf-8")
    return base64.b64encode(token).decode("ascii")


def _base_url() -> str:
    return os.getenv("JIRA_BASE_URL", "https://bugdaddy.atlassian.net").rstrip("/")


def _email() -> str:
    return os.getenv("JIRA_EMAIL", "")


def _api_token() -> str:
    return os.getenv("JIRA_API_TOKEN", "")


def _project_key() -> str:
    return os.getenv("JIRA_PROJECT_KEY", "BUG")


def _timeout_seconds() -> float:
    return float(os.getenv("JIRA_TIMEOUT_SECONDS", "20"))


def _missing_config() -> list[str]:
    missing = []
    if not _base_url():
        missing.append("JIRA_BASE_URL")
    if not _email():
        missing.append("JIRA_EMAIL")
    if not _api_token():
        missing.append("JIRA_API_TOKEN")
    return missing
