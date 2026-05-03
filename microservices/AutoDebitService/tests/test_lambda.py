import json
import pytest
from microservices.AutoDebitService.lambda_function import lambda_handler, execute_debit, load_mandate

class DummyContext:
    aws_request_id = "test-request-id"


def invoke(event):
    return lambda_handler(event, DummyContext())


def test_execute_debit_without_simulate_bug():
    event = {
        "body": json.dumps({
            "requestId": "executeDebit",
            "mandateId": "M-001",
            "amount": 500,
            "transactionId": "TX-123"
        })
    }
    resp = invoke(event)
    body = json.loads(resp["body"])
    assert body["payload"]["requestId"] == "executeDebit"
    assert body["debit"]["amount"] == 500


def test_execute_debit_with_simulate_bug_flag():
    event = {
        "body": json.dumps({
            "requestId": "executeDebit",
            "mandateId": "M-002",
            "amount": 300,
            "transactionId": "TX-456",
            "simulateBug": "execute_type"
        })
    }
    resp = invoke(event)
    body = json.loads(resp["body"])
    # Amount should be incremented by 100 as per fix
    assert body["debit"]["amount"] == 400
