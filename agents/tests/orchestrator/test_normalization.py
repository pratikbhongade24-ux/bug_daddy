"""Rule-table unit tests for the EventNormalizer.

Each test pins one inference path: text hint, metric threshold, CVSS
override, hard-rule (ransomware/unauthorized API). Together they form an
executable specification of the normalizer's contract."""

from __future__ import annotations

from datetime import UTC, datetime

from agentic_solution.orchestrator.contracts import (
    IncidentClass,
    RawTrigger,
    SeverityTier,
    TriggerSource,
)
from agentic_solution.orchestrator.runtime.normalization import EventNormalizer


def _trigger(source, payload, *, hint=None):
    return RawTrigger(
        source=source,
        received_at=datetime.now(UTC),
        payload=payload,
        correlation_hint=hint,
    )


class TestIncidentClassification:
    def setup_method(self):
        self.n = EventNormalizer()

    def test_explicit_type_field_wins(self):
        event = self.n.normalize(_trigger(
            TriggerSource.MANUAL, {"type": "cve", "cvss_score": 5.0}
        ))
        assert event.incident_class is IncidentClass.CVE_VULNERABILITY

    def test_text_hint_falls_back_to_class(self):
        event = self.n.normalize(_trigger(
            TriggerSource.CLOUDWATCH, {"alarm_name": "rds_connections threshold breached"}
        ))
        assert event.incident_class is IncidentClass.DATABASE_SATURATION

    def test_metric_threshold_classifies_cpu(self):
        event = self.n.normalize(_trigger(
            TriggerSource.PROMETHEUS,
            {"service": "x", "metrics": {"cpu_utilization": 96.0}},
        ))
        assert event.incident_class is IncidentClass.CPU_SPIKE

    def test_metric_threshold_classifies_memory(self):
        event = self.n.normalize(_trigger(
            TriggerSource.PROMETHEUS,
            {"service": "x", "metrics": {"memory_utilization": 94.0}},
        ))
        assert event.incident_class is IncidentClass.MEMORY_PRESSURE

    def test_unknown_when_no_signal(self):
        event = self.n.normalize(_trigger(TriggerSource.MANUAL, {"foo": "bar"}))
        assert event.incident_class is IncidentClass.UNKNOWN


class TestSeverityScoring:
    def setup_method(self):
        self.n = EventNormalizer()

    def test_ransomware_is_always_sev0(self):
        event = self.n.normalize(_trigger(
            TriggerSource.GUARDDUTY,
            {"type": "ransomware", "severity": "low"},
        ))
        assert event.severity is SeverityTier.SEV0

    def test_unauthorized_api_is_always_sev0(self):
        event = self.n.normalize(_trigger(
            TriggerSource.CLOUDWATCH,
            {"type": "unauthorized_api", "severity": "info"},
        ))
        assert event.severity is SeverityTier.SEV0

    def test_cvss_overrides_upstream_text(self):
        """The Log4j case — upstream says info, CVSS says 10.0, we trust
        CVSS. This is the canonical regression test for orchestration
        determinism over upstream sloppiness."""
        event = self.n.normalize(_trigger(
            TriggerSource.SNYK,
            {"type": "cve", "cvss_score": 10.0, "severity": "info"},
        ))
        assert event.severity is SeverityTier.SEV0

    def test_cvss_mid_severity(self):
        event = self.n.normalize(_trigger(
            TriggerSource.SNYK,
            {"type": "cve", "cvss_score": 7.5, "severity": "info"},
        ))
        assert event.severity is SeverityTier.SEV1

    def test_text_token_drives_severity_when_no_overrides(self):
        event = self.n.normalize(_trigger(
            TriggerSource.PAGERDUTY,
            {"title": "checkout p1 outage", "service": "checkout"},
        ))
        assert event.severity is SeverityTier.SEV1

    def test_conservative_default_is_sev3(self):
        event = self.n.normalize(_trigger(
            TriggerSource.MANUAL,
            {"foo": "bar"},
        ))
        assert event.severity is SeverityTier.SEV3


class TestCorrelationAndFingerprint:
    def setup_method(self):
        self.n = EventNormalizer()

    def test_correlation_prefers_explicit_id(self):
        event = self.n.normalize(_trigger(
            TriggerSource.MANUAL,
            {"correlation_id": "X-123"},
            hint="ignored",
        ))
        assert event.correlation_id == "manual:X-123"

    def test_correlation_falls_back_to_hint(self):
        event = self.n.normalize(_trigger(
            TriggerSource.MANUAL,
            {},
            hint="hint-only",
        ))
        assert event.correlation_id == "manual:hint-only"

    def test_correlation_falls_back_to_fingerprint(self):
        event = self.n.normalize(_trigger(TriggerSource.MANUAL, {"foo": "bar"}))
        assert event.correlation_id.startswith("manual:")
        assert len(event.correlation_id) > len("manual:")

    def test_fingerprint_is_stable_across_invocations(self):
        payload = {"service": "x", "type": "cve", "cvss_score": 9.0, "resource": "r"}
        a = self.n.normalize(_trigger(TriggerSource.SNYK, payload))
        b = self.n.normalize(_trigger(TriggerSource.SNYK, payload))
        assert a.fingerprint == b.fingerprint

    def test_fingerprint_differs_across_services(self):
        a = self.n.normalize(_trigger(TriggerSource.SNYK, {"service": "a", "type": "cve"}))
        b = self.n.normalize(_trigger(TriggerSource.SNYK, {"service": "b", "type": "cve"}))
        assert a.fingerprint != b.fingerprint
