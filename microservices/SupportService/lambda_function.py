import json
import os
import sys
import traceback
from datetime import datetime, timezone


SERVICE_NAME = "SupportService"
SHARED_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SHARED_ROOT not in sys.path:
    sys.path.insert(0, SHARED_ROOT)

from shared.logger import extract_trace_id, get_trace_id, make_logger, set_trace_id

try:
    from shared.persistence import persist_operation, read_ticket_timeline
except Exception as exc:
    _PERSISTENCE_IMPORT_ERROR = str(exc)
    persist_operation = None

    def read_ticket_timeline(ticket_id):
        return {"persistence": {"status": "failed", "error": _PERSISTENCE_IMPORT_ERROR}, "events": []}


def iso_now():
    return datetime.now(timezone.utc).isoformat()


log = make_logger(SERVICE_NAME)


def parse_request(event):
    body = event.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = {"rawBody": body}
    if isinstance(body, dict):
        payload = body
    elif isinstance(event, dict):
        payload = {key: value for key, value in event.items() if key != "body"}
    else:
        payload = {}
    return payload.get("requestId") or "healthCheck", payload


def response(context, request_id, operation, payload, extra=None):
    trace_id = getattr(context, "aws_request_id", None)
    base = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "traceId": get_trace_id(),
        "requestTraceId": trace_id,
        "timestamp": iso_now(),
        "db": {
            "host": os.environ.get("DB_HOST"),
            "port": os.environ.get("DB_PORT"),
            "name": os.environ.get("DB_NAME"),
            "user": os.environ.get("DB_USER"),
        },
        "payload": payload,
    }
    if extra:
        base.update(extra)
    if persist_operation:
        base["persistence"] = persist_operation(
            service_name=SERVICE_NAME,
            operation=operation,
            request_id=request_id,
            trace_id=trace_id,
            payload=payload,
            response_payload=extra or {},
        )
    return {"statusCode": 200, "body": json.dumps(base)}


def error_response(context, request_id, operation, payload, error_dict, extra=None):
    """Return a structured error payload with HTTP 500.
    error_dict should contain at least ``code`` and ``message`` keys.
    """
    trace_id = getattr(context, "aws_request_id", None)
    base = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "traceId": get_trace_id(),
        "requestTraceId": trace_id,
        "timestamp": iso_now(),
        "db": {
            "host": os.environ.get("DB_HOST"),
            "port": os.environ.get("DB_PORT"),
            "name": os.environ.get("DB_NAME"),
            "user": os.environ.get("DB_USER"),
        },
        "payload": payload,
        "error": error_dict,
    }
    if extra:
        base.update(extra)
    if persist_operation:
        base["persistence"] = persist_operation(
            service_name=SERVICE_NAME,
            operation=operation,
            request_id=request_id,
            trace_id=trace_id,
            payload=payload,
            response_payload=extra or {},
            status="FAILED",
            error_message=error_dict.get("message"),
        )
    return {"statusCode": 500, "body": json.dumps(base)}


def load_ticket(payload):
    ticket = {
        "ticketId": payload.get("ticketId", "SUP-001"),
        "priority": payload.get("priority", "medium"),
        "assignedQueue": payload.get("assignedQueue", "loan-ops"),
    }
    log("load_ticket", ticket)
    return ticket


def create_ticket(payload, context, request_id):
    ticket = load_ticket(payload)
    return response(
        context,
        request_id,
        "createTicket",
        payload,
        {
            "ticket": {
                "ticketId": ticket["ticketId"],
                "priority": ticket["priority"],
                "status": "OPEN",
            },
            "message": "Support ticket created",
        },
    )


def assign_ticket(payload, context, request_id):
    ticket = load_ticket(payload)
    # Only simulate errors in non-production environments
    if os.environ.get("ENVIRONMENT") != "production" and payload.get("simulateBug") == "queue_failure":
        # Return a controlled error response instead of raising an exception
        err = {
            "code": "QUEUE_ASSIGNMENT_FAILED",
            "message": f"queue assignment failed for {ticket['assignedQueue']}",
            "queue": ticket["assignedQueue"],
        }
        return error_response(context, request_id, "assignTicket", payload, err)
    return response(
        context,
        request_id,
        "assignTicket",
        payload,
        {
            "assignment": {
                "ticketId": ticket["ticketId"],
                "assignedQueue": ticket["assignedQueue"],
                "status": "ASSIGNED",
            },
            "message": "Support ticket assigned",
        },
    )


def update_ticket(payload, context, request_id):
    ticket = load_ticket(payload)
    comments = payload.get("comments", [])
    log("update_ticket", {"ticketId": ticket["ticketId"], "commentCount": len(comments)})
    # Only simulate errors in non-production environments
    if os.environ.get("ENVIRONMENT") != "production" and payload.get("simulateBug") == "comment_shape":
        comments["latest"]  # This will raise a TypeError intentionally for testing
    return response(
        context,
        request_id,
        "updateTicket",
        payload,
        {
            "update": {
                "ticketId": ticket["ticketId"],
                "status": payload.get("status", "IN_PROGRESS"),
                "commentCount": len(comments),
            },
            "message": "Support ticket updated",
        },
    )


def get_ticket_status(payload, context, request_id):
    ticket = load_ticket(payload)
    return response(
        context,
        request_id,
        "getTicketStatus",
        payload,
        {
            "status": {
                "ticketId": ticket["ticketId"],
                "currentState": "RESOLVED",
                "resolutionCode": "MOCK_RESOLUTION",
            },
            "message": "Support ticket status fetched",
        },
    )


def get_ticket_timeline(payload, context, request_id):
    ticket = load_ticket(payload)
    return response(
        context,
        request_id,
        "getTicketTimeline",
        payload,
        {
            "timeline": read_ticket_timeline(ticket["ticketId"]),
            "message": "Support ticket timeline fetched",
        },
    )


def health_check(payload, context, request_id):
    return response(
        context,
        request_id,
        "healthCheck",
        payload,
        {"message": "Support service is healthy"},
    )


def route_request(request_id, payload, context):
    if request_id == "createTicket":
        return create_ticket(payload, context, request_id)
    if request_id == "assignTicket":
        return assign_ticket(payload, context, request_id)
    if request_id == "updateTicket":
        return update_ticket(payload, context, request_id)
    if request_id == "getTicketStatus":
        return get_ticket_status(payload, context, request_id)
    if request_id == "getTicketTimeline":
        return get_ticket_timeline(payload, context, request_id)
    return health_check(payload, context, request_id)


def lambda_handler(event, context):
    trace_id = extract_trace_id(event)
    set_trace_id(trace_id)
    request_id, payload = parse_request(event)
    log("request_received", {"requestId": request_id, "traceId": trace_id, "payload": payload})
    try:
        result = route_request(request_id, payload, context)
        log("request_completed", {"requestId": request_id})
        return result
    except Exception as exc:
        # Log the error and return a structured error response instead of bubbling up
        print(f"ERROR {SERVICE_NAME} failed while handling {request_id}: {exc}")
        print(traceback.format_exc())
        err = {"code": "INTERNAL_SERVER_ERROR", "message": str(exc)}
        return error_response(context, request_id, request_id, payload, err)