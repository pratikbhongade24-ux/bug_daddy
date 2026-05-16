from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import boto3


DEFAULT_BEDROCK_MODEL_ID = "openai.gpt-oss-120b-1:0"


def _json_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must contain valid JSON.") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a JSON array of strings.")
    return value


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class MCPServerConfig:
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    tool_allowlist: list[str] = field(default_factory=list)

    @property
    def enabled(self) -> bool:
        if self.transport == "stdio":
            return bool(self.command)
        return bool(self.url)


@dataclass(slots=True)
class PeerAgentConfig:
    name: str
    url: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.url)


@dataclass(slots=True)
class AppConfig:
    aws_region: str = "us-west-2"
    bedrock_model_id: str = DEFAULT_BEDROCK_MODEL_ID
    dry_run: bool = False
    peer_timeout_seconds: float = 20.0
    slack: MCPServerConfig = field(default_factory=lambda: MCPServerConfig(name="slack"))
    jira: MCPServerConfig = field(default_factory=lambda: MCPServerConfig(name="jira"))
    bitbucket: MCPServerConfig = field(default_factory=lambda: MCPServerConfig(name="bitbucket"))
    github: MCPServerConfig = field(default_factory=lambda: MCPServerConfig(name="github"))
    bug_daddy: PeerAgentConfig = field(default_factory=lambda: PeerAgentConfig(name="bug_daddy"))
    incident_daddy: PeerAgentConfig = field(default_factory=lambda: PeerAgentConfig(name="incident_daddy"))
    reviewer_daddy: PeerAgentConfig = field(default_factory=lambda: PeerAgentConfig(name="reviewer_daddy"))
    sme_agent: PeerAgentConfig = field(default_factory=lambda: PeerAgentConfig(name="sme_agent"))

    @classmethod
    def from_env(cls) -> "AppConfig":
        resolved_region = (
            os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or _region_from_boto3_session()
            or "us-west-2"
        )
        return cls(
            aws_region=resolved_region,
            bedrock_model_id=os.getenv(
                "BEDROCK_MODEL_ID",
                DEFAULT_BEDROCK_MODEL_ID,
            ),
            dry_run=_bool("DRY_RUN", False),
            peer_timeout_seconds=_float("PEER_TIMEOUT_SECONDS", 20.0),
            slack=_mcp_config_from_env("SLACK_MCP", "slack"),
            jira=_mcp_config_from_env("JIRA_MCP", "jira"),
            bitbucket=_mcp_config_from_env("BITBUCKET_MCP", "bitbucket"),
            github=_mcp_config_from_env("GITHUB_MCP", "github"),
            bug_daddy=_peer_config_from_env("BUG_DADDY", "bug_daddy"),
            incident_daddy=_peer_config_from_env("INCIDENT_DADDY", "incident_daddy"),
            reviewer_daddy=_peer_config_from_env("REVIEWER_DADDY", "reviewer_daddy"),
            sme_agent=_peer_config_from_env("SME_AGENT", "sme_agent"),
        )


def _mcp_config_from_env(prefix: str, name: str) -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        transport=os.getenv(f"{prefix}_TRANSPORT", "stdio"),
        command=os.getenv(f"{prefix}_COMMAND"),
        args=_json_list(f"{prefix}_ARGS", []),
        url=os.getenv(f"{prefix}_URL"),
        tool_allowlist=_json_list(f"{prefix}_TOOL_ALLOWLIST", []),
    )


def _peer_config_from_env(prefix: str, name: str) -> PeerAgentConfig:
    return PeerAgentConfig(
        name=name,
        url=os.getenv(f"{prefix}_URL"),
    )


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


def _region_from_boto3_session() -> str | None:
    session = boto3.session.Session()
    return session.region_name
