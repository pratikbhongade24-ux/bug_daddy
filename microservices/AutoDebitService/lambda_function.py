import json
import os
import traceback
from datetime import datetime, timezone


SERVICE_NAME = "AutoDebitService"


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
    base = {"service": SERVICE_NAME, "requestId": request_id, "operation": operation, "requestTraceId": getattr(context, "aws_request_id", None), "timestamp": iso_now(), "db": {"host": os.environ.get("DB_HOST"), "port": os.environ.get("DB_PORT"), "name": os.environ.get("DB_NAME"), "user": os.environ.get("DB_USER")}, "payload": payload}
    if extra:
        base.update(extra)
    return {"statusCode": 200, "body": json.dumps(base)}


def load_mandate(payload):
    mandate = {"mandateId": payload.get("mandateId", "MANDATE-001"), "bankCode": payload.get("bankCode", "MOCKBANK"), "amount": payload.get("amount", 0)}
    log("load_mandate", mandate)
    return mandate


def register_mandate(payload, context, request_id):
    mandate = load_mandate(payload)
    return response(context, request_id, "registerMandate", payload, {"mandate": {"mandateId": mandate["mandateId"], "status": "REGISTERED", "bankCode": mandate["bankCode"]}, "message": "Mandate registration completed"})


def validate_mandate(payload, context, request_id):
    mandate = load_mandate(payload)
    if payload.get("simulateBug") == "mandate_lookup":
        [][1]
    return response(context, request_id, "validateMandate", payload, {"validation": {"mandateId": mandate["mandateId"], "status": "VALID", "retryEligible": False}, "message": "Mandate validation completed"})


def execute_debit(payload, context, request_id):
    mandate = load_mandate(payload)
    log("execute_debit", mandate)
    # Fixed TypeError: ensure numeric addition when simulateBug flag is used.
    if payload.get("simulateBug") == "execute_type":
        # Previously attempted string concatenation with an int, causing a TypeError.
        # Perform a safe numeric addition instead.
        mandate["amount"] = mandate["amount"] + 100
    return response(context, request_id, "executeDebit", payload, {"debit": {"transactionId": payload.get("transactionId", "DEBIT-1001"), "status": "SCHEDULED", "amount": mandate["amount"]}, "message": "Debit execution scheduled"})


def get_mandate_status(payload, context, request_id):
    mandate = load_mandate(payload)
    return response(context, request_id, "getMandateStatus", payload, {"status": {"mandateId": mandate["mandateId"], "state": "ACTIVE", "lastExecution": "SUCCESS"}, "message": "Mandate status fetched"})


def health_check(payload, context, request_id):
    return response(context, request_id, "healthCheck", payload, {"message": "Auto debit service is healthy"})


def route_request(request_id, payload, context):
    if request_id == "registerMandate":
        return register_mandate(payload, context, request_id)
    if request_id == "validateMandate":
        return validate_mandate(payload, context, request_id)
    if request_id == "executeDebit":
        return execute_debit(payload, context, request_id)
    if request_id == "getMandateStatus":
        return get_mandate_status(payload, context, request_id)
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
        raise
