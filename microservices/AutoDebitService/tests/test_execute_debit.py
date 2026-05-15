import json
import pytest
from lambda_function import lambda_handler


class DummyContext:
    aws_request_id = "test-request-id"


def invoke(event):
    return lambda_handler(event, DummyContext())


def test_execute_debit_normal():
    event = {
        "body": json.dumps({
            "requestId": "executeDebit",
            "mandateId": "M-001",
            "amount": 500,
            "transactionId": "TX-123"
        })
    }
    resp = invoke(event)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    # Verify operation and debit fields
    assert body["operation"] == "executeDebit"
    assert body["debit"]["status"] == "SCHEDULED"
    assert body["debit"]["amount"] == 500
    assert body["debit"]["transactionId"] == "TX-123"


def test_execute_debit_simulate_bug():
    event = {
        "body": json.dumps({
            "requestId": "executeDebit",
            "mandateId": "M-001",
            "amount": 500,
            "transactionId": "TX-124",
            "simulateBug": "execute_type"
        })
    }
    resp = invoke(event)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["operation"] == "executeDebit"
    # The payload should contain the simulateBug flag unchanged
    assert body["payload"]["simulateBug"] == "execute_type"
    # Debit amount remains the original amount (simulation does not alter response)
    assert body["debit"]["amount"] == 500
