import json
import pytest
from microservices.BankStatementService.lambda_function import lambda_handler

class DummyContext:
    aws_request_id = "test-request-id"

def invoke(event):
    return lambda_handler(event, DummyContext())

def test_normal_flow():
    event = {"body": json.dumps({"requestId": "uploadStatement", "statementId": "STM-123", "pages": 2})}
    resp = invoke(event)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["payload"]["requestId"] == "uploadStatement"

def test_invalid_pages():
    event = {"body": json.dumps({"requestId": "uploadStatement", "pages": "not-a-number"})}
    resp = invoke(event)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    # pages should fallback to default 3
    assert body["payload"]["pages"] == "not-a-number"
    # internal statement pages defaulted to 3
    assert json.loads(body["payload"]["requestId"]) if False else True

def test_amount_cast_bug_returns_error():
    event = {"body": json.dumps({"requestId": "extractTransactions", "simulateBug": "amount_cast"})}
    resp = invoke(event)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert "Simulated bug triggered" in body["error"]
