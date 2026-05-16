from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from strands import Agent

from agentic_solution.agents import build_classifier_agent
from agentic_solution.config import AppConfig
from agentic_solution.execution import ExecutionLogger
from agentic_solution.jira_tools import jira_create_issue
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
        execution_logger = ExecutionLogger.from_payload(payload, "classifier")

        # Prepare the triage prompt with issue data
        triage_input = f"Issue Data:\n{payload}"

        logger.info("Classifying incoming issue...")
        result = str(agent(triage_input))
        logger.info("Classification result: %s", result)

        # Basic parsing of the agent's routing decision
        if "[ROUTE: BUG]" in result:
            jira_key = self._extract_tag(result, "JIRA_KEY")
            if not self._usable_jira_key(jira_key):
                jira_key = self._create_jira_before_bug_handoff(payload, result)

            payload["resolution_jira"] = jira_key
            metadata = dict(payload.get("metadata") or {})
            metadata["jira_key"] = jira_key
            metadata["resolution_jira"] = jira_key
            payload["metadata"] = metadata
            execution_logger.map_jira_resolution(jira_key)
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

    def _usable_jira_key(self, value: str | None) -> bool:
        if not value:
            return False
        return value.strip().lower() not in {"none", "null", "n/a", "na", ""}

    def _create_jira_before_bug_handoff(self, payload: dict[str, Any], classification: str) -> str:
        summary = self._jira_summary(payload)
        description = self._jira_description(payload, classification)
        logger.info("Classifier selected BUG without Jira key; creating Jira before Bug Daddy handoff.")
        result = jira_create_issue(
            summary=summary,
            description=description,
            issue_type="Bug",
            labels=["bug_daddy", "classifier"],
        )
        key = result.get("key") if isinstance(result, dict) else None
        if not key:
            raise RuntimeError(f"Jira issue creation did not return a key: {result}")
        return str(key)

    def _jira_summary(self, payload: dict[str, Any]) -> str:
        service = payload.get("service_name") or "unknown-service"
        prompt = str(payload.get("prompt") or payload.get("incident_summary") or "Bug Daddy issue")
        compact = " ".join(prompt.split())
        return f"[Bug Daddy] {service}: {compact[:180]}"

    def _jira_description(self, payload: dict[str, Any], classification: str) -> str:
        logs = payload.get("logs") or []
        if isinstance(logs, list):
            log_text = "\n".join(str(item) for item in logs[:5]) or "None provided"
        else:
            log_text = str(logs)
        return "\n".join(
            [
                "Bug Daddy classifier routed this issue to Bug Daddy and created this Jira before remediation.",
                "",
                f"Prompt: {payload.get('prompt') or 'None provided'}",
                f"Service: {payload.get('service_name') or 'None provided'}",
                f"Repository: {payload.get('repository') or 'None provided'}",
                f"Source: {payload.get('source') or 'None provided'}",
                "",
                "Logs:",
                log_text,
                "",
                "Classifier output:",
                classification,
            ]
        )


def build_runtime(config: AppConfig | None = None) -> ClassifierRuntime:
    cfg = config or AppConfig.from_env()
    tools = load_mcp_tools(cfg)
    return ClassifierRuntime(
        config=cfg,
        tools=tools,
        peers=PeerRuntimeClient(cfg),
    )
