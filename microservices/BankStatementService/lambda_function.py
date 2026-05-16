import json
import os
import traceback
from datetime import datetime, timezone

SERVICE_NAME = "BankStatementService"


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def log(stage, payload):
    print(json.dumps({"service": SERVICE_NAME, "stage": stage, "payload": payload}))


def safe_int(value, default=3):
    """Convert value to int safely, falling back to default on failure."""
    try:
        return int(value)
    except Exception:
        log("warning", {"message": f"Invalid int conversion for pages='{value}', using default {default}"})
        return default


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


def error_response(context, request_id, exc):
    err_body = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "error": str(exc),
        "timestamp": iso_now(),
    }
    return {"statusCode": 400, "body": json.dumps(err_body)}


def validate_simulate_bug(flag):
    allowed = {"negative_pages", "amount_cast", "missing_bucket", None}
    if flag not in allowed:
        raise ValueError(f"Invalid simulateBug flag: {flag}")


def parse_statement(payload):
    # Validate simulateBug flag early
    validate_simulate_bug(payload.get("simulateBug"))
    pages = safe_int(payload.get("pages", 3), default=3)
    statement = {"statementId": payload.get("statementId", "STM-001"), "pages": pages}
    log("parse_statement", statement)
    if payload.get("simulateBug") == "negative_pages":
        # This will raise IndexError intentionally for the simulated bug
        return list(range(pages))[10]
    return statement


def build_transactions(statement, payload):
    transactions = [
        {"txnId": "TXN-1001", "amount": 1250, "type": "credit"},
        {"txnId": "TXN-1002", "amount": 480, "type": "debit"},
        {"txnId": "TXN-1003", "amount": 2750, "type": "credit"},
    ]
    log("build_transactions", {"statementId": statement["statementId"], "count": len(transactions)})
    if payload.get("simulateBug") == "amount_cast":
        try:
            int("not-a-number")
        except Exception as e:
            raise ValueError("Simulated bug 'amount_cast' triggered invalid int conversion") from e
    return transactions


def upload_statement(payload, context, request_id):
    statement = parse_statement(payload)
    return response(context, request_id, "uploadStatement", payload, {"upload": {"statementId": statement["statementId"], "status": "UPLOADED", "pages": statement["pages"]}, "message": "Statement uploaded to mock storage"})


def extract_transactions(payload, context, request_id):
    statement = parse_statement(payload)
    transactions = build_transactions(statement, payload)
    return response(context, request_id, "extractTransactions", payload, {"transactions": transactions, "message": "Transactions extracted from statement"})


def summarize_cashflow(payload, context, request_id):
    statement = parse_statement(payload)
    transactions = build_transactions(statement, payload)
    credit = sum(item["amount"] for item in transactions if item["type"] == "credit")
    debit = sum(item["amount"] for item in transactions if item["type"] == "debit")
    log("summarize_cashflow", {"credit": credit, "debit": debit})
    if payload.get("simulateBug") == "missing_bucket":
        {}["summary"]
    return response(context, request_id, "summarizeCashflow", payload, {"summary": {"avgMonthlyCredit": credit, "avgMonthlyDebit": debit, "stability": "GOOD"}, "message": "Cashflow summary generated"})


def detect_anomalies(payload, context, request_id):
    statement = parse_statement(payload)
    transactions = build_transactions(statement, payload)
    anomalies = [item for item in transactions if item["amount"] > 2000]
    log("detect_anomalies", {"anomalyCount": len(anomalies)})
    return response(context, request_id, "detectAnomalies", payload, {"anomalies": anomalies, "message": "Statement anomaly detection completed"})


def health_check(payload, context, request_id):
    return response(context, request_id, "healthCheck", payload, {"message": "Bank statement service is healthy"})


def route_request(request_id, payload, context):
    if request_id == "uploadStatement":
        return upload_statement(payload, context, request_id)
    if request_id == "extractTransactions":
        return extract_transactions(payload, context, request_id)
    if request_id == "summarizeCashflow":
        return summarize_cashflow(payload, context, request_id)
    if request_id == "detectAnomalies":
        return detect_anomalies(payload, context, request_id)
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
        return error_response(context, request_id, exc)
