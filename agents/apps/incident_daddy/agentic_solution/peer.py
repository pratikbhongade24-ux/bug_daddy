from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from agentic_solution.config import AppConfig, PeerAgentConfig


class PeerInvocationError(RuntimeError):
    """Raised when a peer AgentCore runtime cannot be reached."""


class PeerRuntimeClient:
    def __init__(self, config: AppConfig):
        self.config = config

    def invoke(self, peer: PeerAgentConfig, payload: dict[str, Any]) -> dict[str, Any]:
        if not peer.enabled:
            raise PeerInvocationError(f"Peer runtime '{peer.name}' is not configured.")

        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            peer.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.config.peer_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PeerInvocationError(
                f"Peer runtime '{peer.name}' returned HTTP {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise PeerInvocationError(
                f"Peer runtime '{peer.name}' could not be reached: {exc.reason}"
            ) from exc

        if not raw:
            return {}
        return json.loads(raw)
