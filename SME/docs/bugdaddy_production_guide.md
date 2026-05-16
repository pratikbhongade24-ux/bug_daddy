# BugDaddy Production Operations Guide

## Purpose
BugDaddy is a production AI-assisted engineering operations platform for incident response, issue triage, code remediation workflows, and security observability.

## Core Production Responsibilities
- Ingest and prioritize runtime issues from integrated sources.
- Route issues to the appropriate agent workflow (incident, bug, reviewer, SME).
- Provide operator-facing visibility across issue lifecycle states.
- Maintain auditability of actions, assignments, and automation outcomes.

## Operational Domains
1. Incident Management
- Escalation queue for critical issues.
- Incident-first routing for high-severity and outage signals.

2. Engineering Triage
- Automated prioritization and workflow assignment.
- Rich context passed to downstream agent workflows.

3. Security Monitoring
- Scanner session orchestration and finding ingestion.
- CVE discovery and operational tracking in issue views.

4. Knowledge and Support
- Embedded SME assistant with RAG-backed retrieval.
- Conversation history, citations, and feedback tracking.

## Production Deployment Notes
- Frontend serves operator dashboard experiences.
- Backend enforces authN/authZ and orchestrates services.
- RAG backend is protected behind API key plus backend proxy.
- Data stores should run with backups, monitoring, and encryption.

## Recommended Metadata Tags for RAG
- domain: bugdaddy
- capability: triage | incident | security | support
- environment: prod
- audience: operator | developer | admin
