import json
import os
import traceback
from datetime import datetime, timezone


SERVICE_NAME = "KYCService"


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
        "db": {"host": os.environ.get("DB_HOST"), "port": os.environ.get("DB_PORT"), "name": os.environ.get("DB_NAME"), "user": os.environ.get("DB_USER")},
        "payload": payload,
    }
    if extra:
        base.update(extra)
    return {"statusCode": 200, "body": json.dumps(base)}


def normalize_identity(payload):
    identity = {"customerId": payload.get("customerId", "UNKNOWN"), "pan": payload.get("pan"), "aadhaarMasked": payload.get("aadhaarMasked", "XXXX-XXXX-1234")}
    log("normalize_identity", identity)
    return identity


def verify_pan(payload, context, request_id):
    identity = normalize_identity(payload)
    if payload.get("simulateBug") == "pan_none":
        identity["pan"].strip()
    return response(context, request_id, "verifyPan", payload, {"verification": {"pan": identity["pan"], "status": "VERIFIED", "provider": "mock-pan-registry"}, "message": "PAN verification completed"})


def verify_aadhaar(payload, context, request_id):
    identity = normalize_identity(payload)
    return response(context, request_id, "verifyAadhaar", payload, {"verification": {"aadhaarMasked": identity["aadhaarMasked"], "status": "VERIFIED"}, "message": "Aadhaar verification completed"})


def run_face_match(payload, context, request_id):
    """
    Perform face match operation.

    If `simulateBug` flag is set to "face_threshold", we simulate a low confidence
    score instead of raising an exception. This allows testing of downstream
    handling without crashing the Lambda.
    """
    identity = normalize_identity(payload)
    log("run_face_match", {"customerId": identity["customerId"]})

    # Default successful score
    score = 0.93

    # Simulated bug path – return a low confidence score safely
    if payload.get("simulateBug") == "face_threshold":
        # Example low score below typical acceptance threshold
        score = 0.45

    return response(
        context,
        request_id,
        "runFaceMatch",
        payload,
        {"faceMatch": {"score": score, "result": "MATCHED"},
         "message": "Face match run completed"}
    )


def get_kyc_status(payload, context, request_id):
    identity = normalize_identity(payload)
    return response(context, request_id, "getKycStatus", payload, {"status": {"customerId": identity["customerId"], "kycStatus": "APPROVED", "reviewMode": "AUTO"}, "message": "KYC status fetched"})


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