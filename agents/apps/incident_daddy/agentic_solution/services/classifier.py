from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from strands import Agent
from agentic_solution.agents import build_classifier_agent
from agentic_solution.config import AppConfig
from agentic_solution.mcp import MCPToolBundle, load_mcp_tools
from agentic_solution.peer import PeerRuntimeClient

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class ClassifierRuntime:
    config: AppConfig
    tools: MCPToolBundle
    peers: PeerRuntimeClient

    def _build_agent(self) -> Agent:
        return build_classifier_agent(self.config, tools={"jira": self.tools.jira_tools})

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent = self._build_agent()
        
        # Prepare the triage prompt with issue data
        triage_input = f"Issue Data:\n{payload}"
        
        logger.info("Classifying incoming issue...")
        result = str(agent(triage_input))
        logger.info("Classification result: %s", result)

        # Basic parsing of the agent's routing decision
        if "[ROUTE: BUG]" in result:
            # Extract Jira Key if present
            jira_key = self._extract_tag(result, "JIRA_KEY")
            payload["resolution_jira"] = jira_key
            logger.info("Routing to Bug Daddy with Jira Key: %s", jira_key)
            return self.peers.invoke(self.config.bug_daddy, payload)
        
        if "[ROUTE: INCIDENT]" in result:
            logger.info("Routing to Incident Daddy")
            return self.peers.invoke(self.config.incident_daddy, payload)

        if "[STATUS: DUPLICATE]" in result:
            jira_key = self._extract_tag(result, "JIRA_KEY")
            return {
                "status": "duplicate",
                "jira_key": jira_key,
                "summary": f"Issue is a duplicate of {jira_key}. No new pipeline started."
            }

        # Fallback to Incident if unsure
        return self.peers.invoke(self.config.incident_daddy, payload)

    def _extract_tag(self, text: str, tag: str) -> str | None:
        import re
        match = re.search(rf"\[{tag}: (.*?)\]", text)
        return match.group(1) if match else None


def build_runtime(config: AppConfig | None = None) -> ClassifierRuntime:
    cfg = config or AppConfig.from_env()
    tools = load_mcp_tools(cfg)
    return ClassifierRuntime(
        config=cfg,
        tools=tools,
        peers=PeerRuntimeClient(cfg),
    )
