import json
import sys
import os

# Ensure the service code is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../microservices/KYCService')))

from lambda_function import lambda_handler


def test_run_face_match_simulated_bug():
    # Simulate an API Gateway event payload
    event = {
        "body": json.dumps({
            "requestId": "runFaceMatch",
            "simulateBug": "face_threshold",
            "customerId": "cust-123"
        })
    }
    # Context can be a simple object with aws_request_id attribute
    class Context:
        aws_request_id = "test-request-id"
    context = Context()

    response = lambda_handler(event, context)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    # Verify the mock score is returned and no exception occurred
    assert "faceMatch" in body["payload"]
    assert body["payload"]["faceMatch"]["score"] == 0.95
    assert body["payload"]["faceMatch"]["result"] == "MATCHED"
