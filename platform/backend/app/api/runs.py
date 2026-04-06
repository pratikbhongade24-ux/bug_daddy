from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Run

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {
        "id": run.id,
        "run_key": run.run_key,
        "status": run.status,
        "current_agent": run.current_agent,
        "started_at": run.started_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "outcome": run.outcome,
        "duration_seconds": run.duration_seconds,
        "events": [
            {
                "id": event.id,
                "sequence": event.sequence,
                "event_type": event.event_type,
                "node_name": event.node_name,
                "title": event.title,
                "detail": event.detail,
                "status": event.status,
                "metadata_json": event.metadata_json,
                "created_at": event.created_at.isoformat(),
            }
            for event in run.events
        ],
    }
