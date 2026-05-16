from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from mcp import StdioServerParameters, stdio_client
from strands.tools.mcp import MCPClient

from agentic_solution.config import AppConfig, MCPServerConfig
from agentic_solution.github_tools import (
    get_native_github_read_write_tools,
    get_native_github_pr_tools,
    native_github_diagnostics
)
from agentic_solution.jira_tools import get_native_jira_tools, native_jira_diagnostics

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MCPToolBundle:
    slack_tools: list[Any]
    jira_tools: list[Any]
    bitbucket_tools: list[Any]
    github_read_write_tools: list[Any]
    github_pr_tools: list[Any]
    diagnostics: dict[str, Any]

    @property
    def github_tools(self) -> list[Any]:
        return self.github_read_write_tools + self.github_pr_tools


def load_mcp_tools(config: AppConfig) -> MCPToolBundle:
    diagnostics: dict[str, Any] = {}

    slack_tools = _load_tools_for_server(config.slack, diagnostics)
    jira_tools = _load_tools_for_server(config.jira, diagnostics)
    native_jira_tools = get_native_jira_tools()
    diagnostics["jira_native"] = native_jira_diagnostics()
    jira_tools = jira_tools + native_jira_tools
    bitbucket_tools = _load_tools_for_server(config.bitbucket, diagnostics)
    
    github_mcp_tools = _load_tools_for_server(config.github, diagnostics)
    native_github_rw = get_native_github_read_write_tools()
    native_github_pr = get_native_github_pr_tools()
    diagnostics["github_native"] = native_github_diagnostics()

    return MCPToolBundle(
        slack_tools=slack_tools,
        jira_tools=jira_tools,
        bitbucket_tools=bitbucket_tools,
        github_read_write_tools=github_mcp_tools + native_github_rw,
        github_pr_tools=native_github_pr,
        diagnostics=diagnostics,
    )


def _load_tools_for_server(server: MCPServerConfig, diagnostics: dict[str, Any]) -> list[Any]:
    if not server.enabled:
        diagnostics[server.name] = {"status": "disabled"}
        return []

    try:
        client = _client_for(server)
        with client:
            tools = client.list_tools_sync()
        filtered = _filter_tools(server, tools)
        diagnostics[server.name] = {
            "status": "loaded",
            "tool_count": len(filtered),
        }
        return filtered
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load MCP tools for %s", server.name)
        diagnostics[server.name] = {
            "status": "error",
            "error": str(exc),
        }
        return []


def _client_for(server: MCPServerConfig) -> MCPClient:
    if server.transport != "stdio":
        raise ValueError(
            f"Unsupported MCP transport '{server.transport}' for {server.name}. "
            "This scaffold currently supports stdio MCP servers."
        )
    if not server.command:
        raise ValueError(f"Missing command for {server.name} MCP server.")

    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=server.command,
                args=server.args,
            )
        )
    )


def _filter_tools(server: MCPServerConfig, tools: list[Any]) -> list[Any]:
    if not server.tool_allowlist:
        return tools

    allowed = set(server.tool_allowlist)
    filtered = []
    for tool in tools:
        tool_name = getattr(tool, "tool_name", None) or getattr(tool, "name", None)
        if tool_name in allowed:
            filtered.append(tool)
    return filtered
