import json
import os
import traceback
from datetime import datetime, timezone


SERVICE_NAME = "SupportService"


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def log(stage, payload):
    print(json.dumps({"service": SERVICE_NAME, "stage": stage, "payload": payload}))


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
    base = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "requestTraceId": getattr(context, "aws_request_id", None),
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
    return {"statusCode": 200, "body": json.dumps(base)}


def error_response(context, request_id, operation, payload, error_dict, extra=None):
    """Return a structured error payload with HTTP 500.
    error_dict should contain at least ``code`` and ``message`` keys.
    """
    base = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "requestTraceId": getattr(context, "aws_request_id", None),
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
    if payload.get("simulateBug") == "queue_failure":
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
    if payload.get("simulateBug") == "comment_shape":
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
    return health_check(payload, context, request_id)


def lambda_handler(event, context):
    request_id, payload = parse_request(event)
    log("request_received", {"requestId": request_id, "payload": payload})
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
