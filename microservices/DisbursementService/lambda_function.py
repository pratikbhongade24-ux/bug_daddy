import json
import os
import traceback
from datetime import datetime, timezone
import boto3

SERVICE_NAME = "DisbursementService"

# Initialize SQS client once (cold start reuse)
_SQS_CLIENT = boto3.client('sqs')


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


def response(context, request_id, operation, payload, extra=None, status_code=200):
    base = {"service": SERVICE_NAME, "requestId": request_id, "operation": operation, "requestTraceId": getattr(context, "aws_request_id", None), "timestamp": iso_now(), "db": {"host": os.environ.get("DB_HOST"), "port": os.environ.get("DB_PORT"), "name": os.environ.get("DB_NAME"), "user": os.environ.get("DB_USER")}, "payload": payload}
    if extra:
        base.update(extra)
    return {"statusCode": status_code, "body": json.dumps(base)}


def prepare_disbursement(payload):
    disbursement = {"disbursementId": payload.get("disbursementId", "DISB-001"), "amount": payload.get("amount", 0), "destinationBank": payload.get("destinationBank", "MOCKBANK")}
    log("prepare_disbursement", disbursement)
    return disbursement


def create_disbursement(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    return response(context, request_id, "createDisbursement", payload, {"disbursement": {"disbursementId": disbursement["disbursementId"], "status": "CREATED", "amount": disbursement["amount"]}, "message": "Disbursement created"})


def validate_account(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    if payload.get("simulateBug") == "account_mask":
        payload["accountNumberMasked"].split("-")[10]
    return response(context, request_id, "validateAccount", payload, {"accountValidation": {"accountNumberMasked": payload.get("accountNumberMasked", "XXXXXX1234"), "status": "VERIFIED"}, "message": "Beneficiary account validated"})


def _enqueue_release(payload):
    """Send the release request to the configured SQS queue.
    Returns the SQS MessageId on success.
    """
    queue_url = os.environ.get("POSTING_QUEUE_URL")
    if not queue_url:
        raise RuntimeError("POSTING_QUEUE_URL environment variable not set for async posting")
    response = _SQS_CLIENT.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(payload)
    )
    return response.get("MessageId")


def release_funds(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    log("release_funds", disbursement)
    # Simulated bug that would raise an exception – keep behaviour unchanged for sync path
    if payload.get("simulateBug") == "release_zero":
        disbursement["amount"] / 0
    # Async handling – enqueue the payload and return immediately
    try:
        message_id = _enqueue_release(payload)
        extra = {"release": {"utr": payload.get("utr", "UTR-001"), "status": "QUEUED", "queueMessageId": message_id, "destination": disbursement["destinationBank"]}, "message": "Funds release queued for async processing"}
        return response(context, request_id, "releaseFunds", payload, extra, status_code=202)
    except Exception as exc:
        # If enqueue fails, fall back to synchronous processing to preserve existing semantics
        log("enqueue_failure", {"error": str(exc)})
        extra = {"release": {"utr": payload.get("utr", "UTR-001"), "status": "PROCESSING", "destination": disbursement["destinationBank"]}, "message": "Funds release initiated (sync fallback)"}
        return response(context, request_id, "releaseFunds", payload, extra)


def get_disbursement_status(payload, context, request_id):
    disbursement = prepare_disbursement(payload)
    return response(context, request_id, "getDisbursementStatus", payload, {"status": {"disbursementId": disbursement["disbursementId"], "state": "SUCCESS", "settlementWindow": "T+0"}, "message": "Disbursement status fetched"})


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
        print(f"ERROR {SERVICE_NAME} failed while handling {request_id}: {exc}")
        print(traceback.format_exc())
        raise
