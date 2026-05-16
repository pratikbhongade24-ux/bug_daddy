"""
Shared pytest fixtures.

Two responsibilities:

1. **Environment hygiene** — every test runs against a clean env so that
   credentials leaked into the developer shell cannot mask a missing config
   bug. Tests that need a value set it themselves via ``monkeypatch.setenv``.

2. **MCP / network isolation** — fakes for the external surface (Slack, Jira,
   Bitbucket, peer runtimes) so unit tests never touch the network.
"""

from __future__ import annotations

import pytest

_ENV_KEYS_TO_SCRUB = (
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "BEDROCK_MODEL_ID",
    "DRY_RUN",
    "PEER_TIMEOUT_SECONDS",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "JIRA_BASE_URL",
    "JIRA_PROJECT_KEY",
    "SLACK_BOT_TOKEN",
    "SLACK_MCP_COMMAND",
    "SLACK_MCP_ARGS",
    "SLACK_MCP_TOOL_ALLOWLIST",
    "BUG_DADDY_URL",
    "REVIEWER_DADDY_URL",
    "SME_AGENT_URL",
    "SME_RAG_URL",
    "SME_RAG_API_KEY",
    "SME_RAG_TIMEOUT_SECONDS",
    "SME_RAG_FETCH_CITATIONS",
    "AGENT_EXECUTION_LOG_SECRET",
    "AGENT_EXECUTION_CALLBACK_URL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove every orchestrator-relevant env var before each test.

    Marked autouse so we never depend on shell state leaking through. Tests
    that need a value re-add it explicitly via monkeypatch — the resulting
    test is then a complete specification of its required environment."""
    for key in _ENV_KEYS_TO_SCRUB:
        monkeypatch.delenv(key, raising=False)
    return


@pytest.fixture
def silent_logger():
    """Structured logger that captures records in-memory instead of printing.

    Use whenever a unit test exercises a component that logs but doesn't
    need to assert on the log output — keeps test runs quiet."""
    import logging

    from agentic_solution.orchestrator.observability.logging import StructuredLogger

    class _CapturingHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records: list[str] = []

        def emit(self, record):  # noqa: D401
            self.records.append(self.format(record))

    handler = _CapturingHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    base = StructuredLogger()
    base._stdlib.handlers = [handler]
    base._stdlib.propagate = False
    return base
