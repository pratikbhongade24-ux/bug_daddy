import json
import os
import sys
import traceback
from datetime import datetime, timezone


SERVICE_NAME = "CustomerOnboardingService"
SHARED_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SHARED_ROOT not in sys.path:
    sys.path.insert(0, SHARED_ROOT)

from shared.logger import extract_trace_id, get_trace_id, make_logger, set_trace_id

try:
    from shared.persistence import persist_operation, read_customer_360
except Exception as exc:
    _PERSISTENCE_IMPORT_ERROR = str(exc)
    persist_operation = None

    def read_customer_360(customer_id):
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


def load_customer(payload):
    customer_id = payload.get("customerId", "UNKNOWN")
    profile = {
        "customerId": customer_id,
        "name": payload.get("name", "Test Customer"),
        "riskBand": payload.get("riskBand", "B"),
        "source": payload.get("source", "web"),
    }
    log("load_customer", profile)
    return profile


def run_risk_checks(profile, payload):
    log("run_risk_checks", {"customerId": profile["customerId"]})
    if payload.get("simulateBug") == "risk_division":
        denominator = int(payload.get("riskDenominator", 0))
        # Handle division by zero case
        if denominator == 0:
            log("zero_division_prevented", {"customerId": profile["customerId"], "riskDenominator": denominator})
            # Return a default risk score when denominator is zero
            return {"riskScore": 0, "message": "Risk score could not be calculated due to zero denominator"}
        return 100 / denominator
    return {"kycScore": 82, "fraudScore": 11, "bureauScore": 741}


def persist_lead(profile, scores, payload):
    lead = {
        "leadId": f"LEAD-{profile['customerId']}",
        "stage": "CREATED",
        "source": profile["source"],
        "scores": scores,
    }
    log("persist_lead", lead)
    if payload.get("simulateBug") == "lead_key_error":
        lead["missingBucket"]["path"] = "boom"
    return lead


def validate_customer_profile(payload, context, request_id):
    profile = load_customer(payload)
    result = {
        "validation": {
            "panPresent": bool(payload.get("pan")),
            "mobilePresent": bool(payload.get("mobile")),
            "emailPresent": bool(payload.get("email")),
        },
        "message": "Customer profile validation completed",
        "profile": profile,
    }
    return response(context, request_id, "validateCustomerProfile", payload, result)


def create_lead(payload, context, request_id):
    profile = load_customer(payload)
    scores = run_risk_checks(profile, payload)
    lead = persist_lead(profile, scores, payload)
    return response(
        context,
        request_id,
        "createLead",
        payload,
        {"lead": lead, "message": "Lead created in onboarding pipeline"},
    )


def submit_onboarding(payload, context, request_id):
    profile = load_customer(payload)
    documents = payload.get("documents", [])
    log("submit_onboarding", {"customerId": profile["customerId"], "documents": documents})
    if payload.get("simulateBug") == "document_type":
        len(documents["pan"])
    return response(
        context,
        request_id,
        "submitOnboarding",
        payload,
        {
            "journey": {
                "status": "SUBMITTED",
                "nextStep": "KYCService",
                "documentsReceived": documents,
            },
            "message": "Onboarding submission accepted",
        },
    )


def get_onboarding_status(payload, context, request_id):
    profile = load_customer(payload)
    return response(
        context,
        request_id,
        "getOnboardingStatus",
        payload,
        {
            "status": {
                "customerId": profile["customerId"],
                "applicationStatus": "IN_REVIEW",
                "assignedService": "SupportService",
            },
            "message": "Onboarding status fetched",
        },
    )


def get_customer_360(payload, context, request_id):
    profile = load_customer(payload)
    return response(
        context,
        request_id,
        "getCustomer360",
        payload,
        {
            "customer360": read_customer_360(profile["customerId"]),
            "message": "Customer 360 fetched from persisted microservice tables",
        },
    )


def health_check(payload, context, request_id):
    log("health_check", {"requestId": request_id})
    return response(
        context, request_id, "healthCheck", payload, {"message": "Customer onboarding service is healthy"}
    )


def route_request(request_id, payload, context):
    if request_id == "validateCustomerProfile":
        return validate_customer_profile(payload, context, request_id)
    if request_id == "createLead":
        return create_lead(payload, context, request_id)
    if request_id == "submitOnboarding":
        return submit_onboarding(payload, context, request_id)
    if request_id == "getOnboardingStatus":
        return get_onboarding_status(payload, context, request_id)
    if request_id == "getCustomer360":
        return get_customer_360(payload, context, request_id)
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