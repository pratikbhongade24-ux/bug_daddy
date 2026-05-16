from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["sev1", "sev2", "sev3", "unknown"]
Criticality = Literal["critical", "high", "medium", "low", "unknown"]
Priority = Literal["p0", "p1", "p2", "p3", "p4", "unknown"]
ReviewDisposition = Literal["pull_request", "jira_ticket", "rework_required"]
BugResolution = Literal["review_required", "pull_request", "jira_ticket", "rework_required"]


class IssueContext(BaseModel):
    prompt: str
    source: str = "api"
    service_name: str | None = None
    repository: str | None = None
    logs: list[str] = Field(default_factory=list)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    kb_context: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SMEQueryRequest(BaseModel):
    question: str
    requested_by: str
    context: IssueContext


class SMEQueryResponse(BaseModel):
    component: Literal["sme_agent"] = "sme_agent"
    summary: str
    references: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class IncidentRequest(IssueContext):
    trigger: str | None = None
    criticality: Criticality = "unknown"
    priority: Priority = "unknown"
    opened_at: datetime | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class IncidentSLAKPI(BaseModel):
    ack_target_minutes: int
    resolve_target_minutes: int
    time_to_ack_minutes: int | None = None
    time_to_resolve_minutes: int | None = None
    ack_remaining_minutes: int | None = None
    resolve_remaining_minutes: int | None = None
    ack_breached: bool = False
    resolve_breached: bool = False


class IncidentReport(BaseModel):
    title: str
    severity: Severity = "unknown"
    criticality: Criticality = "unknown"
    priority: Priority = "unknown"
    blast_radius: str | None = None
    root_cause: str | None = None
    actions_taken: list[str] = Field(default_factory=list)
    owner: str | None = None
    status: str = "Investigating"
    raw_markdown: str


class IncidentResponse(BaseModel):
    component: Literal["incident_daddy"] = "incident_daddy"
    summary: str
    severity: Severity = "unknown"
    criticality: Criticality = "unknown"
    priority: Priority = "unknown"
    sla_kpis: IncidentSLAKPI | None = None
    owner_hint: str | None = None
    next_action: str
    handoff_to_bug: bool = False
    bug_request: dict[str, Any] | None = None
    incident_report: IncidentReport | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class BugRequest(IssueContext):
    incident_summary: str | None = None
    incident_severity: Severity | None = None
    criticality: Criticality = "unknown"
    priority: Priority = "unknown"
    incident_artifacts: list[dict[str, Any]] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    issue: IssueContext
    strategy_plan: str
    context_analysis: str
    sme_guidance: str
    fix_proposal: str
    critique: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    component: Literal["reviewer_daddy"] = "reviewer_daddy"
    disposition: ReviewDisposition
    summary: str
    pr_url: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class BugResponse(BaseModel):
    component: Literal["bug_daddy"] = "bug_daddy"
    summary: str
    resolution_kind: BugResolution
    review_request: dict[str, Any] | None = None
    review_response: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


FeatureDisposition = Literal["pull_request", "rework_required", "review_required"]


class FeatureRequest(BaseModel):
    prd: str
    source: str = "api"
    service_name: str | None = None
    repository: str | None = None
    kb_context: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureResponse(BaseModel):
    component: Literal["feature_daddy"] = "feature_daddy"
    feature_name: str
    summary: str
    disposition: FeatureDisposition
    jira_key: str | None = None
    pr_url: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
