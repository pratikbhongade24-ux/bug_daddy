import json
import os
import sys
import traceback
from datetime import datetime, timezone


SERVICE_NAME = "DisbursementService"
SHARED_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SHARED_ROOT not in sys.path:
    sys.path.insert(0, SHARED_ROOT)

from shared.logger import extract_trace_id, get_trace_id, make_logger, set_trace_id

try:
    from shared.persistence import persist_operation, read_disbursement_ledger
except Exception as exc:
    _PERSISTENCE_IMPORT_ERROR = str(exc)
    persist_operation = None

    def read_disbursement_ledger(disbursement_id):
        return {"persistence": {"status": "failed", "error": _PERSISTENCE_IMPORT_ERROR}}


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
    base = {"service": SERVICE_NAME, "requestId": request_id, "operation": operation, "traceId": get_trace_id(), "requestTraceId": trace_id, "timestamp": iso_now(), "db": {"host": os.environ.get("DB_HOST"), "port": os.environ.get("DB_PORT"), "name": os.environ.get("DB_NAME"), "user": os.environ.get("DB_USER")}, "payload": payload}
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


def prepare_disbursement(payload):
    disbursement = {"disbursementId": payload.get("disbursementId", "DISB-001"), "amount": payload.get("amount", 0), "destinationBank": payload.get("destinationBank", "MOCKBANK")}
    log("prepare_disbursement", disbursement)
    return disbursement


def create_disbursement(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    return response(context, request_id, "createDisbursement", payload, {"disbursement": {"disbursementId": disbursement["disbursementId"], "status": "CREATED", "amount": disbursement["amount"]}, "message": "Disbursement created"})


def validate_account(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    # Removed simulateBug code block that could cause IndexError
    return response(context, request_id, "validateAccount", payload, {"accountValidation": {"accountNumberMasked": payload.get("accountNumberMasked", "XXXXXX1234"), "status": "VERIFIED"}, "message": "Beneficiary account validated"})


def release_funds(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    log("release_funds", disbursement)
    # Removed simulateBug code block that caused ZeroDivisionError
    return response(context, request_id, "releaseFunds", payload, {"release": {"utr": payload.get("utr", "UTR-001"), "status": "PROCESSING", "destination": disbursement["destinationBank"]}, "message": "Funds release initiated"})


def get_disbursement_status(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    return response(context, request_id, "getDisbursementStatus", payload, {"status": {"disbursementId": disbursement["disbursementId"], "state": "SUCCESS", "settlementWindow": "T+0"}, "message": "Disbursement status fetched"})


def get_disbursement_ledger(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    return response(
        context,
        request_id,
        "getDisbursementLedger",
        payload,
        {
            "ledger": read_disbursement_ledger(disbursement["disbursementId"]),
            "message": "Disbursement ledger fetched",
        },
    )


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
    if request_id == "getDisbursementLedger":
        return get_disbursement_ledger(payload, context, request_id)
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
        print(f"ERROR {SERVICE_NAME} failed while handling {request_id}: {exc}")
        print(traceback.format_exc())
        raise
