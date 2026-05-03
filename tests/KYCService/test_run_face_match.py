import json
import unittest
from microservices.KYCService.lambda_function import lambda_handler

class TestRunFaceMatchSimulateBug(unittest.TestCase):
    def test_face_threshold_bug_fixed(self):
        event = {
            "body": json.dumps({
                "requestId": "runFaceMatch",
                "simulateBug": "face_threshold"
            })
        }
        # context can be a simple object with aws_request_id attribute
        class Context:
            aws_request_id = "test-id"
        response = lambda_handler(event, Context())
        body = json.loads(response["body"])
        self.assertIn("faceMatch", body["payload"])  # payload contains original request
        self.assertIn("faceMatch", body["payload"])  # ensure key exists
        # The response extra contains faceMatch details
        self.assertIn("faceMatch", body)
        self.assertEqual(body["faceMatch"]["score"], 0.95)
        self.assertEqual(body["faceMatch"]["result"], "MATCHED")

if __name__ == "__main__":
    unittest.main()