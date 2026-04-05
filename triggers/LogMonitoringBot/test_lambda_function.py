import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("lambda_function.py")
SPEC = importlib.util.spec_from_file_location("log_monitor_lambda", MODULE_PATH)
lambda_function = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(lambda_function)


def test_build_fingerprint_ignores_request_scoped_values():
    service = "grabhack-CustomerOnboardingService"
    issue_type = "error"
    first = "ERROR Failed to create onboarding lead for customer C101 RequestId: a815fe75-ce89-4032-b58e-48d16fe9a3ad"
    second = "ERROR Failed to create onboarding lead for customer C202 RequestId: db04fb56-847d-4c82-9364-367537086fa5"

    first_fingerprint = lambda_function.build_fingerprint(service, issue_type, first)
    second_fingerprint = lambda_function.build_fingerprint(service, issue_type, second)

    assert first_fingerprint == second_fingerprint


def test_build_fingerprint_changes_for_distinct_failures():
    service = "grabhack-CustomerOnboardingService"
    first = lambda_function.build_fingerprint(
        service,
        "timeout",
        "Exception: database connection timeout while inserting lead",
    )
    second = lambda_function.build_fingerprint(
        service,
        "zero_division",
        "[ERROR] ZeroDivisionError: division by zero",
    )

    assert first != second
