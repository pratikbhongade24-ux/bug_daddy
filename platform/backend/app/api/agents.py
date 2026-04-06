from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AgentRuntime, ConnectorHealth

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    items = db.query(AgentRuntime).order_by(AgentRuntime.name.asc()).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "runtime_arn": item.runtime_arn,
            "runtime_id": item.runtime_id,
            "status": item.status,
            "average_latency_ms": item.average_latency_ms,
            "success_rate": item.success_rate,
            "version": item.version,
            "last_invoked_at": item.last_invoked_at.isoformat() if item.last_invoked_at else None,
        }
        for item in items
    ]


@router.get("/health")
def get_agent_health(db: Session = Depends(get_db)):
    agents = db.query(AgentRuntime).order_by(AgentRuntime.name.asc()).all()
    connectors = db.query(ConnectorHealth).order_by(ConnectorHealth.name.asc()).all()
    return {
        "agents": [
            {
                "name": item.name,
                "status": item.status,
                "runtime_id": item.runtime_id,
                "average_latency_ms": item.average_latency_ms,
                "success_rate": item.success_rate,
            }
            for item in agents
        ],
        "connectors": [
            {
                "name": item.name,
                "status": item.status,
                "detail": item.detail,
                "checked_at": item.checked_at.isoformat(),
            }
            for item in connectors
        ],
    }
