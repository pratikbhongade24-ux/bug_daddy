import json
import pytest

from microservices.KYCService import lambda_function

class DummyContext:
    aws_request_id = "dummy-request-id"


def test_run_face_match_normal():
    payload = {"customerId": "C123"}
    result = lambda_function.run_face_match(payload, DummyContext(), "runFaceMatch")
    body = json.loads(result["body"])
    assert body["faceMatch"]["score"] == 0.93
    assert body["faceMatch"]["result"] == "MATCHED"


def test_run_face_match_simulated_bug():
    payload = {"customerId": "C123", "simulateBug": "face_threshold"}
    result = lambda_function.run_face_match(payload, DummyContext(), "runFaceMatch")
    body = json.loads(result["body"])
    assert body["faceMatch"]["score"] == 0.45
    assert body["faceMatch"]["result"] == "MATCHED"
