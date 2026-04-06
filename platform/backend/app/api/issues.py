from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Artifact, Issue, Run, TriggerEvent
from app.schemas import ArtifactOut, IssueDetailOut, RetryRequest, RunEventOut, RunOut, TriggerOut
from app.services.metrics import build_issue_summary
from app.services.orchestration import process_run, relaunch_issue

router = APIRouter(prefix="/api/issues", tags=["issues"])


@router.get("")
def list_issues(db: Session = Depends(get_db)):
    issues = db.query(Issue).order_by(desc(Issue.updated_at)).all()
    return [build_issue_summary(issue).model_dump() for issue in issues]


@router.get("/{issue_id}")
def get_issue_detail(issue_id: int, db: Session = Depends(get_db)):
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")

    runs = db.query(Run).filter(Run.issue_id == issue_id).order_by(desc(Run.started_at)).all()
    triggers = db.query(TriggerEvent).filter(TriggerEvent.issue_id == issue_id).order_by(desc(TriggerEvent.created_at)).all()
    artifacts = db.query(Artifact).filter(Artifact.issue_id == issue_id).order_by(desc(Artifact.created_at)).all()
    latest = build_issue_summary(issue)

    detail = IssueDetailOut(
        **latest.model_dump(),
        logs=issue.logs,
        telemetry=issue.telemetry,
        kb_context=issue.kb_context,
        source_payload=issue.source_payload,
        triggers=[
            TriggerOut(
                id=item.id,
                source=item.source,
                trigger_name=item.trigger_name,
                service_name=item.service_name,
                payload_json=item.payload_json,
                status=item.status,
                created_at=item.created_at,
            )
            for item in triggers
        ],
        runs=[
            RunOut(
                id=run.id,
                run_key=run.run_key,
                status=run.status,
                current_agent=run.current_agent,
                started_at=run.started_at,
                updated_at=run.updated_at,
                ended_at=run.ended_at,
                outcome=run.outcome,
                duration_seconds=run.duration_seconds,
                events=[
                    RunEventOut(
                        id=event.id,
                        sequence=event.sequence,
                        event_type=event.event_type,
                        node_name=event.node_name,
                        title=event.title,
                        detail=event.detail,
                        status=event.status,
                        metadata_json=event.metadata_json,
                        created_at=event.created_at,
                    )
                    for event in sorted(run.events, key=lambda item: item.sequence)
                ],
            )
            for run in runs
        ],
        artifacts=[
            ArtifactOut(
                id=item.id,
                artifact_type=item.artifact_type,
                title=item.title,
                external_ref=item.external_ref,
                url=item.url,
                payload_json=item.payload_json,
                created_at=item.created_at,
            )
            for item in artifacts
        ],
    )
    return detail.model_dump()


@router.post("/{issue_id}/retry")
def retry_issue(issue_id: int, _: RetryRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if db.get(Issue, issue_id) is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    new_issue, run = relaunch_issue(issue_id)
    background_tasks.add_task(process_run, new_issue.id, run.id)
    return {"issue_id": new_issue.id, "run_id": run.id, "status": "queued"}


@router.post("/{issue_id}/replay")
def replay_issue(issue_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if db.get(Issue, issue_id) is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    new_issue, run = relaunch_issue(issue_id)
    background_tasks.add_task(process_run, new_issue.id, run.id)
    return {"issue_id": new_issue.id, "run_id": run.id, "status": "queued"}
