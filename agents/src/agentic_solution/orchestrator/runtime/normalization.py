"""
Event Normalization & Enrichment.

Translates a heterogeneous ``RawTrigger`` into the canonical
``NormalizedEvent`` envelope. This is where every downstream invariant
gets established:

* Severity is *scored*, not passthrough.
* Incident class is *derived* from a deterministic rule table —
  upstream-provided categories are treated as hints, not truth.
* A stable ``correlation_id`` is established (preferring upstream
  hint, falling back to a content-derived hash).
* A ``fingerprint`` collapses duplicate observations of the same
  incident across re-firings.
* Enrichment annotations (environment, owning team, runbook hints)
  are attached without mutating the raw payload.

The normalizer is deliberately small and rule-driven; we do not call an
LLM here. Putting model judgment in the normalization path would make
routing non-reproducible, which is the *one* property we refuse to give up.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ..contracts import (
    IncidentClass,
    NormalizedEvent,
    RawTrigger,
    SeverityTier,
    TriggerSource,
)


# Mapping from coarse upstream hints -> incident class. We intentionally
# lower-case the keys at lookup time so upstream casing does not matter.
_HINT_TO_CLASS: dict[str, IncidentClass] = {
    # Compute / capacity
    "cpu": IncidentClass.CPU_SPIKE,
    "high_cpu": IncidentClass.CPU_SPIKE,
    "cpuutilization": IncidentClass.CPU_SPIKE,
    "memory": IncidentClass.MEMORY_PRESSURE,
    "oom": IncidentClass.MEMORY_PRESSURE,
    "memoryutilization": IncidentClass.MEMORY_PRESSURE,
    "db_saturation": IncidentClass.DATABASE_SATURATION,
    "rds_cpu": IncidentClass.DATABASE_SATURATION,
    "rds_connections": IncidentClass.DATABASE_SATURATION,
    # Availability
    "service_down": IncidentClass.SERVICE_DOWNTIME,
    "downtime": IncidentClass.SERVICE_DOWNTIME,
    "health_check_failed": IncidentClass.SERVICE_DOWNTIME,
    "5xx_rate": IncidentClass.ELEVATED_ERROR_RATE,
    "error_rate": IncidentClass.ELEVATED_ERROR_RATE,
    "deploy_failed": IncidentClass.FAILED_DEPLOYMENT,
    "deployment_failed": IncidentClass.FAILED_DEPLOYMENT,
    # Security
    "cve": IncidentClass.CVE_VULNERABILITY,
    "vulnerability": IncidentClass.CVE_VULNERABILITY,
    "iam_anomaly": IncidentClass.SUSPICIOUS_IAM,
    "guardduty_finding": IncidentClass.SUSPICIOUS_IAM,
    "unauthorized_api": IncidentClass.UNAUTHORIZED_API_ACCESS,
    "unauthorized": IncidentClass.UNAUTHORIZED_API_ACCESS,
    "waf_block": IncidentClass.WAF_ANOMALY,
    "ids_alert": IncidentClass.IDS_ANOMALY,
    "tls_expiry": IncidentClass.TLS_EXPIRY,
    "certificate_expiry": IncidentClass.TLS_EXPIRY,
    "misconfiguration": IncidentClass.CLOUD_MISCONFIG,
    "config_drift": IncidentClass.CLOUD_MISCONFIG,
    "ransomware": IncidentClass.RANSOMWARE_INDICATOR,
    "mass_encryption": IncidentClass.RANSOMWARE_INDICATOR,
}


# Severity inference rules. Order matters — we return on first match.
_SEVERITY_FROM_TEXT: tuple[tuple[str, SeverityTier], ...] = (
    ("critical", SeverityTier.SEV0),
    ("sev0", SeverityTier.SEV0),
    ("p0", SeverityTier.SEV0),
    ("emergency", SeverityTier.SEV0),
    ("ransom", SeverityTier.SEV0),
    ("sev1", SeverityTier.SEV1),
    ("p1", SeverityTier.SEV1),
    ("high", SeverityTier.SEV1),
    ("major", SeverityTier.SEV1),
    ("sev2", SeverityTier.SEV2),
    ("p2", SeverityTier.SEV2),
    ("medium", SeverityTier.SEV2),
    ("warning", SeverityTier.SEV2),
    ("sev3", SeverityTier.SEV3),
    ("p3", SeverityTier.SEV3),
    ("low", SeverityTier.SEV3),
    ("sev4", SeverityTier.SEV4),
    ("info", SeverityTier.SEV4),
)


class EventNormalizer:
    """Pure normalization. Holds only static rule tables — instances are
    interchangeable."""

    def normalize(self, trigger: RawTrigger) -> NormalizedEvent:
        payload = trigger.payload
        text_blob = " ".join(
            [
                str(payload.get("alert_name", "")),
                str(payload.get("alarm_name", "")),
                str(payload.get("title", "")),
                str(payload.get("type", "")),
                str(payload.get("category", "")),
                str(payload.get("message", "")),
                str(payload.get("severity", "")),
                str(payload.get("priority", "")),
            ]
        ).lower()

        incident_class = self._classify(payload, text_blob)
        severity = self._score_severity(payload, text_blob, incident_class)
        correlation_id = self._derive_correlation_id(trigger, payload)
        fingerprint = self._fingerprint(trigger, payload, incident_class)
        service = self._extract_service(payload)
        environment = self._extract_environment(payload)
        region = self._extract_region(payload)
        metrics = self._extract_metrics(payload)
        indicators = self._extract_indicators(payload, incident_class)
        tags = self._extract_tags(payload)

        enrichment = {
            "classifier_text": text_blob[:512],
            "source": trigger.source.value,
        }

        return NormalizedEvent(
            correlation_id=correlation_id,
            fingerprint=fingerprint,
            source=trigger.source,
            incident_class=incident_class,
            severity=severity,
            received_at=trigger.received_at,
            normalized_at=datetime.now(timezone.utc),
            service=service,
            environment=environment,
            region=region,
            tags=tags,
            metrics=metrics,
            indicators=indicators,
            raw=payload,
            enrichment=enrichment,
        )

    # ------------------------------------------------------------------
    # Rule-based classification.
    # ------------------------------------------------------------------

    def _classify(self, payload: dict, text_blob: str) -> IncidentClass:
        # Explicit upstream type field wins if it maps cleanly.
        for key in ("incident_class", "type", "category", "alert_type"):
            raw = str(payload.get(key, "")).lower().strip()
            if raw and raw in _HINT_TO_CLASS:
                return _HINT_TO_CLASS[raw]

        for hint, cls in _HINT_TO_CLASS.items():
            if hint in text_blob:
                return cls

        # Metric-derived classification as a last resort.
        metrics = payload.get("metrics") or {}
        if isinstance(metrics, dict):
            cpu = self._as_float(metrics.get("cpu_utilization"))
            mem = self._as_float(metrics.get("memory_utilization"))
            err = self._as_float(metrics.get("error_rate"))
            if cpu is not None and cpu >= 90.0:
                return IncidentClass.CPU_SPIKE
            if mem is not None and mem >= 92.0:
                return IncidentClass.MEMORY_PRESSURE
            if err is not None and err >= 0.05:
                return IncidentClass.ELEVATED_ERROR_RATE

        return IncidentClass.UNKNOWN

    def _score_severity(
        self,
        payload: dict,
        text_blob: str,
        incident_class: IncidentClass,
    ) -> SeverityTier:
        # Hard rule: ransomware indicator and active unauthorized access
        # are SEV0 regardless of upstream tagging.
        if incident_class is IncidentClass.RANSOMWARE_INDICATOR:
            return SeverityTier.SEV0
        if incident_class is IncidentClass.UNAUTHORIZED_API_ACCESS:
            return SeverityTier.SEV0

        # CVE severity from CVSS score is authoritative — runs *before*
        # text scanning so an upstream-mistagged "info" CVSS-10 CVE still
        # routes as SEV0. This is the canonical example of why we score
        # severity rather than passing it through.
        cvss = self._as_float(payload.get("cvss_score"))
        if cvss is not None and incident_class is IncidentClass.CVE_VULNERABILITY:
            if cvss >= 9.0:
                return SeverityTier.SEV0
            if cvss >= 7.0:
                return SeverityTier.SEV1
            if cvss >= 4.0:
                return SeverityTier.SEV2
            return SeverityTier.SEV3

        for token, tier in _SEVERITY_FROM_TEXT:
            if token in text_blob:
                return tier

        # Conservative default — never silently SEV0.
        return SeverityTier.SEV3

    # ------------------------------------------------------------------
    # Identity derivation.
    # ------------------------------------------------------------------

    def _derive_correlation_id(self, trigger: RawTrigger, payload: dict) -> str:
        for key in ("correlation_id", "incident_key", "fingerprint", "alarm_arn"):
            value = payload.get(key)
            if value:
                return f"{trigger.source.value}:{value}"
        if trigger.correlation_hint:
            return f"{trigger.source.value}:{trigger.correlation_hint}"
        return f"{trigger.source.value}:{self._fingerprint(trigger, payload, IncidentClass.UNKNOWN)}"

    def _fingerprint(
        self,
        trigger: RawTrigger,
        payload: dict,
        incident_class: IncidentClass,
    ) -> str:
        parts = {
            "src": trigger.source.value,
            "cls": incident_class.value,
            "svc": payload.get("service") or payload.get("service_name"),
            "res": payload.get("resource") or payload.get("arn"),
            "alarm": payload.get("alarm_name") or payload.get("alert_name"),
        }
        raw = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Enrichment helpers.
    # ------------------------------------------------------------------

    def _extract_service(self, payload: dict) -> str | None:
        for key in ("service", "service_name", "app", "workload"):
            value = payload.get(key)
            if value:
                return str(value)
        return None

    def _extract_environment(self, payload: dict):
        env = str(payload.get("environment") or payload.get("env") or "").lower()
        if env in ("prod", "production"):
            return "prod"
        if env in ("staging", "stage", "preprod"):
            return "staging"
        if env in ("dev", "development", "test"):
            return "dev"
        return "unknown"

    def _extract_region(self, payload: dict) -> str | None:
        for key in ("region", "aws_region", "zone"):
            value = payload.get(key)
            if value:
                return str(value)
        return None

    def _extract_metrics(self, payload: dict) -> dict[str, float]:
        out: dict[str, float] = {}
        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            for k, v in metrics.items():
                f = self._as_float(v)
                if f is not None:
                    out[k] = f
        for key in ("cpu", "memory", "error_rate", "latency_ms", "p99_ms"):
            f = self._as_float(payload.get(key))
            if f is not None:
                out.setdefault(key, f)
        return out

    def _extract_indicators(self, payload: dict, incident_class: IncidentClass) -> list[str]:
        indicators = payload.get("indicators") or []
        if not isinstance(indicators, list):
            indicators = [str(indicators)]
        if incident_class is IncidentClass.RANSOMWARE_INDICATOR:
            indicators = list(indicators) + ["mass_file_rename", "extension_drift"]
        return [str(x) for x in indicators]

    def _extract_tags(self, payload: dict) -> dict[str, str]:
        tags = payload.get("tags") or {}
        if isinstance(tags, dict):
            return {str(k): str(v) for k, v in tags.items()}
        return {}

    @staticmethod
    def _as_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
