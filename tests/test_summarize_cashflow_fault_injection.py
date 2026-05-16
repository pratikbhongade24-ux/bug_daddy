import os
import json
import pytest

# Import the lambda handler from the service module
from microservices.BankStatementService.lambda_function import lambda_handler


def invoke(event_body, enable_fault=False):
    # Set the environment variable for the duration of the call
    os.environ["ENABLE_FAULT_INJECTION"] = "true" if enable_fault else "false"
    event = {"body": json.dumps(event_body)}
    # Context can be a simple stub
    class Context:
        aws_request_id = "test-request-id"
    return lambda_handler(event, Context())


def test_amount_cast_fault_injection_enabled():
    payload = {
        "requestId": "summarizeCashflow",
        "simulateBug": "amount_cast",
        "statementId": "STM-900",
    }
    response = invoke(payload, enable_fault=True)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    # Expect a structured error response
    assert body.get("operation") == "error"
    error = body.get("error")
    assert error is not None
    assert error.get("code") == "UNHANDLED_EXCEPTION"
    assert "Fault injection (amount_cast)" in error.get("message", "")


def test_amount_cast_fault_injection_disabled():
    payload = {
        "requestId": "summarizeCashflow",
        "simulateBug": "amount_cast",
        "statementId": "STM-900",
    }
    response = invoke(payload, enable_fault=False)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    # Normal operation should succeed and contain a summary
    assert body.get("operation") == "summarizeCashflow"
    summary = body.get("summary")
    assert summary is not None
    assert summary["avgMonthlyCredit"] >= 0
