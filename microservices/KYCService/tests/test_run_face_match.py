import json

from lambda_function import run_face_match, normalize_identity, response

class DummyContext:
    aws_request_id = "dummy-request-id"

def test_run_face_match_normal():
    payload = {"customerId": "C123"}
    result = run_face_match(payload, DummyContext(), "runFaceMatch")
    body = json.loads(result["body"])
    assert body["faceMatch"]["score"] == 0.93
    assert body["faceMatch"]["result"] == "MATCHED"

def test_run_face_match_simulated_low_score():
    payload = {"customerId": "C123", "simulateBug": "face_threshold"}
    result = run_face_match(payload, DummyContext(), "runFaceMatch")
    body = json.loads(result["body"])
    assert body["faceMatch"]["score"] == 0.45
    assert body["faceMatch"]["result"] == "MATCHED"