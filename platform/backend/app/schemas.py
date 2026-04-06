from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TriggerIngestRequest(BaseModel):
    title: str
    description: str
    issue_type: str = "incident"
    source: str = "api"
    trigger_name: str = "manual"
    service_name: str = "unknown-service"
    severity: str = "unknown"
    owner: str | None = None
    recurrence_count: int = 1
    confidence_score: float = 0.5
    blast_radius: str | None = None
    logs: list[str] = Field(default_factory=list)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    kb_context: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ScenarioLaunchRequest(BaseModel):
    scenario_id: str


class RetryRequest(BaseModel):
    preserve_history: bool = True


class ArtifactOut(BaseModel):
    id: int
    artifact_type: str
    title: str
    external_ref: str | None
    url: str | None
    payload_json: dict[str, Any]
    created_at: datetime


class RunEventOut(BaseModel):
    id: int
    sequence: int
    event_type: str
    node_name: str
    title: str
    detail: str
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime


class RunOut(BaseModel):
    id: int
    run_key: str
    status: str
    current_agent: str | None
    started_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    outcome: str | None
    duration_seconds: float | None
    events: list[RunEventOut] = Field(default_factory=list)


class TriggerOut(BaseModel):
    id: int
    source: str
    trigger_name: str
    service_name: str
    payload_json: dict[str, Any]
    status: str
    created_at: datetime


class IssueOut(BaseModel):
    id: int
    external_id: str
    title: str
    description: str
    issue_type: str
    source: str
    trigger_name: str
    service_name: str
    severity: str
    status: str
    owner: str | None
    summary: str | None
    resolution_summary: str | None
    blast_radius: str | None
    guardrail_state: str
    confidence_score: float
    recurrence_count: int
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    latest_run: RunOut | None = None
    latest_artifacts: list[ArtifactOut] = Field(default_factory=list)


class IssueDetailOut(IssueOut):
    logs: list[str] = Field(default_factory=list)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    kb_context: str | None = None
    source_payload: dict[str, Any] = Field(default_factory=dict)
    triggers: list[TriggerOut] = Field(default_factory=list)
    runs: list[RunOut] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)


class AgentRuntimeOut(BaseModel):
    id: int
    name: str
    runtime_arn: str | None
    runtime_id: str | None
    status: str
    average_latency_ms: float | None
    success_rate: float | None
    version: str
    last_invoked_at: datetime | None


class ConnectorHealthOut(BaseModel):
    id: int
    name: str
    status: str
    detail: str
    checked_at: datetime


class ScenarioOut(BaseModel):
    id: str
    title: str
    summary: str
    issue_type: str
    source: str
    trigger_name: str
    service_name: str
    severity: str
    blast_radius: str
    recurrence_count: int


class DashboardSummaryOut(BaseModel):
    metrics: dict[str, Any]
    recent_issues: list[IssueOut]
    trigger_breakdown: list[dict[str, Any]]
    service_hotspots: list[dict[str, Any]]
    live_runs: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]
    guardrails: list[dict[str, Any]]
    second_pair_of_eyes: list[dict[str, Any]]
    agent_runtimes: list[AgentRuntimeOut]
    connectors: list[ConnectorHealthOut]
