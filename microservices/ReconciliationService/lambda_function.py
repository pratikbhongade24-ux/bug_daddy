import json
import os
import sys
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone


SERVICE_NAME = "ReconciliationService"
SHARED_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SHARED_ROOT not in sys.path:
    sys.path.insert(0, SHARED_ROOT)

from shared.logger import extract_trace_id, get_trace_id, make_logger, set_trace_id

try:
    from shared.persistence import persist_operation, read_reconciliation_report
except Exception as exc:
    _PERSISTENCE_IMPORT_ERROR = str(exc)
    persist_operation = None

    def read_reconciliation_report(recon_id):
        return {"persistence": {"status": "failed", "error": _PERSISTENCE_IMPORT_ERROR}}


def iso_now():
    return datetime.now(timezone.utc).isoformat()


log = make_logger(SERVICE_NAME)

SUPPORTED_BANKS = ["HDFC", "ICICI", "AXIS"]


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

def _mock_match_transactions(internal_records, bank_records):
    """Match internal records against bank records by referenceId AND amount equality."""
    bank_by_ref = {r["referenceId"]: r for r in bank_records}
    internal_by_ref = {r["referenceId"]: r for r in internal_records}

    matched = []
    discrepancies = []

    for ref_id, internal in internal_by_ref.items():
        bank_rec = bank_by_ref.get(ref_id)
        if bank_rec and bank_rec["amount"] == internal["amount"]:
            matched.append({
                "referenceId": ref_id,
                "internalTxnId": internal["txnId"],
                "bankTxnId": bank_rec["txnId"],
                "amount": internal["amount"],
                "status": "MATCHED",
            })
        else:
            discrepancies.append({
                "referenceId": ref_id,
                "internalTxnId": internal["txnId"],
                "bankTxnId": bank_rec["txnId"] if bank_rec else None,
                "internalAmount": internal["amount"],
                "bankAmount": bank_rec["amount"] if bank_rec else None,
                "status": "UNMATCHED_INTERNAL",
            })

    # Bank records with no matching internal record
    for ref_id, bank_rec in bank_by_ref.items():
        if ref_id not in internal_by_ref:
            discrepancies.append({
                "referenceId": ref_id,
                "internalTxnId": None,
                "bankTxnId": bank_rec["txnId"],
                "internalAmount": None,
                "bankAmount": bank_rec["amount"],
                "status": "UNMATCHED_BANK",
            })

    return matched, discrepancies


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_request(event):
    body = event.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = {"rawBody": body}
    if isinstance(body, dict):
        payload = body
    elif isinstance(event, dict):
        payload = {key: value for key, value in event.items() if key != "body"}
    else:
        payload = {}
    return payload.get("requestId") or "healthCheck", payload


def response(context, request_id, operation, payload, extra=None):
    trace_id = getattr(context, "aws_request_id", None)
    base = {
        "service": SERVICE_NAME,
        "requestId": request_id,
        "operation": operation,
        "traceId": get_trace_id(),
        "requestTraceId": trace_id,
        "timestamp": iso_now(),
        "db": {
            "host": os.environ.get("DB_HOST"),
            "port": os.environ.get("DB_PORT"),
            "name": os.environ.get("DB_NAME"),
            "user": os.environ.get("DB_USER"),
        },
        "payload": payload,
    }
    if extra:
        base.update(extra)
    if persist_operation:
        base["persistence"] = persist_operation(
            service_name=SERVICE_NAME,
            operation=operation,
            request_id=request_id,
            trace_id=trace_id,
            payload=payload,
            response_payload=extra or {},
        )
    return {"statusCode": 200, "body": json.dumps(base)}


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------

def run_reconciliation(payload, context, request_id):
    bank_code = payload.get("bankCode", "ALL")
    from_date = payload.get("fromDate", "")
    to_date = payload.get("toDate", "")
    recon_type = payload.get("reconType", "ALL")

    recon_id = "RECON-" + uuid.uuid4().hex[:12].upper()

    # Mock internal records: 5 entries
    internal_records = [
        {"txnId": f"INT-{str(i).zfill(4)}", "referenceId": f"REF-{str(i).zfill(4)}", "amount": 1000 + i * 100}
        for i in range(1, 6)
    ]

    # Mock bank records: 4 entries — intentionally missing REF-0005
    bank_records = [
        {"txnId": f"BANK-{str(i).zfill(4)}", "referenceId": f"REF-{str(i).zfill(4)}", "amount": 1000 + i * 100}
        for i in range(1, 5)
    ]

    matched, discrepancies = _mock_match_transactions(internal_records, bank_records)

    total_internal = len(internal_records)
    total_bank = len(bank_records)
    matched_count = len(matched)
    discrepancy_count = len(discrepancies)
    match_rate = f"{round(matched_count / total_internal * 100, 2)}%" if total_internal else "0%"

    reconciliation = {
        "reconId": recon_id,
        "bankCode": bank_code,
        "fromDate": from_date,
        "toDate": to_date,
        "reconType": recon_type,
        "status": "COMPLETED",
        "completedAt": iso_now(),
    }
    summary = {
        "totalInternal": total_internal,
        "totalBank": total_bank,
        "matched": matched_count,
        "discrepancies": discrepancy_count,
        "matchRate": match_rate,
    }
    return response(context, request_id, "runReconciliation", payload, {
        "reconciliation": reconciliation,
        "summary": summary,
        "matched": matched,
        "discrepancies": discrepancies,
        "message": "Reconciliation completed",
    })


def get_discrepancies(payload, context, request_id):
    discrepancies = [
        {
            "referenceId": "REF-0005",
            "internalTxnId": "INT-0005",
            "bankTxnId": None,
            "internalAmount": 1500,
            "bankAmount": None,
            "status": "UNMATCHED_INTERNAL",
            "description": "Transaction present in internal records but missing from bank statement",
        }
    ]
    return response(context, request_id, "getDiscrepancies", payload, {
        "discrepancies": discrepancies,
        "count": len(discrepancies),
        "message": "Discrepancies fetched",
    })


def resolve_discrepancy(payload, context, request_id):
    required_fields = ["reconId", "referenceId", "resolutionCode", "resolvedBy"]
    missing = [f for f in required_fields if not payload.get(f)]
    if missing:
        body = json.dumps({"error": f"Missing required fields: {missing}", "missingFields": missing})
        return {"statusCode": 400, "body": body}

    resolution = {
        "reconId": payload["reconId"],
        "referenceId": payload["referenceId"],
        "resolutionCode": payload["resolutionCode"],
        "resolvedBy": payload["resolvedBy"],
        "remarks": payload.get("remarks", ""),
        "status": "RESOLVED",
        "resolvedAt": iso_now(),
    }
    return response(context, request_id, "resolveDiscrepancy", payload, {
        "resolution": resolution,
        "message": "Discrepancy resolved successfully",
    })


def get_reconciliation_report(payload, context, request_id):
    recon_id = payload.get("reconId", "RECON-001")
    return response(context, request_id, "getReconciliationReport", payload, {
        "report": read_reconciliation_report(recon_id),
        "message": "Reconciliation report fetched",
    })


def get_daily_recon_report_json(payload, context, request_id):
    bank_code_filter = payload.get("bankCode")
    date_override = payload.get("date")

    if date_override:
        report_date = date_override
    else:
        report_date = (date.today() - timedelta(days=1)).isoformat()

    report_id = "RPT-" + uuid.uuid4().hex[:12].upper()
    generated_at = iso_now()

    banks_to_process = [bank_code_filter.upper()] if bank_code_filter else SUPPORTED_BANKS

    all_transactions = []
    all_refunds = []
    summary_by_bank = {}

    for bank in banks_to_process:
        settlement_window = "T+1" if bank == "ICICI" else "T+0"

        # 5 mock payment transactions per bank
        bank_transactions = []
        for i in range(1, 6):
            txn_id = f"PAY-{bank}-{str(i).zfill(4)}"
            amount = 1250 + (i - 1) * 250  # 1250, 1500, 1750, 2000, 2250
            status = "FAILED" if i % 5 == 0 else "SUCCESS"
            bank_match_status = "UNMATCHED_INTERNAL" if status == "FAILED" else "MATCHED"
            bank_transactions.append({
                "txnId": txn_id,
                "bankCode": bank,
                "amount": amount,
                "status": status,
                "bankMatchStatus": bank_match_status,
                "settlementWindow": settlement_window,
                "date": report_date,
            })

        # 2 mock refund transactions per bank
        bank_refunds = []
        for i in range(1, 3):
            ref_id = f"REF-TXN-{bank}-{str(i).zfill(4)}"
            refund_amount = 600 + (i - 1) * 100  # 600, 700
            refund_type = "FULL" if i % 2 != 0 else "PARTIAL"
            bank_refunds.append({
                "refundId": ref_id,
                "bankCode": bank,
                "refundAmount": refund_amount,
                "refundType": refund_type,
                "date": report_date,
            })

        successful_txns = [t for t in bank_transactions if t["status"] == "SUCCESS"]
        failed_txns = [t for t in bank_transactions if t["status"] == "FAILED"]

        summary_by_bank[bank] = {
            "totalTransactions": len(bank_transactions),
            "successfulTransactions": len(successful_txns),
            "failedTransactions": len(failed_txns),
            "totalRefunds": len(bank_refunds),
            "totalAmount": sum(t["amount"] for t in bank_transactions),
            "totalRefundAmount": sum(r["refundAmount"] for r in bank_refunds),
            "settlementWindow": settlement_window,
        }

        all_transactions.extend(bank_transactions)
        all_refunds.extend(bank_refunds)

    overall_summary = {
        "totalBanks": len(banks_to_process),
        "totalTransactions": len(all_transactions),
        "totalRefunds": len(all_refunds),
        "totalAmount": sum(t["amount"] for t in all_transactions),
        "totalRefundAmount": sum(r["refundAmount"] for r in all_refunds),
        "reportDate": report_date,
    }

    report = {
        "reportId": report_id,
        "reportDate": report_date,
        "generatedAt": generated_at,
        "summary": overall_summary,
        "summaryByBank": summary_by_bank,
        "transactions": all_transactions,
        "refunds": all_refunds,
    }
    return response(context, request_id, "getDailyReconReportJson", payload, {
        "report": report,
        "message": "Daily reconciliation report generated",
    })


def get_reconciliation_summary(payload, context, request_id):
    summary = {
        "totalRuns": 42,
        "completedRuns": 40,
        "pendingRuns": 2,
        "totalMatched": 3800,
        "totalDiscrepancies": 150,
        "overallMatchRate": "96.2%",
        "lastRunAt": iso_now(),
    }
    return response(context, request_id, "getReconciliationSummary", payload, {
        "summary": summary,
        "message": "Reconciliation summary fetched",
    })


def health_check(payload, context, request_id):
    return response(context, request_id, "healthCheck", payload, {
        "message": "Reconciliation service is healthy",
        "supportedBanks": SUPPORTED_BANKS,
    })


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def route_request(request_id, payload, context):
    if request_id == "runReconciliation":
        return run_reconciliation(payload, context, request_id)
    if request_id == "getDiscrepancies":
        return get_discrepancies(payload, context, request_id)
    if request_id == "resolveDiscrepancy":
        return resolve_discrepancy(payload, context, request_id)
    if request_id == "getReconciliationReport":
        return get_reconciliation_report(payload, context, request_id)
    if request_id == "getDailyReconReportJson":
        return get_daily_recon_report_json(payload, context, request_id)
    if request_id == "getReconciliationSummary":
        return get_reconciliation_summary(payload, context, request_id)
    return health_check(payload, context, request_id)


def lambda_handler(event, context):
    trace_id = extract_trace_id(event)
    set_trace_id(trace_id)
    request_id, payload = parse_request(event)
    log("request_received", {"requestId": request_id, "traceId": trace_id, "payload": payload})
    try:
        result = route_request(request_id, payload, context)
        log("request_completed", {"requestId": request_id})
        return result
    except Exception as exc:
        print(f"ERROR {SERVICE_NAME} failed while handling {request_id}: {exc}")
        print(traceback.format_exc())
        raise
