from __future__ import annotations

from copy import deepcopy


SCENARIOS = [
    {
        "id": "checkout-null-pointer",
        "title": "Recurring checkout null pointer",
        "summary": "Checkout service throws a recurring null pointer after a release.",
        "issue_type": "incident",
        "source": "microservice_logs",
        "trigger_name": "log_parser",
        "service_name": "checkout-service",
        "severity": "sev2",
        "blast_radius": "payments-and-order-placement",
        "recurrence_count": 8,
        "description": "Recurring null pointer degrades checkout completion rate and causes intermittent payment retries.",
        "logs": [
            "java.lang.NullPointerException at CheckoutFlow.java:42",
            "OrderDraft missing billing profile after release 2026.04.05-3",
            "Retry queue backlog rising for payment-authorize"
        ],
        "telemetry": {"latency_p95_ms": 1900, "error_rate": 0.14, "region": "ap-south-1"},
        "kb_context": "SOP: validate billing profile hydration before checkout finalization. Owner: commerce-payments."
    },
    {
        "id": "support-cpu-regression",
        "title": "Support service CPU regression",
        "summary": "Background support summarizer shows sustained CPU spikes and p95 degradation.",
        "issue_type": "bug",
        "source": "telemetry_monitor",
        "trigger_name": "performance_watch",
        "service_name": "support-service",
        "severity": "sev3",
        "blast_radius": "internal-agent-productivity",
        "recurrence_count": 13,
        "description": "The support summarizer workload regressed after prompt expansion and now burns CPU on batch processing.",
        "logs": [
            "summary_batch took 8421ms for tenant=sg-enterprise",
            "warning: token window inflation after prompt enrichment",
            "cpu utilization sustained above 92 percent"
        ],
        "telemetry": {"latency_p95_ms": 8421, "cpu_percent": 92, "region": "ap-south-1"},
        "kb_context": "Runbook: reduce prompt fanout and batch size when summarizer p95 exceeds 5 seconds."
    },
    {
        "id": "kyc-sop-drift",
        "title": "KYC incident with SOP drift risk",
        "summary": "KYC verification incident acknowledged, but engineers are missing one dependency check from the SOP.",
        "issue_type": "incident",
        "source": "slack",
        "trigger_name": "incident_channel",
        "service_name": "kyc-service",
        "severity": "sev1",
        "blast_radius": "new-user-onboarding",
        "recurrence_count": 3,
        "description": "The incident requires real-time guidance and a second pair of eyes on mitigations.",
        "logs": [
            "identity provider timeout crossing 30s",
            "fallback provider quota near threshold",
            "manual override requests rising"
        ],
        "telemetry": {"availability": 0.82, "region": "ap-south-1"},
        "kb_context": "SOP: acknowledge incident, engage fallback provider owner, confirm quota, verify mandate impact before customer messaging."
    },
]


def list_scenarios() -> list[dict]:
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "summary": item["summary"],
            "issue_type": item["issue_type"],
            "source": item["source"],
            "trigger_name": item["trigger_name"],
            "service_name": item["service_name"],
            "severity": item["severity"],
            "blast_radius": item["blast_radius"],
            "recurrence_count": item["recurrence_count"],
        }
        for item in SCENARIOS
    ]


def get_scenario_payload(scenario_id: str) -> dict:
    for item in SCENARIOS:
        if item["id"] == scenario_id:
            return deepcopy(item)
    raise KeyError(f"Unknown scenario: {scenario_id}")
