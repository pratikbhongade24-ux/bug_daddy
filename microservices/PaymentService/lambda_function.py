import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from decimal import Decimal


SERVICE_NAME = "PaymentService"
SHARED_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SHARED_ROOT not in sys.path:
    sys.path.insert(0, SHARED_ROOT)

from shared.logger import extract_trace_id, get_trace_id, make_logger, set_trace_id

try:
    from shared.persistence import persist_operation, read_payment_ledger
except Exception as exc:
    _PERSISTENCE_IMPORT_ERROR = str(exc)
    persist_operation = None

    def read_payment_ledger(payment_id):
        return {"persistence": {"status": "failed", "error": _PERSISTENCE_IMPORT_ERROR}}


def iso_now():
    return datetime.now(timezone.utc).isoformat()


log = make_logger(SERVICE_NAME)

SUPPORTED_BANKS = ["HDFC", "ICICI", "AXIS"]


# ---------------------------------------------------------------------------
# Mock bank payment adapters
# ---------------------------------------------------------------------------

def _mock_hdfc_process_payment(payment_id, amount, account_masked=None):
    bank_ref_id = "HDFC" + uuid.uuid4().hex[:10].upper()
    return {
        "bankCode": "HDFC",
        "bankRefId": bank_ref_id,
        "paymentId": payment_id,
        "amount": amount,
        "accountMasked": account_masked or "XXXXXX1234",
        "status": "SUCCESS",
        "settlementWindow": "T+0",
    }


def _mock_icici_process_payment(payment_id, amount, account_masked=None):
    bank_ref_id = "ICICI" + uuid.uuid4().hex[:10].upper()
    return {
        "bankCode": "ICICI",
        "bankRefId": bank_ref_id,
        "paymentId": payment_id,
        "amount": amount,
        "accountMasked": account_masked or "XXXXXX1234",
        "status": "SUCCESS",
        "settlementWindow": "T+1",
    }


def _mock_axis_process_payment(payment_id, amount, account_masked=None):
    bank_ref_id = "AXIS" + uuid.uuid4().hex[:10].upper()
    return {
        "bankCode": "AXIS",
        "bankRefId": bank_ref_id,
        "paymentId": payment_id,
        "amount": amount,
        "accountMasked": account_masked or "XXXXXX1234",
        "status": "SUCCESS",
        "settlementWindow": "T+0",
    }


_PAYMENT_ADAPTERS = {
    "HDFC": _mock_hdfc_process_payment,
    "ICICI": _mock_icici_process_payment,
    "AXIS": _mock_axis_process_payment,
}


# ---------------------------------------------------------------------------
# Mock bank refund adapters
# ---------------------------------------------------------------------------

def _mock_hdfc_process_refund(refund_id, original_payment_id, amount):
    bank_ref_id = "HDFCREF" + uuid.uuid4().hex[:8].upper()
    return {
        "bankCode": "HDFC",
        "bankRefId": bank_ref_id,
        "refundId": refund_id,
        "originalPaymentId": original_payment_id,
        "refundAmount": float(amount),
        "status": "REFUND_INITIATED",
        "tat": "3-5 business days",
    }


def _mock_icici_process_refund(refund_id, original_payment_id, amount):
    bank_ref_id = "ICICREF" + uuid.uuid4().hex[:8].upper()
    return {
        "bankCode": "ICICI",
        "bankRefId": bank_ref_id,
        "refundId": refund_id,
        "originalPaymentId": original_payment_id,
        "refundAmount": float(amount),
        "status": "REFUND_INITIATED",
        "tat": "5-7 business days",
    }


# Bug: AXIS ignores partial refund amounts and processes the original full amount instead.
# The adapter accepts original_amount as a separate parameter, and when provided it uses
# that instead of the requested refund amount — simulating AXIS's broken partial refund flow.
def _mock_axis_process_refund(refund_id, original_payment_id, amount, original_amount=None):
    bank_ref_id = "AXISREF" + uuid.uuid4().hex[:8].upper()
    actual_amount = original_amount if original_amount is not None else amount
    return {
        "bankCode": "AXIS",
        "bankRefId": bank_ref_id,
        "refundId": refund_id,
        "originalPaymentId": original_payment_id,
        "refundAmount": float(actual_amount),
        "requestedRefundAmount": float(amount),
        "status": "REFUND_INITIATED",
        "tat": "2-3 business days",
    }


_REFUND_ADAPTERS = {
    "HDFC": _mock_hdfc_process_refund,
    "ICICI": _mock_icici_process_refund,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def error_response(context, request_id, operation, payload, status_code, error_msg):
    trace_id = getattr(context, "aws_request_id", None)
    body = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "traceId": get_trace_id(),
        "requestTraceId": trace_id,
        "timestamp": iso_now(),
        "payload": payload,
        "error": error_msg,
    }
    return {"statusCode": status_code, "body": json.dumps(body)}


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


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------

def initiate_payment(payload, context, request_id):
    bank_code = payload.get("bankCode", "").upper()
    amount = payload.get("amount")

    if bank_code not in SUPPORTED_BANKS:
        return error_response(context, request_id, "initiatePayment", payload, 400,
                              f"Unsupported bankCode '{bank_code}'. Supported banks: {SUPPORTED_BANKS}")

    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except (TypeError, ValueError):
        return error_response(context, request_id, "initiatePayment", payload, 400,
                              "Invalid or missing 'amount'. Must be a positive number.")

    payment_id = "PAY-" + uuid.uuid4().hex[:12].upper()
    account_masked = payload.get("accountNumberMasked")

    adapter = _PAYMENT_ADAPTERS[bank_code]
    bank_response = adapter(payment_id, amount, account_masked)

    payment = {
        "paymentId": payment_id,
        "status": "INITIATED",
        "amount": amount,
        "bankCode": bank_code,
    }
    return response(context, request_id, "initiatePayment", payload, {
        "payment": payment,
        "bankResponse": bank_response,
        "message": "Payment initiated successfully",
    })


def get_payment_status(payload, context, request_id):
    payment_id = payload.get("paymentId", "PAY-001")
    bank_code = payload.get("bankCode", "HDFC")
    status = {
        "paymentId": payment_id,
        "state": "SUCCESS",
        "bankCode": bank_code,
        "settledAt": iso_now(),
    }
    return response(context, request_id, "getPaymentStatus", payload, {
        "status": status,
        "message": "Payment status fetched",
    })


def process_refund(payload, context, request_id):
    required_fields = ["originalPaymentId", "bankCode", "refundType", "reason", "customerId"]
    refund_type = payload.get("refundType", "").upper()
    if refund_type == "PARTIAL":
        required_fields.append("refundAmount")

    missing = [f for f in required_fields if not payload.get(f)]
    if missing:
        return error_response(context, request_id, "processRefund", payload, 400,
                              f"Missing required fields: {missing}")

    bank_code = payload["bankCode"].upper()
    original_payment_id = payload["originalPaymentId"]
    reason = payload["reason"]
    remarks = payload.get("remarks", "")
    notify_customer = payload.get("notifyCustomer", True)

    # Prevent partial refunds for AXIS bank due to API limitation
    if bank_code == "AXIS" and refund_type == "PARTIAL":
        return error_response(context, request_id, "processRefund", payload, 400,
                              "AXIS bank does not support partial refunds. Please use a different bank or process a full refund.")

    if refund_type == "PARTIAL":
        try:
            refund_amount = float(payload["refundAmount"])
            if refund_amount <= 0:
                raise ValueError("refundAmount must be positive")
        except (TypeError, ValueError):
            return error_response(context, request_id, "processRefund", payload, 400,
                                  "Invalid 'refundAmount'. Must be a positive number.")
    else:
        refund_amount = float(payload.get("amount") or 0)

    refund_id = "REF-" + uuid.uuid4().hex[:12].upper()

    if bank_code in _REFUND_ADAPTERS:
        bank_response = _REFUND_ADAPTERS[bank_code](refund_id, original_payment_id, refund_amount)
    elif bank_code == "AXIS":
        bank_response = _mock_axis_process_refund(refund_id, original_payment_id, refund_amount)
    else:
        return error_response(context, request_id, "processRefund", payload, 400,
                              f"Unsupported bankCode '{bank_code}'. Supported banks: {SUPPORTED_BANKS}")

    refund = {
        "refundId": refund_id,
        "originalPaymentId": original_payment_id,
        "refundType": refund_type,
        "refundAmount": refund_amount,
        "status": "INITIATED",
        "bankCode": bank_code,
        "reason": reason,
        "remarks": remarks,
        "notifyCustomer": notify_customer,
    }
    return response(context, request_id, "processRefund", payload, {
        "refund": refund,
        "bankResponse": bank_response,
        "message": "Refund initiated successfully",
    })


def get_refund_status(payload, context, request_id):
    refund_id = payload.get("refundId", "REF-001")
    status = {
        "refundId": refund_id,
        "state": "PROCESSED",
        "creditedAt": iso_now(),
    }
    return response(context, request_id, "getRefundStatus", payload, {
        "status": status,
        "message": "Refund status fetched",
    })


def get_payment_ledger(payload, context, request_id):
    payment_id = payload.get("paymentId", "PAY-001")
    return response(context, request_id, "getPaymentLedger", payload, {
        "ledger": read_payment_ledger(payment_id),
        "message": "Payment ledger fetched",
    })


def health_check(payload, context, request_id):
    return response(context, request_id, "healthCheck", payload, {
        "message": "Payment service is healthy",
        "supportedBanks": SUPPORTED_BANKS,
    })


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def route_request(request_id, payload, context):
    if request_id == "initiatePayment":
        return initiate_payment(payload, context, request_id)
    if request_id == "getPaymentStatus":
        return get_payment_status(payload, context, request_id)
    if request_id == "processRefund":
        return process_refund(payload, context, request_id)
    if request_id == "getRefundStatus":
        return get_refund_status(payload, context, request_id)
    if request_id == "getPaymentLedger":
        return get_payment_ledger(payload, context, request_id)
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