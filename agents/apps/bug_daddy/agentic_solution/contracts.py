from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["sev1", "sev2", "sev3", "unknown"]
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


class IncidentResponse(BaseModel):
    component: Literal["incident_daddy"] = "incident_daddy"
    summary: str
    severity: Severity = "unknown"
    owner_hint: str | None = None
    next_action: str
    handoff_to_bug: bool = False
    bug_request: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class BugRequest(IssueContext):
    incident_summary: str | None = None
    incident_severity: Severity | None = None
    incident_artifacts: list[dict[str, Any]] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    issue: IssueContext
    plan: str
    context_summary: str
    sme_guidance: str
    log_analysis: str
    fix_proposal: str
    critique: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    component: Literal["reviewer_daddy"] = "reviewer_daddy"
    disposition: ReviewDisposition
    summary: str
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
