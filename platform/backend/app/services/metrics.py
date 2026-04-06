from __future__ import annotations

from collections import Counter
from statistics import mean

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models import AgentRuntime, Artifact, ConnectorHealth, Issue, Run, RunEvent, TriggerEvent
from app.schemas import (
    AgentRuntimeOut,
    ArtifactOut,
    ConnectorHealthOut,
    DashboardSummaryOut,
    IssueOut,
    RunOut,
)


def build_issue_summary(issue: Issue) -> IssueOut:
    latest_run = sorted(issue.runs, key=lambda item: item.started_at, reverse=True)[0] if issue.runs else None
    latest_artifacts = [
        ArtifactOut(
            id=artifact.id,
            artifact_type=artifact.artifact_type,
            title=artifact.title,
            external_ref=artifact.external_ref,
            url=artifact.url,
            payload_json=artifact.payload_json,
            created_at=artifact.created_at,
        )
        for artifact in sorted(issue.artifacts, key=lambda item: item.created_at, reverse=True)[:3]
    ]
    run_out = None
    if latest_run:
        run_out = RunOut(
            id=latest_run.id,
            run_key=latest_run.run_key,
            status=latest_run.status,
            current_agent=latest_run.current_agent,
            started_at=latest_run.started_at,
            updated_at=latest_run.updated_at,
            ended_at=latest_run.ended_at,
            outcome=latest_run.outcome,
            duration_seconds=latest_run.duration_seconds,
            events=[],
        )

    return IssueOut(
        id=issue.id,
        external_id=issue.external_id,
        title=issue.title,
        description=issue.description,
        issue_type=issue.issue_type,
        source=issue.source,
        trigger_name=issue.trigger_name,
        service_name=issue.service_name,
        severity=issue.severity,
        status=issue.status,
        owner=issue.owner,
        summary=issue.summary,
        resolution_summary=issue.resolution_summary,
        blast_radius=issue.blast_radius,
        guardrail_state=issue.guardrail_state,
        confidence_score=issue.confidence_score,
        recurrence_count=issue.recurrence_count,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        resolved_at=issue.resolved_at,
        latest_run=run_out,
        latest_artifacts=latest_artifacts,
    )


def build_dashboard_summary(db: Session) -> DashboardSummaryOut:
    issues = (
        db.query(Issue)
        .order_by(desc(Issue.updated_at))
        .limit(12)
        .all()
    )
    runs = db.query(Run).order_by(desc(Run.started_at)).limit(8).all()
    events = db.query(RunEvent).order_by(desc(RunEvent.created_at)).limit(12).all()
    triggers = db.query(TriggerEvent).order_by(desc(TriggerEvent.created_at)).limit(50).all()
    agents = db.query(AgentRuntime).order_by(AgentRuntime.name.asc()).all()
    connectors = db.query(ConnectorHealth).order_by(ConnectorHealth.name.asc()).all()

    resolved_count = db.query(func.count(Issue.id)).filter(Issue.status == "resolved").scalar() or 0
    running_count = db.query(func.count(Issue.id)).filter(Issue.status == "running").scalar() or 0
    open_count = db.query(func.count(Issue.id)).filter(Issue.status.in_(["open", "needs_review"])).scalar() or 0
    total_triggers = db.query(func.count(TriggerEvent.id)).scalar() or 0
    auto_prs = db.query(func.count(Artifact.id)).filter(Artifact.artifact_type == "pull_request").scalar() or 0
    jira_actions = db.query(func.count(Artifact.id)).filter(Artifact.artifact_type == "jira_ticket").scalar() or 0

    durations = [run.duration_seconds for run in db.query(Run).filter(Run.duration_seconds.is_not(None)).all()]
    mean_time = round(mean(durations), 1) if durations else None

    trigger_breakdown = [
        {"source": name, "count": count}
        for name, count in Counter(trigger.source for trigger in triggers).most_common()
    ]
    service_hotspots = [
        {"service_name": name, "count": count}
        for name, count in Counter(issue.service_name for issue in issues).most_common()
    ]
    live_runs = [
        {
            "run_id": run.id,
            "run_key": run.run_key,
            "issue_id": run.issue_id,
            "status": run.status,
            "current_agent": run.current_agent,
            "started_at": run.started_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
        }
        for run in runs
        if run.status in {"queued", "running", "needs_review"}
    ]
    recent_events = [
        {
            "run_id": event.run_id,
            "issue_id": event.issue_id,
            "node_name": event.node_name,
            "title": event.title,
            "detail": event.detail,
            "status": event.status,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]
    guardrails = [
        {
            "issue_id": issue.id,
            "external_id": issue.external_id,
            "state": issue.guardrail_state,
            "message": issue.summary or "Awaiting richer context.",
        }
        for issue in issues[:4]
    ]
    second_pair = [
        {
            "issue_id": event.issue_id,
            "message": event.detail,
            "node_name": event.node_name,
        }
        for event in events
        if event.event_type in {"guardrail", "review_note", "second_pair_of_eyes"}
    ][:4]

    metrics = {
        "resolved_issues": resolved_count,
        "running_issues": running_count,
        "open_issues": open_count,
        "total_triggers": total_triggers,
        "mean_time_to_resolve_seconds": mean_time,
        "auto_pull_requests": auto_prs,
        "jira_actions": jira_actions,
        "estimated_engineer_hours_saved": (auto_prs * 3) + resolved_count,
    }

    return DashboardSummaryOut(
        metrics=metrics,
        recent_issues=[build_issue_summary(issue) for issue in issues],
        trigger_breakdown=trigger_breakdown,
        service_hotspots=service_hotspots,
        live_runs=live_runs,
        recent_events=recent_events,
        guardrails=guardrails,
        second_pair_of_eyes=second_pair,
        agent_runtimes=[AgentRuntimeOut.model_validate(agent, from_attributes=True) for agent in agents],
        connectors=[ConnectorHealthOut.model_validate(item, from_attributes=True) for item in connectors],
    )
