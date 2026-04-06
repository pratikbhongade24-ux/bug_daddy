from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AgentRuntime, ConnectorHealth


def seed_platform(db: Session) -> None:
    settings = get_settings()
    _seed_agents(db, settings)
    db.flush()
    _seed_connectors(db)
    db.commit()


def _seed_agents(db: Session, settings) -> None:
    runtimes = {
        "incident_daddy": settings.incident_daddy_runtime_arn,
        "bug_daddy": settings.bug_daddy_runtime_arn,
        "reviewer_daddy": settings.reviewer_daddy_runtime_arn,
        "sme_agent": settings.sme_agent_runtime_arn,
    }
    for name, arn in runtimes.items():
        runtime = db.query(AgentRuntime).filter(AgentRuntime.name == name).one_or_none()
        if runtime is None:
            runtime = AgentRuntime(name=name)
            db.add(runtime)
        runtime.runtime_arn = arn or None
        runtime.runtime_id = arn.rsplit("/", 1)[-1] if arn else None
        runtime.status = "ready" if arn else "configured"


def _seed_connectors(db: Session) -> None:
    settings = get_settings()
    defaults = {
        "agentcore": ("ready", "AgentCore runtimes reachable through AWS credentials."),
        "slack": ("configured", "Slack MCP can be attached when credentials are ready."),
        "jira": ("configured", "Jira MCP can be attached when credentials are ready."),
        "bitbucket": ("configured", "Bitbucket MCP can be attached when credentials are ready."),
        "mysql": (
            "ready" if settings.using_mysql else "development",
            "Primary issue store is online." if settings.using_mysql else "SQLite fallback in use for local development.",
        ),
    }
    for name, values in defaults.items():
        connector = db.query(ConnectorHealth).filter(ConnectorHealth.name == name).one_or_none()
        if connector is None:
            connector = ConnectorHealth(name=name)
            db.add(connector)
        connector.status, connector.detail = values
