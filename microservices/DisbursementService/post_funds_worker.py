import json
import os
import traceback
from datetime import datetime, timezone
import boto3

SERVICE_NAME = "DisbursementServiceWorker"

_SQS_CLIENT = boto3.client('sqs')


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def log(stage, payload):
    print(json.dumps({"service": SERVICE_NAME, "stage": stage, "payload": payload}))


def process_release(payload):
    """Core logic that would normally run in release_funds.
    For the mock service we simply log and return a success dict.
    """
    disbursement = {
        "disbursementId": payload.get("disbursementId", "DISB-001"),
        "amount": payload.get("amount", 0),
        "destinationBank": payload.get("destinationBank", "MOCKBANK")
    }
    log("process_release", disbursement)
    # Simulate possible bug that could raise – keep behaviour consistent with sync path
    if payload.get("simulateBug") == "release_zero":
        disbursement["amount"] / 0
    # Return a mock result structure
    return {
        "utr": payload.get("utr", "UTR-001"),
        "status": "SUCCESS",
        "destination": disbursement["destinationBank"]
    }


def lambda_handler(event, context):
    # SQS event format: Records list
    for record in event.get("Records", []):
        try:
            payload = json.loads(record.get("body", "{}"))
            log("worker_received", payload)
            result = process_release(payload)
            log("worker_success", result)
            # In a real system we would update DB / emit metrics here.
        except Exception as exc:
            print(f"ERROR {SERVICE_NAME} processing record {record.get('messageId')}: {exc}")
            print(traceback.format_exc())
            # Optionally send to DLQ – omitted for brevity.
    # SQS Lambda integration expects no return value.
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Batch processed"})
    }
