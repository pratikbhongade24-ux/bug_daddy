import json
import os
import sys
import traceback
from datetime import datetime, timezone


SERVICE_NAME = "KYCService"
SHARED_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SHARED_ROOT not in sys.path:
    sys.path.insert(0, SHARED_ROOT)

from shared.logger import extract_trace_id, get_trace_id, make_logger, set_trace_id

try:
    from shared.persistence import persist_operation, read_verification_history
except Exception as exc:
    _PERSISTENCE_IMPORT_ERROR = str(exc)
    persist_operation = None

    def read_verification_history(customer_id):
        return {"persistence": {"status": "failed", "error": _PERSISTENCE_IMPORT_ERROR}, "items": []}


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
        "db": {"host": os.environ.get("DB_HOST"), "port": os.environ.get("DB_PORT"), "name": os.environ.get("DB_NAME"), "user": os.environ.get("DB_USER")},
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


def normalize_identity(payload):
    identity = {"customerId": payload.get("customerId", "UNKNOWN"), "pan": payload.get("pan"), "aadhaarMasked": payload.get("aadhaarMasked", "XXXX-XXXX-1234")}
    log("normalize_identity", identity)
    return identity


def verify_pan(payload, context, request_id):
    identity = normalize_identity(payload)
    if payload.get("simulateBug") == "pan_none":
        identity["pan"].strip()
    # Bug: kyc_bad_pan — originates in CustomerOnboardingService which omits pan when
    # the lead is created without PAN validation. KYC receives pan=None and crashes here.
    if payload.get("simulateBug") == "kyc_bad_pan":
        pan_from_onboarding = payload.get("pan")   # None — onboarding never set it
        pan_from_onboarding.strip()                # AttributeError: 'NoneType' has no attribute 'strip'
    return response(context, request_id, "verifyPan", payload, {"verification": {"pan": identity["pan"], "status": "VERIFIED", "provider": "mock-pan-registry"}, "message": "PAN verification completed"})


def verify_aadhaar(payload, context, request_id):
    identity = normalize_identity(payload)
    return response(context, request_id, "verifyAadhaar", payload, {"verification": {"aadhaarMasked": identity["aadhaarMasked"], "status": "VERIFIED"}, "message": "Aadhaar verification completed"})


def run_face_match(payload, context, request_id):
    identity = normalize_identity(payload)
    log("run_face_match", {"customerId": identity["customerId"]})
    if payload.get("simulateBug") == "face_threshold":
        # Fixed division by zero error - returning appropriate error response
        return response(context, request_id, "runFaceMatch", payload, {
            "error": "THRESHOLD_ERROR", 
            "message": "Face match threshold simulation triggered"
        })
    return response(context, request_id, "runFaceMatch", payload, {"faceMatch": {"score": 0.93, "result": "MATCHED"}, "message": "Face match run completed"})


def get_kyc_status(payload, context, request_id):
    identity = normalize_identity(payload)
    return response(context, request_id, "getKycStatus", payload, {"status": {"customerId": identity["customerId"], "kycStatus": "APPROVED", "reviewMode": "AUTO"}, "message": "KYC status fetched"})


def get_verification_history(payload, context, request_id):
    identity = normalize_identity(payload)
    return response(
        context,
        request_id,
        "getVerificationHistory",
        payload,
        {
            "history": read_verification_history(identity["customerId"]),
            "message": "KYC verification history fetched",
        },
    )


def health_check(payload, context, request_id):
    return response(context, request_id, "healthCheck", payload, {"message": "KYC service is healthy"})


def route_request(request_id, payload, context):
    if request_id == "verifyPan":
        return verify_pan(payload, context, request_id)
    if request_id == "verifyAadhaar":
        return verify_aadhaar(payload, context, request_id)
    if request_id == "runFaceMatch":
        return run_face_match(payload, context, request_id)
    if request_id == "getKycStatus":
        return get_kyc_status(payload, context, request_id)
    if request_id == "getVerificationHistory":
        return get_verification_history(payload, context, request_id)
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