"""
Specialized remediation agents.

Each agent is a self-contained, async, side-effect-bounded unit. Agents
declare a capability manifest (`AgentCapability`) and implement a uniform
`async def execute(step, event, ctx) -> AgentOutcome` entrypoint.

Agents are registered into the global `AgentRegistry` via the
`@register_agent` decorator, which is what makes the runtime "plugin
shaped" — adding a new incident class is a matter of dropping a new file
into this folder and importing it from `bootstrap.py`.
"""

from .base import BaseRemediationAgent, ExecutionContext, register_agent
from .bootstrap import bootstrap_default_agents

__all__ = [
    "BaseRemediationAgent",
    "ExecutionContext",
    "bootstrap_default_agents",
    "register_agent",
]
