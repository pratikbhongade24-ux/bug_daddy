import json
import os
import sys
import unittest

# Ensure the module path includes the service directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lambda_function import lambda_handler

class TestSimulateBugHandling(unittest.TestCase):
    def setUp(self):
        # Ensure the environment variable that enables the bug simulation is NOT set
        if "ENABLE_SIMULATE_BUG" in os.environ:
            del os.environ["ENABLE_SIMULATE_BUG"]

    def test_amount_cast_flag_ignored(self):
        event = {
            "body": json.dumps({
                "requestId": "summarizeCashflow",
                "simulateBug": "amount_cast",
                "statementId": "STM-123",
                "pages": 2
            })
        }
        # Context can be a simple object with aws_request_id attribute
        class Context:
            aws_request_id = "test-id"
        result = lambda_handler(event, Context())
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])  # type: ignore
        self.assertIn("summary", body["payload"])  # ensure normal flow

if __name__ == "__main__":
    unittest.main()
