import pytest
from microservices.AutoDebitService.lambda_function import execute_debit


class DummyContext:
    aws_request_id = "dummy-id"


def test_execute_debit_without_bug():
    payload = {"amount": 1200, "transactionId": "T1"}
    result = execute_debit(payload, DummyContext(), "executeDebit")
    assert result["statusCode"] == 200
    # Verify the amount is present in the response body
    body = result["body"]
    assert "\"amount\": 1200" in body


def test_execute_debit_with_simulate_bug_raises():
    payload = {"amount": 1200, "simulateBug": "execute_type"}
    with pytest.raises(ValueError) as exc:
        execute_debit(payload, DummyContext(), "executeDebit")
    assert "simulateBug 'execute_type' is not permitted" in str(exc.value)
