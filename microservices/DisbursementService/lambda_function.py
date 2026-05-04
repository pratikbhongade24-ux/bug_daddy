import json
import os
import traceback
from datetime import datetime, timezone

SERVICE_NAME = "DisbursementService"


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def log(stage, payload):
    print(json.dumps({"service": SERVICE_NAME, "stage": stage, "payload": payload}))


def error_response(context, request_id, operation, error_code, message, status_code=400):
    """Return a consistent error JSON payload.
    Args:
        context: Lambda context (for requestTraceId)
        request_id: The logical request identifier (e.g., createDisbursement)
        operation: The operation being performed when the error occurred
        error_code: Short string identifier for the error type
        message: Human‑readable description
        status_code: HTTP status code to return (default 400)
    """
    base = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "requestTraceId": getattr(context, "aws_request_id", None),
        "timestamp": iso_now(),
        "error": {"code": error_code, "message": message},
        "payload": {}
    }
    return {"statusCode": status_code, "body": json.dumps(base)}


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


def prepare_disbursement(payload):
    # Basic validation – ensure required fields exist and are of correct type
    disbursement_id = payload.get("disbursementId")
    amount = payload.get("amount")
    if disbursement_id is None or not isinstance(disbursement_id, str):
        raise ValueError("'disbursementId' is required and must be a string")
    if amount is None or not isinstance(amount, (int, float)):
        raise ValueError("'amount' is required and must be a number")
    disbursement = {
        "disbursementId": disbursement_id,
        "amount": amount,
        "destinationBank": payload.get("destinationBank", "MOCKBANK")
    }
    log("prepare_disbursement", disbursement)
    return disbursement


def create_disbursement(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    return response(context, request_id, "createDisbursement", payload, {
        "disbursement": {
            "disbursementId": disbursement["disbursementId"],
            "status": "CREATED",
            "amount": disbursement["amount"]
        },
        "message": "Disbursement created"
    })


def validate_account(payload, context, request_id):
    try:
        disbursement = prepare_disbursement(payload)
        if payload.get("simulateBug") == "account_mask":
            # This line previously raised IndexError; guard it
            payload["accountNumberMasked"].split("-")[10]
        return response(context, request_id, "validateAccount", payload, {
            "accountValidation": {
                "accountNumberMasked": payload.get("accountNumberMasked", "XXXXXX1234"),
                "status": "VERIFIED"
            },
            "message": "Beneficiary account validated"
        })
    except Exception as exc:
        log("validate_account_error", {"error": str(exc)})
        return error_response(context, request_id, "validateAccount", "VALIDATION_ERROR", str(exc))


def release_funds(payload, context, request_id):
    try:
        disbursement = prepare_disbursement(payload)
        log("release_funds", disbursement)
        if payload.get("simulateBug") == "release_zero":
            # Previously caused ZeroDivisionError; guard it
            _ = disbursement["amount"] / 0
        return response(context, request_id, "releaseFunds", payload, {
            "release": {
                "utr": payload.get("utr", "UTR-001"),
                "status": "PROCESSING",
                "destination": disbursement["destinationBank"]
            },
            "message": "Funds release initiated"
        })
    except Exception as exc:
        log("release_funds_error", {"error": str(exc)})
        return error_response(context, request_id, "releaseFunds", "RELEASE_ERROR", str(exc))


def get_disbursement_status(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    return response(context, request_id, "getDisbursementStatus", payload, {
        "status": {
            "disbursementId": disbursement["disbursementId"],
            "state": "SUCCESS",
            "settlementWindow": "T+0"
        },
        "message": "Disbursement status fetched"
    })


def health_check(payload, context, request_id):
    return response(context, request_id, "healthCheck", payload, {"message": "Disbursement service is healthy"})


def route_request(request_id, payload, context):
    if request_id == "createDisbursement":
        return create_disbursement(payload, context, request_id)
    if request_id == "validateAccount":
        return validate_account(payload, context, request_id)
    if request_id == "releaseFunds":
        return release_funds(payload, context, request_id)
    if request_id == "getDisbursementStatus":
        return get_disbursement_status(payload, context, request_id)
    return health_check(payload, context, request_id)


def lambda_handler(event, context):
    request_id, payload = parse_request(event)
    log("request_received", {"requestId": request_id, "payload": payload})
    try:
        result = route_request(request_id, payload, context)
        log("request_completed", {"requestId": request_id})
        return result
    except Exception as exc:
        # Unexpected errors – return a generic 500 error payload
        log("unhandled_error", {"error": str(exc)})
        return error_response(context, request_id, request_id, "UNHANDLED_ERROR", str(exc), status_code=500)
