import json

from microservices.KYCService.lambda_function import lambda_handler


def test_run_face_match_simulated_bug():
    # Simulate an API Gateway event with body containing simulateBug flag
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
    result = lambda_handler(event, Context())
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    # Verify the mock response for the simulated bug
    assert body["operation"] == "runFaceMatch"
    assert body["payload"]["simulateBug"] == "face_threshold"
    assert body["faceMatch"]["score"] == 0.0
    assert body["faceMatch"]["result"] == "MATCHED"
