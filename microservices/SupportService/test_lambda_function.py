import json
import pytest

# Simple context mock
class Context:
    def __init__(self, request_id="test-request-id"):
        self.aws_request_id = request_id

from microservices.SupportService.lambda_function import lambda_handler

@pytest.fixture
def context():
    return Context()


def test_assign_ticket_simulated_queue_failure(context):
    event = {
        "body": json.dumps({
            "requestId": "assignTicket",
            "ticketId": "SUP-123",
            "simulateBug": "queue_failure"
        })
    }
    result = lambda_handler(event, context)
    assert result["statusCode"] == 500
    body = json.loads(result["body"])
    assert body["error"]["code"] == "QUEUE_ASSIGNMENT_FAILED"
    assert "queue assignment failed" in body["error"]["message"].lower()


def test_assign_ticket_success(context):
    event = {
        "body": json.dumps({
            "requestId": "assignTicket",
            "ticketId": "SUP-124"
        })
    }
    result = lambda_handler(event, context)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["payload"]["requestId"] == "assignTicket"
    assert body["payload"]["ticketId"] == "SUP-124"
