from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import AgentRuntime, Artifact, Issue, Run, RunEvent, TriggerEvent
from app.schemas import TriggerIngestRequest
from app.services.agentcore import agentcore_client
from app.services.catalog import get_scenario_payload
from app.services.realtime import realtime_manager


settings = get_settings()

AGENT_CHAIN = ["trigger_router", "incident_daddy", "sme_agent", "bug_daddy", "reviewer_daddy", "platform"]


def create_issue_and_run(db: Session, request: TriggerIngestRequest) -> tuple[Issue, Run]:
    external_id = f"ISS-{datetime.utcnow():%Y%m%d}-{str(uuid4())[:6].upper()}"
    issue = Issue(
        external_id=external_id,
        title=request.title,
        description=request.description,
        issue_type=request.issue_type,
        source=request.source,
        trigger_name=request.trigger_name,
        service_name=request.service_name,
        severity=request.severity,
        status="queued",
        owner=request.owner,
        blast_radius=request.blast_radius,
        guardrail_state="reviewing",
        confidence_score=request.confidence_score,
        recurrence_count=request.recurrence_count,
        source_payload=request.payload,
        logs=request.logs,
        telemetry=request.telemetry,
        kb_context=request.kb_context,
    )
    db.add(issue)
    db.flush()

    trigger = TriggerEvent(
        issue_id=issue.id,
        source=request.source,
        trigger_name=request.trigger_name,
        service_name=request.service_name,
        payload_json=request.payload,
        status="accepted",
    )
    run = Run(
        issue_id=issue.id,
        run_key=f"run-{uuid4().hex[:10]}",
        status="queued",
        current_agent="trigger_router",
    )
    db.add(trigger)
    db.add(run)
    db.commit()
    db.refresh(issue)
    db.refresh(run)
    return issue, run


def launch_scenario(scenario_id: str) -> tuple[Issue, Run]:
    payload = get_scenario_payload(scenario_id)
    request = TriggerIngestRequest(
        title=payload["title"],
        description=payload["description"],
        issue_type=payload["issue_type"],
        source=payload["source"],
        trigger_name=payload["trigger_name"],
        service_name=payload["service_name"],
        severity=payload["severity"],
        blast_radius=payload["blast_radius"],
        recurrence_count=payload["recurrence_count"],
        confidence_score=0.71,
        logs=payload["logs"],
        telemetry=payload["telemetry"],
        kb_context=payload["kb_context"],
        payload=payload,
    )
    with SessionLocal() as db:
        issue, run = create_issue_and_run(db, request)
    return issue, run


def relaunch_issue(issue_id: int) -> tuple[Issue, Run]:
    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        if issue is None:
            raise KeyError(f"Issue {issue_id} not found.")

        request = TriggerIngestRequest(
            title=issue.title,
            description=issue.description,
            issue_type=issue.issue_type,
            source=issue.source,
            trigger_name=issue.trigger_name,
            service_name=issue.service_name,
            severity=issue.severity,
            owner=issue.owner,
            recurrence_count=issue.recurrence_count,
            confidence_score=issue.confidence_score,
            blast_radius=issue.blast_radius,
            logs=issue.logs,
            telemetry=issue.telemetry,
            kb_context=issue.kb_context,
            payload=issue.source_payload,
        )
        new_issue, run = create_issue_and_run(db, request)
    return new_issue, run


async def process_run(issue_id: int, run_id: int) -> None:
    step_delay = 0.75
    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        run = db.get(Run, run_id)
        if issue is None or run is None:
            return
        issue.status = "running"
        run.status = "running"
        run.current_agent = "trigger_router"
        db.commit()

    issue_snapshot = _issue_snapshot(issue_id)
    next_agent = "incident_daddy" if issue_snapshot["issue_type"] == "incident" else "sme_agent"
    await _emit_event(
        issue_id,
        run_id,
        "trigger_received",
        "trigger_router",
        "Trigger normalized",
        "The platform accepted the trigger and created a runnable issue record.",
        "success",
        {
            "stage": "ingest",
            "session_id": f"{run_id}:trigger_router",
            "log_line": f"normalized {issue_snapshot['source']} signal for {issue_snapshot['service_name']}",
            "token_usage": {"input_tokens": 42, "output_tokens": 16, "total_tokens": 58},
        },
    )
    await _emit_event(
        issue_id,
        run_id,
        "agent_handoff",
        "trigger_router",
        f"Handoff to {next_agent}",
        f"Routing completed. The issue is being transferred to {next_agent}.",
        "info",
        {
            "from": "trigger_router",
            "to": next_agent,
            "session_id": f"{run_id}:trigger_router",
            "log_line": f"handoff trigger_router -> {next_agent}",
        },
    )
    await asyncio.sleep(step_delay / 2)

    if _is_incident(issue_id):
        incident_result = await _invoke_agent(
            issue_id,
            run_id,
            "incident_daddy",
            settings.incident_daddy_runtime_arn,
            "Incident triage",
            "Reviewed the signal, classified severity, and prepared the incident summary.",
            issue_snapshot=issue_snapshot,
            next_agent="sme_agent",
        )
        # Extract real artifact URLs from incident_daddy response
        incident_artifacts = {a.get("type"): a for a in incident_result.get("artifacts", [])}
        slack_art = incident_artifacts.get("slack_channel", {})
        jira_art = incident_artifacts.get("jira_ticket", {})
        await _store_artifact(
            issue_id, run_id, "slack_channel",
            slack_art.get("title", "Slack Incident Channel"),
            slack_art.get("external_ref"), slack_art.get("url"), incident_result,
        )
        await _store_artifact(
            issue_id, run_id, "jira_ticket",
            jira_art.get("title", "Incident Jira Ticket"),
            jira_art.get("external_ref"), jira_art.get("url"), incident_result,
        )
        await asyncio.sleep(step_delay)

    sme_result = await _invoke_agent(
        issue_id,
        run_id,
        "sme_agent",
        settings.sme_agent_runtime_arn,
        "Domain context injected",
        "Retrieved SOP steps, service ownership, and historical patterns for the issue.",
        issue_snapshot=issue_snapshot,
        next_agent="bug_daddy",
    )
    await asyncio.sleep(step_delay)

    bug_result = await _invoke_agent(
        issue_id,
        run_id,
        "bug_daddy",
        settings.bug_daddy_runtime_arn,
        "Remediation strategy created",
        "Generated a remediation plan, gathered technical evidence, and prepared a proposed change.",
        issue_snapshot=issue_snapshot,
        next_agent="reviewer_daddy",
    )
    await asyncio.sleep(step_delay)

    reviewer_result = await _invoke_agent(
        issue_id,
        run_id,
        "reviewer_daddy",
        settings.reviewer_daddy_runtime_arn,
        "Review and action decision",
        "Reviewer validated the proposed change, checked rollback risk, and decided the release path.",
        event_type="review_note",
        issue_snapshot=issue_snapshot,
        next_agent="platform",
    )
    disposition = reviewer_result.get("disposition", "pull_request")

    artifact_type = "pull_request" if disposition == "pull_request" else "jira_ticket"
    artifact_title = "Autonomous Pull Request" if disposition == "pull_request" else "Operational Jira Resolution"

    # Extract real artifact URL from the AgentCore response
    artifact_url = None
    for art in reviewer_result.get("artifacts", []):
        if art.get("type") == artifact_type:
            artifact_url = art.get("url")
            artifact_title = art.get("title", artifact_title)
            break
    await _store_artifact(issue_id, run_id, artifact_type, artifact_title, None, artifact_url, reviewer_result)

    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        run = db.get(Run, run_id)
        if issue is None or run is None:
            return
        run.status = "resolved"
        run.outcome = disposition
        run.current_agent = "completed"
        run.ended_at = datetime.utcnow()
        run.duration_seconds = (run.ended_at - run.started_at).total_seconds()
        issue.status = "resolved" if disposition != "rework_required" else "needs_review"
        issue.summary = incident_result.get("summary") if issue.issue_type == "incident" else bug_result.get("summary")
        issue.resolution_summary = reviewer_result.get("summary")
        issue.guardrail_state = "approval_required" if disposition == "rework_required" else "safe"
        # Use real confidence from the final agent response
        final_confidence = reviewer_result.get("confidence") or bug_result.get("confidence")
        if final_confidence is not None:
            issue.confidence_score = round(final_confidence, 2)
        if issue.status == "resolved":
            issue.resolved_at = datetime.utcnow()
        primary_agent = "incident_daddy" if issue.issue_type == "incident" else "bug_daddy"
        primary_result = incident_result if issue.issue_type == "incident" else bug_result
        _touch_agent_runtime(db, primary_agent, latency_ms=primary_result.get("_latency_ms"))
        _touch_agent_runtime(db, "sme_agent", latency_ms=sme_result.get("_latency_ms"))
        _touch_agent_runtime(db, "reviewer_daddy", latency_ms=reviewer_result.get("_latency_ms"))
        db.commit()

    await _emit_event(
        issue_id,
        run_id,
        "resolution",
        "platform",
        "Issue resolved",
        "The orchestration completed and the platform published final artifacts to the operations surface.",
        "success",
        {
            "disposition": disposition,
            "review_summary": reviewer_result.get("summary"),
            "session_id": f"{run_id}:platform",
            "token_usage": {"input_tokens": 18, "output_tokens": 12, "total_tokens": 30},
            "log_line": f"finalized run with disposition={disposition}",
        },
    )


def _is_incident(issue_id: int) -> bool:
    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        return bool(issue and issue.issue_type == "incident")


async def _invoke_agent(
    issue_id: int,
    run_id: int,
    agent_name: str,
    runtime_arn: str | None,
    title: str,
    detail: str,
    event_type: str = "agent_step",
    issue_snapshot: dict[str, Any] | None = None,
    next_agent: str | None = None,
) -> dict[str, Any]:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run:
            run.current_agent = agent_name
            db.commit()

    snapshot = issue_snapshot or _issue_snapshot(issue_id)
    session_id = f"{run_id}:{agent_name}"

    # Invoke AgentCore and measure latency
    payload = {
        "issue_id": issue_id,
        "run_id": run_id,
        "agent_name": agent_name,
        "title": title,
        "service_name": snapshot["service_name"],
        "issue_type": snapshot["issue_type"],
        "severity": snapshot.get("severity"),
        "blast_radius": snapshot.get("blast_radius"),
        "recurrence_count": snapshot.get("recurrence_count"),
        "trigger_name": snapshot.get("trigger_name"),
        "source": snapshot.get("source"),
    }
    start = time.monotonic()
    response = agentcore_client.invoke(runtime_arn, payload)
    latency_ms = round((time.monotonic() - start) * 1000)
    response["_latency_ms"] = latency_ms

    response.setdefault("summary", f"{agent_name} completed: {title}.")
    if agent_name == "reviewer_daddy":
        response.setdefault("disposition", "pull_request")

    # Extract real values from the AgentCore response
    reasoning = response.get("reasoning", response.get("summary", ""))
    tool_calls: list[dict[str, Any]] = response.get("tool_calls", [])
    token_usage: dict[str, int] = response.get("token_usage", {})
    confidence = response.get("confidence")

    # Emit thought event
    await _emit_event(
        issue_id,
        run_id,
        "agent_thought",
        agent_name,
        f"{agent_name} analysis",
        reasoning,
        "info",
        {
            "session_id": session_id,
            "thought_summary": reasoning,
            "token_usage": token_usage,
            "log_line": f"{agent_name} analysis: {reasoning}",
        },
    )

    # Emit tool call events from real AgentCore data
    for tc in tool_calls:
        tool_name = tc.get("tool_name", "unknown_tool")
        tc_latency = tc.get("latency_ms", 0)
        tc_token_usage = tc.get("token_usage", {})

        await _emit_event(
            issue_id,
            run_id,
            "tool_call",
            agent_name,
            f"{tool_name} invoked",
            tc.get("summary", f"{tool_name} called"),
            "running",
            {
                "session_id": session_id,
                "tool_name": tool_name,
                "arguments": tc.get("arguments", {}),
                "latency_ms": tc_latency,
                "token_usage": tc_token_usage,
                "log_line": f"{agent_name} -> {tool_name}",
            },
        )
        await _emit_event(
            issue_id,
            run_id,
            "tool_result",
            agent_name,
            f"{tool_name} returned",
            tc.get("result_preview", f"{tool_name} completed"),
            "success",
            {
                "session_id": session_id,
                "tool_name": tool_name,
                "result_preview": tc.get("result_preview", ""),
                "latency_ms": tc_latency,
                "token_usage": tc_token_usage,
                "log_line": f"{tool_name} completed in {tc_latency}ms",
            },
        )

    # Emit completion event
    await _emit_event(
        issue_id,
        run_id,
        event_type,
        agent_name,
        title,
        detail,
        "success" if agent_name != "reviewer_daddy" else "info",
        {
            "response_summary": response.get("summary"),
            "mode": "agentcore",
            "confidence": confidence,
            "session_id": session_id,
            "tool_count": len(tool_calls),
            "token_usage": token_usage,
            "thought_summary": reasoning,
            "latency_ms": latency_ms,
            "log_line": f"{agent_name} completed in {latency_ms}ms",
        },
    )

    if next_agent:
        await _emit_event(
            issue_id,
            run_id,
            "agent_handoff",
            agent_name,
            f"Handoff to {next_agent}",
            f"{agent_name} completed and transferred control to {next_agent}.",
            "info",
            {
                "session_id": session_id,
                "from": agent_name,
                "to": next_agent,
                "token_usage": token_usage,
                "log_line": f"handoff {agent_name} -> {next_agent}",
            },
        )
    return response


async def _emit_event(
    issue_id: int,
    run_id: int,
    event_type: str,
    node_name: str,
    title: str,
    detail: str,
    status: str,
    metadata: dict[str, Any],
) -> None:
    with SessionLocal() as db:
        sequence = db.query(RunEvent).filter(RunEvent.run_id == run_id).count() + 1
        event = RunEvent(
            run_id=run_id,
            issue_id=issue_id,
            sequence=sequence,
            event_type=event_type,
            node_name=node_name,
            title=title,
            detail=detail,
            status=status,
            metadata_json=metadata,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

    payload = {
        "kind": "run_event",
        "issue_id": issue_id,
        "run_id": run_id,
        "sequence": event.sequence,
        "node_name": node_name,
        "title": title,
        "detail": detail,
        "status": status,
        "metadata": metadata,
        "created_at": event.created_at.isoformat(),
    }
    await realtime_manager.broadcast_run(run_id, payload)
    await realtime_manager.broadcast_dashboard({"kind": "dashboard_refresh", "issue_id": issue_id, "run_id": run_id})


async def _store_artifact(
    issue_id: int,
    run_id: int,
    artifact_type: str,
    title: str,
    external_ref: str | None,
    url: str | None,
    payload_json: dict[str, Any],
) -> None:
    with SessionLocal() as db:
        artifact = Artifact(
            issue_id=issue_id,
            run_id=run_id,
            artifact_type=artifact_type,
            title=title,
            external_ref=external_ref,
            url=url,
            payload_json=payload_json,
        )
        db.add(artifact)
        db.commit()


def _touch_agent_runtime(db: Session, name: str, latency_ms: int | None = None) -> None:
    runtime = db.query(AgentRuntime).filter(AgentRuntime.name == name).one_or_none()
    if runtime is None:
        return
    runtime.last_invoked_at = datetime.utcnow()
    if latency_ms is not None:
        runtime.average_latency_ms = float(latency_ms)
    runtime.status = "ready"


def _issue_snapshot(issue_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        if issue is None:
            return {
                "title": "Unknown issue",
                "issue_type": "incident",
                "service_name": "unknown-service",
                "severity": "unknown",
                "source": "unknown",
                "trigger_name": "unknown",
            }
        return {
            "title": issue.title,
            "issue_type": issue.issue_type,
            "service_name": issue.service_name,
            "severity": issue.severity,
            "source": issue.source,
            "trigger_name": issue.trigger_name,
            "blast_radius": issue.blast_radius,
            "recurrence_count": issue.recurrence_count,
        }


