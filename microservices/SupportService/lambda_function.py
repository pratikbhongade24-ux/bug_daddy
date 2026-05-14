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


def error_response(context, request_id, operation, message, status_code=400, details=None):
    """Return a consistent error payload.

    Args:
        context: Lambda context (for requestTraceId).
        request_id: The incoming request identifier.
        operation: The operation being performed.
        message: Human‑readable error message.
        status_code: HTTP status code to return (default 400).
        details: Optional dict with additional debugging info.
    """
    err = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "requestTraceId": getattr(context, "aws_request_id", None),
        "timestamp": iso_now(),
        "error": {"message": message},
    }
    if details:
        err["error"]["details"] = details
    return {"statusCode": status_code, "body": json.dumps(err)}


def validate_payload(request_id, payload):
    """Basic validation for required fields.

    Returns:
        (bool, str) – (is_valid, error_message)
    """
    ticket_ops = {"createTicket", "assignTicket", "updateTicket", "getTicketStatus"}
    if request_id in ticket_ops:
        if not payload.get("ticketId"):
            return False, "Missing required field 'ticketId'"
    return True, ""


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
        return error_response(
            context,
            request_id,
            "assignTicket",
            "Queue assignment failed",
            status_code=500,
            details={"queue": ticket["assignedQueue"]},
        )
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
        if isinstance(comments, dict):
            latest = comments.get("latest")
        elif isinstance(comments, list):
            latest = comments[-1] if comments else None
        else:
            latest = None
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
    is_valid, err_msg = validate_payload(request_id, payload)
    if not is_valid:
        return error_response(context, request_id, request_id, err_msg, status_code=400)
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
        print(f"ERROR {SERVICE_NAME} failed while handling {request_id}: {exc}")
        print(traceback.format_exc())
        return error_response(context, request_id, request_id, "Internal server error", status_code=500, details={"exception": str(exc)})
