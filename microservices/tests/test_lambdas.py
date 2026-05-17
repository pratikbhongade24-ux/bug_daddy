"""
Unit tests for all 6 microservice Lambda functions.

Each test exercises:
  - happy-path routing for every operation
  - simulateBug paths raise the expected exceptions (proving intentional bug injection)
  - health-check fallback
  - body-parsing (JSON string body and direct-dict event)
  - X-Trace-ID propagation
"""
import json
import sys
import os
import pytest

# Make the microservices root importable so shared.* and each service work
MICROSERVICES_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if MICROSERVICES_ROOT not in sys.path:
    sys.path.insert(0, MICROSERVICES_ROOT)


class _FakeContext:
    aws_request_id = "test-aws-request-id"


CTX = _FakeContext()


def _body(result):
    return json.loads(result["body"])


# ---------------------------------------------------------------------------
# AutoDebitService
# ---------------------------------------------------------------------------

import AutoDebitService.lambda_function as auto_debit


class TestAutoDebitService:
    def _invoke(self, request_id, payload=None):
        event = {"requestId": request_id, **(payload or {})}
        return auto_debit.lambda_handler(event, CTX)

    def test_register_mandate(self):
        r = self._invoke("registerMandate", {"mandateId": "M-1", "bankCode": "AXIS"})
        assert r["statusCode"] == 200
        b = _body(r)
        assert b["mandate"]["status"] == "REGISTERED"

    def test_validate_mandate_ok(self):
        r = self._invoke("validateMandate", {"mandateId": "M-2"})
        assert r["statusCode"] == 200
        b = _body(r)
        assert b["validation"]["status"] == "VALID"

    def test_validate_mandate_bug_index_error(self):
        with pytest.raises(IndexError):
            self._invoke("validateMandate", {"simulateBug": "mandate_lookup"})

    def test_execute_debit_ok(self):
        r = self._invoke("executeDebit", {"mandateId": "M-3", "amount": 500})
        assert r["statusCode"] == 200
        assert _body(r)["debit"]["status"] == "SCHEDULED"

    def test_execute_debit_bug_type_error(self):
        with pytest.raises(TypeError):
            self._invoke("executeDebit", {"simulateBug": "execute_type"})

    def test_execute_debit_bug_str_amount(self):
        with pytest.raises(TypeError):
            self._invoke("executeDebit", {"simulateBug": "mandate_str_amount", "amount": "4500"})

    def test_get_mandate_status(self):
        r = self._invoke("getMandateStatus", {"mandateId": "M-4"})
        assert _body(r)["status"]["state"] == "ACTIVE"

    def test_health_check(self):
        r = auto_debit.lambda_handler({}, CTX)
        assert r["statusCode"] == 200
        assert "healthy" in _body(r)["message"]

    def test_trace_id_propagation(self):
        event = {"headers": {"X-Trace-ID": "trace-abc"}, "requestId": "healthCheck"}
        r = auto_debit.lambda_handler(event, CTX)
        assert _body(r)["traceId"] == "trace-abc"

    def test_json_string_body(self):
        event = {"body": json.dumps({"requestId": "getMandateStatus", "mandateId": "M-5"})}
        r = auto_debit.lambda_handler(event, CTX)
        assert r["statusCode"] == 200


# ---------------------------------------------------------------------------
# BankStatementService
# ---------------------------------------------------------------------------

import BankStatementService.lambda_function as bank_stmt


class TestBankStatementService:
    def _invoke(self, request_id, payload=None):
        event = {"requestId": request_id, **(payload or {})}
        return bank_stmt.lambda_handler(event, CTX)

    def test_upload_statement(self):
        r = self._invoke("uploadStatement", {"statementId": "STM-1", "pages": 5})
        assert r["statusCode"] == 200
        assert _body(r)["upload"]["status"] == "UPLOADED"

    def test_extract_transactions(self):
        r = self._invoke("extractTransactions", {"statementId": "STM-2"})
        b = _body(r)
        assert isinstance(b["transactions"], list)
        assert len(b["transactions"]) == 3

    def test_extract_transactions_bug_amount_cast(self):
        with pytest.raises(ValueError):
            self._invoke("extractTransactions", {"simulateBug": "amount_cast"})

    def test_summarize_cashflow(self):
        r = self._invoke("summarizeCashflow")
        b = _body(r)
        assert "summary" in b
        assert b["summary"]["stability"] == "GOOD"

    def test_summarize_cashflow_bug_missing_bucket(self):
        with pytest.raises(KeyError):
            self._invoke("summarizeCashflow", {"simulateBug": "missing_bucket"})

    def test_upload_bug_negative_pages(self):
        with pytest.raises(IndexError):
            self._invoke("uploadStatement", {"simulateBug": "negative_pages", "pages": 3})

    def test_detect_anomalies(self):
        r = self._invoke("detectAnomalies")
        b = _body(r)
        assert isinstance(b["anomalies"], list)

    def test_health_check(self):
        r = bank_stmt.lambda_handler({}, CTX)
        assert "healthy" in _body(r)["message"]

    def test_json_body_parsing(self):
        event = {"body": json.dumps({"requestId": "uploadStatement", "pages": 2})}
        r = bank_stmt.lambda_handler(event, CTX)
        assert r["statusCode"] == 200


# ---------------------------------------------------------------------------
# CustomerOnboardingService
# ---------------------------------------------------------------------------

import CustomerOnboardingService.lambda_function as onboarding


class TestCustomerOnboardingService:
    def _invoke(self, request_id, payload=None):
        event = {"requestId": request_id, **(payload or {})}
        return onboarding.lambda_handler(event, CTX)

    def test_validate_customer_profile(self):
        r = self._invoke("validateCustomerProfile", {"pan": "ABCDE1234F", "mobile": "9999999999"})
        b = _body(r)
        assert b["validation"]["panPresent"] is True
        assert b["validation"]["mobilePresent"] is True

    def test_create_lead(self):
        r = self._invoke("createLead", {"customerId": "C-1", "name": "Test User"})
        b = _body(r)
        assert b["lead"]["leadId"] == "LEAD-C-1"

    def test_create_lead_bug_risk_division(self):
        with pytest.raises(ZeroDivisionError):
            self._invoke("createLead", {"simulateBug": "risk_division", "riskDenominator": "0"})

    def test_create_lead_bug_key_error(self):
        with pytest.raises((TypeError, KeyError)):
            self._invoke("createLead", {"simulateBug": "lead_key_error"})

    def test_submit_onboarding(self):
        r = self._invoke("submitOnboarding", {"customerId": "C-2", "documents": ["pan", "aadhaar"]})
        b = _body(r)
        assert b["journey"]["status"] == "SUBMITTED"

    def test_submit_onboarding_bug_document_type(self):
        # documents passed as a list; len(documents["pan"]) raises TypeError
        with pytest.raises(TypeError):
            self._invoke("submitOnboarding", {"simulateBug": "document_type", "documents": ["pan", "aadhaar"]})

    def test_get_onboarding_status(self):
        r = self._invoke("getOnboardingStatus", {"customerId": "C-3"})
        assert _body(r)["status"]["applicationStatus"] == "IN_REVIEW"

    def test_health_check(self):
        r = onboarding.lambda_handler({}, CTX)
        assert "healthy" in _body(r)["message"]

    def test_trace_id_header(self):
        event = {"headers": {"x-trace-id": "tid-999"}, "requestId": "healthCheck"}
        r = onboarding.lambda_handler(event, CTX)
        assert _body(r)["traceId"] == "tid-999"


# ---------------------------------------------------------------------------
# DisbursementService
# ---------------------------------------------------------------------------

import DisbursementService.lambda_function as disbursement


class TestDisbursementService:
    def _invoke(self, request_id, payload=None):
        event = {"requestId": request_id, **(payload or {})}
        return disbursement.lambda_handler(event, CTX)

    def test_create_disbursement(self):
        r = self._invoke("createDisbursement", {"disbursementId": "D-1", "amount": 10000})
        b = _body(r)
        assert b["disbursement"]["status"] == "CREATED"

    def test_validate_account_ok(self):
        r = self._invoke("validateAccount", {"accountNumberMasked": "XXXX-1234"})
        assert _body(r)["accountValidation"]["status"] == "VERIFIED"

    def test_validate_account_bug_index_error(self):
        with pytest.raises((IndexError, AttributeError)):
            self._invoke("validateAccount", {"simulateBug": "account_mask", "accountNumberMasked": "XXXX"})

    def test_release_funds_ok(self):
        r = self._invoke("releaseFunds", {"utr": "UTR-XYZ"})
        assert _body(r)["release"]["status"] == "PROCESSING"

    def test_release_funds_bug_zero_division(self):
        with pytest.raises(ZeroDivisionError):
            self._invoke("releaseFunds", {"simulateBug": "release_zero"})

    def test_release_funds_bug_kyc_zero(self):
        with pytest.raises(ZeroDivisionError):
            self._invoke("releaseFunds", {"simulateBug": "disb_zero_from_kyc", "kycScore": 0})

    def test_get_disbursement_status(self):
        r = self._invoke("getDisbursementStatus", {"disbursementId": "D-2"})
        assert _body(r)["status"]["state"] == "SUCCESS"

    def test_health_check(self):
        r = disbursement.lambda_handler({}, CTX)
        assert "healthy" in _body(r)["message"]

    def test_json_body(self):
        event = {"body": json.dumps({"requestId": "getDisbursementStatus", "disbursementId": "D-3"})}
        r = disbursement.lambda_handler(event, CTX)
        assert r["statusCode"] == 200


# ---------------------------------------------------------------------------
# KYCService
# ---------------------------------------------------------------------------

import KYCService.lambda_function as kyc


class TestKYCService:
    def _invoke(self, request_id, payload=None):
        event = {"requestId": request_id, **(payload or {})}
        return kyc.lambda_handler(event, CTX)

    def test_verify_pan_ok(self):
        r = self._invoke("verifyPan", {"pan": "ABCDE1234F"})
        assert _body(r)["verification"]["status"] == "VERIFIED"

    def test_verify_pan_bug_none(self):
        with pytest.raises(AttributeError):
            self._invoke("verifyPan", {"simulateBug": "pan_none"})

    def test_verify_pan_bug_from_onboarding(self):
        with pytest.raises(AttributeError):
            self._invoke("verifyPan", {"simulateBug": "kyc_bad_pan"})

    def test_verify_aadhaar(self):
        r = self._invoke("verifyAadhaar", {"aadhaarMasked": "XXXX-XXXX-5678"})
        assert _body(r)["verification"]["status"] == "VERIFIED"

    def test_run_face_match_ok(self):
        r = self._invoke("runFaceMatch", {"customerId": "C-10"})
        assert _body(r)["faceMatch"]["result"] == "MATCHED"

    def test_run_face_match_bug_zero_division(self):
        with pytest.raises(ZeroDivisionError):
            self._invoke("runFaceMatch", {"simulateBug": "face_threshold"})

    def test_get_kyc_status(self):
        r = self._invoke("getKycStatus", {"customerId": "C-11"})
        assert _body(r)["status"]["kycStatus"] == "APPROVED"

    def test_health_check(self):
        r = kyc.lambda_handler({}, CTX)
        assert "healthy" in _body(r)["message"]

    def test_invalid_json_body_fallback(self):
        event = {"body": "not-json"}
        r = kyc.lambda_handler(event, CTX)
        assert r["statusCode"] == 200


# ---------------------------------------------------------------------------
# SupportService
# ---------------------------------------------------------------------------

import SupportService.lambda_function as support


class TestSupportService:
    def _invoke(self, request_id, payload=None):
        event = {"requestId": request_id, **(payload or {})}
        return support.lambda_handler(event, CTX)

    def test_create_ticket(self):
        r = self._invoke("createTicket", {"ticketId": "SUP-1", "priority": "high"})
        b = _body(r)
        assert b["ticket"]["status"] == "OPEN"
        assert b["ticket"]["priority"] == "high"

    def test_assign_ticket_ok(self):
        r = self._invoke("assignTicket", {"ticketId": "SUP-2", "assignedQueue": "loan-ops"})
        assert _body(r)["assignment"]["status"] == "ASSIGNED"

    def test_assign_ticket_bug_queue_failure(self):
        r = self._invoke("assignTicket", {"simulateBug": "queue_failure", "assignedQueue": "DEAD_QUEUE"})
        assert r["statusCode"] == 500
        b = _body(r)
        assert b["error"]["code"] == "QUEUE_ASSIGNMENT_FAILED"

    def test_update_ticket_ok(self):
        r = self._invoke("updateTicket", {"ticketId": "SUP-3", "comments": ["c1", "c2"]})
        b = _body(r)
        assert b["update"]["commentCount"] == 2

    def test_update_ticket_bug_comment_shape(self):
        # SupportService catches the TypeError and returns HTTP 500 error response
        r = self._invoke("updateTicket", {"simulateBug": "comment_shape", "comments": []})
        assert r["statusCode"] == 500
        assert _body(r)["error"]["code"] == "INTERNAL_SERVER_ERROR"

    def test_update_ticket_bug_from_onboarding(self):
        # comments_from_onboarding is a dict; integer index raises KeyError, caught → HTTP 500
        r = self._invoke("updateTicket", {"simulateBug": "support_from_onboarding"})
        assert r["statusCode"] == 500
        assert _body(r)["error"]["code"] == "INTERNAL_SERVER_ERROR"

    def test_get_ticket_status(self):
        r = self._invoke("getTicketStatus", {"ticketId": "SUP-4"})
        assert _body(r)["status"]["currentState"] == "RESOLVED"

    def test_health_check(self):
        r = support.lambda_handler({}, CTX)
        assert "healthy" in _body(r)["message"]

    def test_json_body(self):
        event = {"body": json.dumps({"requestId": "getTicketStatus", "ticketId": "SUP-5"})}
        r = support.lambda_handler(event, CTX)
        assert r["statusCode"] == 200
