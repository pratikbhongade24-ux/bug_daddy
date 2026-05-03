from __future__ import annotations

import base64
import os
from typing import Any

import requests
from strands.tools import tool


def _github_token() -> str:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set.")
    return token


def _github_headers() -> dict[str, str]:
    return {
        "Authorization": f"token {_github_token()}",
        "Accept": "application/vnd.github.v3+json",
    }


def _request(method: str, path: str, json: Any = None) -> Any:
    url = f"https://api.github.com{path}"
    response = requests.request(method, url, headers=_github_headers(), json=json, timeout=15)
    response.raise_for_status()
    if response.status_code == 204:
        return None
    return response.json()


@tool
def github_list_files(repo_owner: str, repo_name: str, path: str = "", branch: str = "master") -> list[str]:
    """List files in a GitHub repository path."""
    contents = _request("GET", f"/repos/{repo_owner}/{repo_name}/contents/{path}?ref={branch}")
    return [item["path"] for item in contents]


@tool
def github_get_file_content(repo_owner: str, repo_name: str, path: str, branch: str = "master") -> str:
    """Read the content of a file from GitHub."""
    content = _request("GET", f"/repos/{repo_owner}/{repo_name}/contents/{path}?ref={branch}")
    return base64.b64decode(content["content"]).decode("utf-8")


@tool
def github_create_branch(repo_owner: str, repo_name: str, branch_name: str, base_branch: str = "master") -> str:
    """Create a new branch in a GitHub repository."""
    # Get base branch SHA
    base = _request("GET", f"/repos/{repo_owner}/{repo_name}/git/ref/heads/{base_branch}")
    sha = base["object"]["sha"]
    
    # Create new ref
    _request("POST", f"/repos/{repo_owner}/{repo_name}/git/refs", {
        "ref": f"refs/heads/{branch_name}",
        "sha": sha
    })
    return f"Branch {branch_name} created from {base_branch}."


@tool
def github_update_file(
    repo_owner: str, 
    repo_name: str, 
    path: str, 
    content: str, 
    message: str, 
    branch: str,
    sha: str | None = None
) -> str:
    """Create or update a file in a GitHub repository."""
    if not sha:
        # Get existing file SHA if any
        try:
            existing = _request("GET", f"/repos/{repo_owner}/{repo_name}/contents/{path}?ref={branch}")
            sha = existing["sha"]
        except Exception:
            sha = None

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    _request("PUT", f"/repos/{repo_owner}/{repo_name}/contents/{path}", payload)
    return f"File {path} updated in branch {branch}."


@tool
def github_create_pull_request(
    repo_owner: str, 
    repo_name: str, 
    title: str, 
    body: str, 
    head: str, 
    base: str = "master"
) -> dict[str, Any]:
    """Create a pull request on GitHub."""
    return _request("POST", f"/repos/{repo_owner}/{repo_name}/pulls", {
        "title": title,
        "body": body,
        "head": head,
        "base": base
    })


def get_native_github_tools() -> list[Any]:
    """Return the list of native GitHub tools."""
    return [
        github_list_files,
        github_get_file_content,
        github_create_branch,
        github_update_file,
        github_create_pull_request,
    ]


def native_github_diagnostics() -> dict[str, Any]:
    """Return diagnostics for the native GitHub tools."""
    token = os.getenv("GITHUB_TOKEN")
    return {
        "status": "available" if token else "missing_token",
        "has_token": bool(token),
    }
