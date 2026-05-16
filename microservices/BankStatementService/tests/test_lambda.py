import json
import pytest

from microservices.BankStatementService.lambda_function import lambda_handler

class DummyContext:
    aws_request_id = "test-request-id"

def invoke(event):
    return lambda_handler(event, DummyContext())

def test_normal_summarize_cashflow_success():
    event = {
        "body": json.dumps({"requestId": "summarizeCashflow", "statementId": "STM-001"})
    }
    resp = invoke(event)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["operation"] == "summarizeCashflow"
    assert "summary" in body["payload"]

def test_simulated_amount_cast_returns_400():
    event = {
        "body": json.dumps({
            "requestId": "summarizeCashflow",
            "statementId": "STM-001",
            "simulateBug": "amount_cast"
        })
    }
    resp = invoke(event)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert "error" in body
    assert "amount_cast" in body["error"]

def test_simulated_negative_pages_returns_400():
    event = {
        "body": json.dumps({
            "requestId": "summarizeCashflow",
            "statementId": "STM-001",
            "pages": 2,
            "simulateBug": "negative_pages"
        })
    }
    resp = invoke(event)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert "error" in body
    assert "negative_pages" in body["error"]

def test_simulated_missing_bucket_returns_400():
    event = {
        "body": json.dumps({
            "requestId": "summarizeCashflow",
            "statementId": "STM-001",
            "simulateBug": "missing_bucket"
        })
    }
    resp = invoke(event)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert "error" in body
    assert "missing_bucket" in body["error"]
