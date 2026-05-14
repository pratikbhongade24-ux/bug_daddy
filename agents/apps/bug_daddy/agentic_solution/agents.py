from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strands import Agent
from strands.models import BedrockModel

from agentic_solution.config import AppConfig
from agentic_solution.prompts import (
    STRATEGY_PLANNER_PROMPT,
    CONTEXT_ANALYZER_PROMPT,
    CODER_PROMPT,
    CRITIC_PROMPT,
    INCIDENT_ANALYSER_PROMPT,
    INCIDENT_ORCHESTRATOR_PROMPT,
    REVIEWER_PROMPT,
    SME_AGENT_PROMPT,
    CLASSIFIER_PROMPT,
)


@dataclass(slots=True)
class IncidentAgentBundle:
    analyzer: Agent
    orchestrator: Agent


@dataclass(slots=True)
class BugAgentBundle:
    strategy_planner: Agent
    context_analyzer: Agent
    coder: Agent
    critic: Agent


@dataclass(slots=True)
class ReviewerAgentBundle:
    reviewer: Agent


@dataclass(slots=True)
class SMEAgentBundle:
    expert: Agent


def build_incident_agents(config: AppConfig, tools: dict[str, list[Any]]) -> IncidentAgentBundle:
    model = _build_model(config)
    return IncidentAgentBundle(
        analyzer=Agent(model=model, system_prompt=INCIDENT_ANALYSER_PROMPT, tools=[]),
        orchestrator=Agent(
            model=model,
            system_prompt=INCIDENT_ORCHESTRATOR_PROMPT,
            tools=tools["slack"] + tools["jira"],
        ),
    )


def build_bug_agents(config: AppConfig, tools: dict[str, list[Any]]) -> BugAgentBundle:
    model = _build_model(config)
    repo_read_write = tools["bitbucket"] + tools.get("github_read_write", [])
    all_repo_tools = tools["bitbucket"] + tools.get("github", [])
    return BugAgentBundle(
        strategy_planner=Agent(
            model=model,
            system_prompt=STRATEGY_PLANNER_PROMPT,
            tools=tools["jira"] + all_repo_tools,
        ),
        context_analyzer=Agent(
            model=model,
            system_prompt=CONTEXT_ANALYZER_PROMPT,
            tools=tools["jira"] + all_repo_tools,
        ),
        coder=Agent(model=model, system_prompt=CODER_PROMPT, tools=repo_read_write),
        critic=Agent(model=model, system_prompt=CRITIC_PROMPT, tools=[]),
    )


def build_reviewer_agents(config: AppConfig, tools: dict[str, list[Any]]) -> ReviewerAgentBundle:
    model = _build_model(config)
    all_repo_tools = tools["bitbucket"] + tools.get("github", [])
    return ReviewerAgentBundle(
        reviewer=Agent(
            model=model,
            system_prompt=REVIEWER_PROMPT,
            tools=tools["jira"] + all_repo_tools,
        )
    )


def build_classifier_agent(config: AppConfig, tools: dict[str, list[Any]]) -> Agent:
    model = _build_model(config)
    return Agent(
        model=model,
        system_prompt=CLASSIFIER_PROMPT,
        tools=tools["jira"],
    )


def build_sme_agents(config: AppConfig) -> SMEAgentBundle:
    model = _build_model(config)
    return SMEAgentBundle(
        expert=Agent(model=model, system_prompt=SME_AGENT_PROMPT, tools=[]),
    )


def _build_model(config: AppConfig) -> BedrockModel:
    return BedrockModel(
        model_id=config.bedrock_model_id,
        region_name=config.aws_region,
        temperature=0.1,
    )
