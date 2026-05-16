from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ExecutionLogger:
    session_id: str | None
    endpoint: str | None
    secret: str | None
    component: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any], component: str) -> ExecutionLogger:
        endpoint = (
            payload.get("execution_log_endpoint")
            or os.getenv("AGENT_EXECUTION_CALLBACK_URL")
            or os.getenv("PLATFORM_API_BASE_URL")
        )
        secret = payload.get("execution_log_secret") or os.getenv("AGENT_EXECUTION_LOG_SECRET")
        return cls(
            session_id=_session_id_from_payload(payload),
            endpoint=str(endpoint).rstrip("/") if endpoint else None,
            secret=str(secret) if secret else None,
            component=component,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.session_id and self.endpoint)

    def emit(self, event_type: str, **payload: Any) -> None:
        if not self.enabled:
            return
        body = {
            "event_type": event_type,
            "agent_name": payload.pop("agent_name", self.component),
            **{key: value for key, value in payload.items() if value is not None},
        }
        request = urllib.request.Request(
            f"{self.endpoint}/agent/executions/{self.session_id}/events",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                **({"X-Agent-Execution-Secret": self.secret} if self.secret else {}),
            },
        )
        try:
            urllib.request.urlopen(request, timeout=float(os.getenv("AGENT_EXECUTION_LOG_TIMEOUT", "3"))).read()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            # Execution logging must never break the agent's primary remediation path.
            return

    def map_jira_resolution(self, resolution_jira: str) -> None:
        self._post_resolution("jira", {"resolution_jira": resolution_jira})

    def map_pull_request_resolution(self, resolution_pr: str) -> None:
        self._post_resolution("pr", {"resolution_pr": resolution_pr})

    def _post_resolution(self, resolution_type: str, body: dict[str, Any]) -> None:
        if not self.enabled:
            return
        request = urllib.request.Request(
            f"{self.endpoint}/agent/executions/{self.session_id}/resolution/{resolution_type}",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                **({"X-Agent-Execution-Secret": self.secret} if self.secret else {}),
            },
        )
        try:
            urllib.request.urlopen(request, timeout=float(os.getenv("AGENT_EXECUTION_LOG_TIMEOUT", "3"))).read()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return

    def node_started(
        self,
        node_id: str,
        node_name: str,
        title: str,
        input_summary: str | None = None,
    ) -> float:
        self.emit(
            "node.started",
            node_id=node_id,
            node_name=node_name,
            status="running",
            level="info",
            title=title,
            input_summary=_truncate(input_summary),
        )
        return time.monotonic()

    def node_completed(
        self,
        node_id: str,
        node_name: str,
        title: str,
        started_at: float,
        output_summary: str | None = None,
        result: Any = None,
    ) -> None:
        self.emit(
            "node.completed",
            node_id=node_id,
            node_name=node_name,
            status="succeeded",
            level="info",
            title=title,
            output_summary=_truncate(output_summary),
            result=_json_safe(result),
            duration_ms=int((time.monotonic() - started_at) * 1000),
        )

    def node_failed(
        self,
        node_id: str,
        node_name: str,
        title: str,
        started_at: float,
        error: Exception,
    ) -> None:
        self.emit(
            "node.failed",
            node_id=node_id,
            node_name=node_name,
            status="failed",
            level="error",
            title=title,
            error_message=str(error),
            duration_ms=int((time.monotonic() - started_at) * 1000),
        )


def _session_id_from_payload(payload: dict[str, Any]) -> str | None:
    direct = payload.get("session_id") or payload.get("execution_session_id")
    if isinstance(direct, str) and direct:
        return direct

    candidates = [
        payload.get("metadata"),
        payload.get("context", {}).get("metadata") if isinstance(payload.get("context"), dict) else None,
        payload.get("issue", {}).get("metadata") if isinstance(payload.get("issue"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            value = candidate.get("execution_session_id") or candidate.get("session_id")
            if isinstance(value, str) and value:
                return value
    return None


def _truncate(value: str | None, limit: int = 4000) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
