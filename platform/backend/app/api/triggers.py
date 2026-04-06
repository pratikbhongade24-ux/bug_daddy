from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TriggerEvent
from app.schemas import ScenarioLaunchRequest, TriggerIngestRequest
from app.services.catalog import list_scenarios
from app.services.orchestration import create_issue_and_run, launch_scenario, process_run

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


@router.get("")
def list_trigger_events(db: Session = Depends(get_db)):
    items = db.query(TriggerEvent).order_by(desc(TriggerEvent.created_at)).limit(100).all()
    return [
        {
            "id": item.id,
            "source": item.source,
            "trigger_name": item.trigger_name,
            "service_name": item.service_name,
            "payload_json": item.payload_json,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


@router.get("/scenarios")
def get_scenarios():
    return list_scenarios()


@router.post("/ingest")
def ingest_trigger(request: TriggerIngestRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    issue, run = create_issue_and_run(db, request)
    background_tasks.add_task(process_run, issue.id, run.id)
    return {"issue_id": issue.id, "run_id": run.id, "status": "queued"}


@router.post("/simulate")
def simulate_trigger(request: ScenarioLaunchRequest, background_tasks: BackgroundTasks):
    issue, run = launch_scenario(request.scenario_id)
    background_tasks.add_task(process_run, issue.id, run.id)
    return {"issue_id": issue.id, "run_id": run.id, "status": "queued"}
