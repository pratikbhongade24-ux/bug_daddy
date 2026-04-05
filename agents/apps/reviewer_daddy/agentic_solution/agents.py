from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strands import Agent
from strands.models import BedrockModel

from agentic_solution.config import AppConfig
from agentic_solution.prompts import (
    BUG_ORCHESTRATOR_PROMPT,
    CODER_PROMPT,
    CRITIC_PROMPT,
    GATHERER_PROMPT,
    INCIDENT_ANALYSER_PROMPT,
    INCIDENT_ORCHESTRATOR_PROMPT,
    LOG_ANALYSER_PROMPT,
    PLANNER_PROMPT,
    REVIEWER_PROMPT,
    SME_AGENT_PROMPT,
)


@dataclass(slots=True)
class IncidentAgentBundle:
    analyzer: Agent
    orchestrator: Agent


@dataclass(slots=True)
class BugAgentBundle:
    orchestrator: Agent
    planner: Agent
    gatherer: Agent
    log_analyser: Agent
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
    return BugAgentBundle(
        orchestrator=Agent(
            model=model,
            system_prompt=BUG_ORCHESTRATOR_PROMPT,
            tools=tools["jira"] + tools["bitbucket"],
        ),
        planner=Agent(model=model, system_prompt=PLANNER_PROMPT, tools=[]),
        gatherer=Agent(
            model=model,
            system_prompt=GATHERER_PROMPT,
            tools=tools["jira"] + tools["bitbucket"],
        ),
        log_analyser=Agent(model=model, system_prompt=LOG_ANALYSER_PROMPT, tools=[]),
        coder=Agent(model=model, system_prompt=CODER_PROMPT, tools=tools["bitbucket"]),
        critic=Agent(model=model, system_prompt=CRITIC_PROMPT, tools=[]),
    )


def build_reviewer_agents(config: AppConfig, tools: dict[str, list[Any]]) -> ReviewerAgentBundle:
    model = _build_model(config)
    return ReviewerAgentBundle(
        reviewer=Agent(
            model=model,
            system_prompt=REVIEWER_PROMPT,
            tools=tools["jira"] + tools["bitbucket"],
        )
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
