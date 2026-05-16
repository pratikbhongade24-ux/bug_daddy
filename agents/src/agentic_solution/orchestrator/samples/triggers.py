"""
Realistic trigger payloads, shaped to mirror real upstream emitters
(CloudWatch alarm, GuardDuty finding, Snyk webhook, etc.).

The shapes are intentionally heterogeneous so the normalization layer
does real work — each payload exercises a different inference path
(metric-derived class, hint-derived class, CVSS-derived severity, etc.).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..contracts import RawTrigger, TriggerSource


def build_sample_triggers() -> list[RawTrigger]:
    """Return one trigger per incident class, ordered chaotically by
    severity so the priority scheduler is visibly exercised."""
    now = datetime.now(UTC)
    return [
        # SEV3 hygiene first — would block SEV0 in a FIFO scheduler.
        RawTrigger(
            source=TriggerSource.GRAFANA,
            received_at=now,
            correlation_hint="tls-checkout-cert",
            payload={
                "alert_name": "tls_expiry",
                "hostname": "checkout.api.example.com",
                "service": "checkout-service",
                "environment": "prod",
                "region": "ap-south-1",
                "days_until_expiry": 6,
                "severity": "warning",
            },
        ),
        # SEV4 informational — should drain only via fairness slot.
        RawTrigger(
            source=TriggerSource.PROMETHEUS,
            received_at=now,
            correlation_hint="cpu-checkout-warmpath",
            payload={
                "alarm_name": "cpu_utilization",
                "service": "checkout-service",
                "environment": "prod",
                "region": "ap-south-1",
                "metrics": {"cpu_utilization": 78.0},
                "severity": "info",
            },
        ),
        # SEV0 ransomware indicator — must preempt the queue.
        RawTrigger(
            source=TriggerSource.GUARDDUTY,
            received_at=now,
            correlation_hint="ransomware-fleet-prod",
            payload={
                "type": "ransomware",
                "service": "asset-store",
                "environment": "prod",
                "region": "ap-south-1",
                "indicators": ["mass_file_rename", "shadow_copy_deletion"],
                "severity": "critical",
            },
        ),
        # SEV1 service downtime with recent deploy — should route to
        # ServiceDowntimeRemediator with rollback action.
        RawTrigger(
            source=TriggerSource.PAGERDUTY,
            received_at=now,
            correlation_hint="downtime-checkout-prod",
            payload={
                "title": "checkout-service health_check_failed",
                "service": "checkout-service",
                "environment": "prod",
                "region": "ap-south-1",
                "recent_deploy": True,
                "severity": "sev1",
            },
        ),
        # SEV2 elevated error rate — exercise the bug daddy hand-off field.
        RawTrigger(
            source=TriggerSource.DATADOG,
            received_at=now,
            correlation_hint="errors-payments-prod",
            payload={
                "alert_name": "elevated_error_rate",
                "service": "payments-service",
                "environment": "prod",
                "region": "ap-south-1",
                "metrics": {"error_rate": 0.087},
                "severity": "sev2",
            },
        ),
        # SEV0 CVE with critical CVSS — severity inferred from CVSS, not text.
        RawTrigger(
            source=TriggerSource.SNYK,
            received_at=now,
            correlation_hint="cve-log4j-asset-store",
            payload={
                "type": "cve",
                "cve_id": "CVE-2021-44228",
                "cvss_score": 10.0,
                "service": "asset-store",
                "environment": "prod",
                "severity": "info",  # upstream is wrong; normalizer overrides
            },
        ),
        # SEV1 IAM anomaly.
        RawTrigger(
            source=TriggerSource.GUARDDUTY,
            received_at=now,
            correlation_hint="iam-impossible-travel",
            payload={
                "type": "iam_anomaly",
                "principal": "arn:aws:iam::1234:user/ops-bot",
                "environment": "prod",
                "severity": "high",
            },
        ),
        # SEV2 failed deployment.
        RawTrigger(
            source=TriggerSource.GITHUB,
            received_at=now,
            correlation_hint="deploy-checkout-v412-failed",
            payload={
                "type": "deployment_failed",
                "service": "checkout-service",
                "environment": "prod",
                "severity": "sev2",
            },
        ),
        # SEV2 database saturation.
        RawTrigger(
            source=TriggerSource.CLOUDWATCH,
            received_at=now,
            correlation_hint="rds-conn-spike",
            payload={
                "alarm_name": "rds_connections",
                "service": "payments-service",
                "environment": "prod",
                "metrics": {"rds_connections": 980, "cpu_utilization": 92.0},
                "severity": "sev2",
            },
        ),
        # SEV3 WAF anomaly.
        RawTrigger(
            source=TriggerSource.WAF,
            received_at=now,
            correlation_hint="waf-spike-checkout",
            payload={
                "type": "waf_block",
                "service": "checkout-service",
                "environment": "prod",
                "severity": "warning",
            },
        ),
        # SEV0 unauthorized API access.
        RawTrigger(
            source=TriggerSource.CLOUDWATCH,
            received_at=now,
            correlation_hint="unauth-api-checkout",
            payload={
                "type": "unauthorized_api",
                "source_ip": "203.0.113.42",
                "service": "checkout-service",
                "environment": "prod",
                "severity": "critical",
            },
        ),
        # SEV3 cloud misconfiguration drift.
        RawTrigger(
            source=TriggerSource.SECURITY_HUB,
            received_at=now,
            correlation_hint="s3-public-bucket-asset-store",
            payload={
                "type": "config_drift",
                "resource": "arn:aws:s3:::asset-store-prod",
                "environment": "prod",
                "severity": "low",
            },
        ),
        # SEV2 memory pressure derived from metric only (no text hint).
        RawTrigger(
            source=TriggerSource.PROMETHEUS,
            received_at=now,
            correlation_hint="mem-payments-prod",
            payload={
                "service": "payments-service",
                "environment": "prod",
                "metrics": {"memory_utilization": 94.0},
                "severity": "sev2",
            },
        ),
        # SEV1 IDS anomaly.
        RawTrigger(
            source=TriggerSource.IDS,
            received_at=now,
            correlation_hint="ids-lateral-movement",
            payload={
                "type": "ids_alert",
                "host": "i-0123456789abcdef0",
                "environment": "prod",
                "severity": "high",
            },
        ),
    ]


SAMPLE_TRIGGERS = build_sample_triggers()
