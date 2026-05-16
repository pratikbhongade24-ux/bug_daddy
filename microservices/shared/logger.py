"""
Distributed trace logger for all Lambda microservices.

Usage in each service:
    from shared.logger import extract_trace_id, set_trace_id, get_trace_id, make_logger

    log = make_logger(SERVICE_NAME)   # replaces the local log() function

    def lambda_handler(event, context):
        trace_id = extract_trace_id(event)
        set_trace_id(trace_id)
        log("request_received", {"requestId": ..., "traceId": trace_id})
        ...

Trace ID propagation:
    - Inbound:  read from the `X-Trace-ID` HTTP header (API Gateway forwards headers
                under `event["headers"]`).  Falls back to a fresh UUID v4.
    - Outbound: when this service calls another service, include the header:
                  headers = {"X-Trace-ID": get_trace_id(), ...}
"""

import json
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

# One ContextVar per Lambda worker process.  Each invocation sets its own value
# before any business logic runs, so concurrent executions are isolated.
_TRACE_ID_VAR: ContextVar[str] = ContextVar("trace_id", default="")

TRACE_ID_HEADER = "x-trace-id"  # lower-cased; API Gateway normalises header names


def get_trace_id() -> str:
    """Return the trace ID bound to the current execution context."""
    return _TRACE_ID_VAR.get()


def set_trace_id(trace_id: str) -> None:
    """Bind a trace ID to the current execution context."""
    _TRACE_ID_VAR.set(trace_id)


def extract_trace_id(event: dict) -> str:
    """Extract X-Trace-ID from a Lambda event's HTTP headers.

    Checks (in order):
        1. ``event["headers"]["x-trace-id"]``           (API Gateway v1/v2 lower-case)
        2. ``event["headers"]["X-Trace-ID"]``           (direct invocation / tests)
        3. Generates a new UUID v4 when none is found.
    """
    headers: dict = event.get("headers") or {}
    trace_id = (
        headers.get("x-trace-id")
        or headers.get("X-Trace-ID")
        or ""
    ).strip()
    return trace_id if trace_id else str(uuid.uuid4())


def make_logger(service_name: str):
    """Return a ``log(stage, payload)`` function pre-bound to *service_name*.

    Every log line is a single JSON object printed to stdout so CloudWatch
    Logs Insights (and any log aggregator) can filter by ``traceId``.

    Example output::

        {"traceId": "abc-123", "service": "KYCService",
         "stage": "request_received", "timestamp": "2026-05-17T10:00:00+00:00",
         "payload": {"requestId": "verifyPan", ...}}
    """
    def _log(stage: str, payload) -> None:
        record = {
            "traceId": get_trace_id(),
            "service": service_name,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        print(json.dumps(record, default=str))

    return _log
