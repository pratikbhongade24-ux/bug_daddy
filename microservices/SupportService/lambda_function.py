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
            "user": os.environ.get("DB_USER")
        },
        "payload": payload
    }
    if extra:
        base.update(extra)
    return {"statusCode": 200, "body": json.dumps(base)}

def error_response(context, request_id, operation, error_msg, status_code=500):
    """Return a structured error payload."""
    body = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "error": error_msg,
        "timestamp": iso_now(),
        "requestTraceId": getattr(context, "aws_request_id", None)
    }
    return {"statusCode": status_code, "body": json.dumps(body)}

def load_ticket(payload):
    ticket = {
        "ticketId": payload.get("ticketId", "SUP-001"),
        "priority": payload.get("priority", "medium"),
        "assignedQueue": payload.get("assignedQueue", "loan-ops")
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
        {"ticket": {"ticketId": ticket["ticketId"], "priority": ticket["priority"], "status": "OPEN"},
         "message": "Support ticket created"}
    )

def assign_ticket(payload, context, request_id):
    ticket = load_ticket(payload)
    # Guard simulated bug behind feature flag
    simulate = payload.get("simulateBug")
    enable_sim = os.getenv("ENABLE_SIMULATED_BUGS", "false").lower() == "true"
    if simulate == "queue_failure" and enable_sim:
        # Simulated failure – raise to be caught by lambda_handler
        raise RuntimeError(f"queue assignment failed for {ticket['assignedQueue']}")
    # Normal path (or simulation disabled)
    return response(
        context,
        request_id,
        "assignTicket",
        payload,
        {"assignment": {"ticketId": ticket["ticketId"],
                        "assignedQueue": ticket["assignedQueue"],
                        "status": "ASSIGNED"},
         "message": "Support ticket assigned"}
    )

def update_ticket(payload, context, request_id):
    ticket = load_ticket(payload)
    comments = payload.get("comments", [])
    log("update_ticket", {"ticketId": ticket["ticketId"], "commentCount": len(comments)})
    if payload.get("simulateBug") == "comment_shape":
        # This will raise a TypeError intentionally when simulation is enabled
        comments["latest"]
    return response(
        context,
        request_id,
        "updateTicket",
        payload,
        {"update": {"ticketId": ticket["ticketId"],
                    "status": payload.get("status", "IN_PROGRESS"),
                    "commentCount": len(comments)},
         "message": "Support ticket updated"}
    )

def get_ticket_status(payload, context, request_id):
    ticket = load_ticket(payload)
    return response(
        context,
        request_id,
        "getTicketStatus",
        payload,
        {"status": {"ticketId": ticket["ticketId"],
                    "currentState": "RESOLVED",
                    "resolutionCode": "MOCK_RESOLUTION"},
         "message": "Support ticket status fetched"}
    )

def health_check(payload, context, request_id):
    return response(context, request_id, "healthCheck", payload, {"message": "Support service is healthy"})

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
        err_msg = f"{SERVICE_NAME} failed while handling {request_id}: {exc}"
        print(f"ERROR {err_msg}")
        print(traceback.format_exc())
        return error_response(context, request_id, request_id, str(exc))
