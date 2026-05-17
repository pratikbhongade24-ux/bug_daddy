"""
Seed script: payments, refunds, and reconciliation data.

Demonstrates the AXIS partial-refund bug:
- AXIS ignores partial refund amounts and processes the original full amount.
- The ms_reconciliation_items for those refunds reflect the bank-paid amount
  (original), creating AMOUNT_MISMATCH discrepancies.

Usage:
    cd microservices
    python seeds/seed_payments_and_recon.py
"""

import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MICROSERVICES_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if MICROSERVICES_ROOT not in sys.path:
    sys.path.insert(0, MICROSERVICES_ROOT)

from shared.persistence import connect_db, decimal_value, ensure_schema, json_value


BANKS = ["HDFC", "ICICI", "AXIS"]
NUM_PAYMENTS = 50
NUM_REFUNDS = 20
NUM_AXIS_BUG_REFUNDS = 8  # among the 20 refunds, exactly 8 are AXIS PARTIAL bug cases

random.seed(42)


def utc_sql_offset(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def round_to_nearest_500(value: float) -> float:
    return round(value / 500) * 500


def generate_payments() -> list[dict]:
    """Generate 50 seed payments spread across 3 banks and 20 customers."""
    payments = []
    for i in range(1, NUM_PAYMENTS + 1):
        payment_id = f"PAY-SEED-{str(i).zfill(4)}"
        bank_code = BANKS[i % 3]
        customer_id = f"CUST-{str(random.randint(1, 20)).zfill(4)}"
        amount = round_to_nearest_500(random.uniform(50000, 200000))
        days_ago = random.randint(0, 30)
        created_at = utc_sql_offset(days_ago)
        bank_ref_id = bank_code + uuid.uuid4().hex[:10].upper()
        payments.append({
            "payment_id": payment_id,
            "customer_id": customer_id,
            "bank_code": bank_code,
            "amount": amount,
            "account_masked": "XXXXXX" + str(random.randint(1000, 9999)),
            "status": "SUCCESS",
            "bank_ref_id": bank_ref_id,
            "settlement_window": "T+1" if bank_code == "ICICI" else "T+0",
            "created_at": created_at,
        })
    return payments


def generate_refunds(payments: list[dict]) -> list[dict]:
    """
    Generate 20 refunds from 50 payments.
    - Exactly 8 are AXIS PARTIAL refunds (the bug cases).
    - The rest are a mix of banks/types with correct amounts.
    """
    axis_payments = [p for p in payments if p["bank_code"] == "AXIS"]
    non_axis_payments = [p for p in payments if p["bank_code"] != "AXIS"]

    random.shuffle(axis_payments)
    random.shuffle(non_axis_payments)

    refunds = []

    # 8 AXIS PARTIAL bug refunds
    for i, payment in enumerate(axis_payments[:NUM_AXIS_BUG_REFUNDS]):
        refund_id = f"REF-SEED-AXIS-BUG-{str(i + 1).zfill(4)}"
        original_amount = payment["amount"]
        requested_refund = round_to_nearest_500(original_amount * random.uniform(0.2, 0.6))
        refunds.append({
            "refund_id": refund_id,
            "original_payment_id": payment["payment_id"],
            "customer_id": payment["customer_id"],
            "bank_code": "AXIS",
            "refund_type": "PARTIAL",
            "refund_amount": requested_refund,
            "original_amount": original_amount,
            "reason": "Partial cancellation requested by customer",
            "remarks": "AXIS bug: bank processed full original amount instead of partial refund",
            "status": "INITIATED",
            "bank_ref_id": "AXISREF" + uuid.uuid4().hex[:8].upper(),
            "notify_customer": True,
            "is_bug": True,
        })

    # 12 non-bug refunds (mix of banks and types)
    remaining_slots = NUM_REFUNDS - NUM_AXIS_BUG_REFUNDS
    source_payments = (non_axis_payments + axis_payments[NUM_AXIS_BUG_REFUNDS:])[:remaining_slots]
    for i, payment in enumerate(source_payments):
        refund_id = f"REF-SEED-{str(i + 1).zfill(4)}"
        original_amount = payment["amount"]
        refund_type = "FULL" if i % 3 == 0 else "PARTIAL"
        refund_amount = original_amount if refund_type == "FULL" else round_to_nearest_500(original_amount * random.uniform(0.1, 0.9))
        refunds.append({
            "refund_id": refund_id,
            "original_payment_id": payment["payment_id"],
            "customer_id": payment["customer_id"],
            "bank_code": payment["bank_code"],
            "refund_type": refund_type,
            "refund_amount": refund_amount,
            "original_amount": original_amount,
            "reason": "Customer initiated refund",
            "remarks": "",
            "status": "PROCESSED",
            "bank_ref_id": payment["bank_code"] + "REF" + uuid.uuid4().hex[:8].upper(),
            "notify_customer": True,
            "is_bug": False,
        })

    return refunds


def seed(conn) -> None:
    ensure_schema(conn)

    payments = generate_payments()
    refunds = generate_refunds(payments)

    print(f"Seeding {len(payments)} payments...")
    with conn.cursor() as cur:
        for p in payments:
            cur.execute(
                """
                INSERT INTO ms_payments
                  (payment_id, bank_code, amount, account_masked, status,
                   bank_ref_id, settlement_window, raw_payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status),
                  bank_ref_id = COALESCE(VALUES(bank_ref_id), bank_ref_id)
                """,
                (
                    p["payment_id"],
                    p["bank_code"],
                    decimal_value(p["amount"]),
                    p["account_masked"],
                    p["status"],
                    p["bank_ref_id"],
                    p["settlement_window"],
                    json_value(p),
                    p["created_at"],
                ),
            )
    print(f"  Inserted {len(payments)} payments into ms_payments")

    print(f"Seeding {len(refunds)} refunds ({NUM_AXIS_BUG_REFUNDS} AXIS bug cases)...")
    with conn.cursor() as cur:
        for r in refunds:
            cur.execute(
                """
                INSERT INTO ms_refunds
                  (refund_id, original_payment_id, bank_code, refund_type, refund_amount,
                   reason, remarks, status, bank_ref_id, notify_customer, raw_payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  status = VALUES(status)
                """,
                (
                    r["refund_id"],
                    r["original_payment_id"],
                    r["bank_code"],
                    r["refund_type"],
                    decimal_value(r["refund_amount"]),
                    r["reason"],
                    r["remarks"],
                    r["status"],
                    r["bank_ref_id"],
                    r["notify_customer"],
                    json_value(r),
                ),
            )
    print(f"  Inserted {len(refunds)} refunds into ms_refunds")

    # Build reconciliation run
    recon_id = "RECON-SEED-MASTER-001"
    total_internal = len(payments)
    matched_count = len(payments)  # all payments match
    discrepancy_count = NUM_AXIS_BUG_REFUNDS  # 8 AXIS partial refund mismatches
    match_rate = f"{round((matched_count / total_internal) * 100, 2)}%"

    print(f"Seeding reconciliation run {recon_id}...")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ms_reconciliation_runs
              (recon_id, bank_code, recon_type, status, total_internal, total_bank,
               matched_count, discrepancy_count, match_rate, summary_json, completed_at)
            VALUES (%s, 'ALL', 'ALL', 'COMPLETED', %s, %s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
              status = VALUES(status),
              total_internal = VALUES(total_internal),
              total_bank = VALUES(total_bank),
              matched_count = VALUES(matched_count),
              discrepancy_count = VALUES(discrepancy_count),
              match_rate = VALUES(match_rate),
              summary_json = VALUES(summary_json),
              completed_at = VALUES(completed_at)
            """,
            (
                recon_id,
                total_internal,
                total_internal,  # total_bank same as internal (all present)
                matched_count,
                discrepancy_count,
                match_rate,
                json_value({
                    "totalInternal": total_internal,
                    "totalBank": total_internal,
                    "matched": matched_count,
                    "discrepancies": discrepancy_count,
                    "matchRate": match_rate,
                }),
            ),
        )

    # Insert all 50 payments as MATCHED reconciliation items
    print(f"Seeding {len(payments)} reconciliation items (payments = MATCHED)...")
    with conn.cursor() as cur:
        for p in payments:
            cur.execute(
                """
                INSERT INTO ms_reconciliation_items
                  (recon_id, reference_id, txn_type, internal_txn_id, bank_txn_id, amount, match_status)
                VALUES (%s, %s, 'PAYMENT', %s, %s, %s, 'MATCHED')
                ON DUPLICATE KEY UPDATE match_status = 'MATCHED'
                """,
                (
                    recon_id,
                    p["payment_id"],
                    p["payment_id"],
                    p["bank_ref_id"],
                    decimal_value(p["amount"]),
                ),
            )

    # Insert AXIS PARTIAL bug refunds as AMOUNT_MISMATCH items
    axis_bug_refunds = [r for r in refunds if r.get("is_bug")]
    print(f"Seeding {len(axis_bug_refunds)} AMOUNT_MISMATCH items (AXIS partial bug)...")
    with conn.cursor() as cur:
        for r in axis_bug_refunds:
            cur.execute(
                """
                INSERT INTO ms_reconciliation_items
                  (recon_id, reference_id, txn_type, internal_txn_id, bank_txn_id,
                   amount, match_status, remarks)
                VALUES (%s, %s, 'REFUND', %s, %s, %s, 'AMOUNT_MISMATCH', %s)
                ON DUPLICATE KEY UPDATE
                  match_status = 'AMOUNT_MISMATCH',
                  remarks = VALUES(remarks)
                """,
                (
                    recon_id,
                    r["refund_id"],
                    r["refund_id"],
                    r["bank_ref_id"],
                    decimal_value(r["original_amount"]),  # bank paid full original amount
                    (
                        f"AXIS BUG: Customer requested partial refund of {r['refund_amount']}, "
                        f"but AXIS processed full original amount {r['original_amount']}. "
                        f"Overpaid by {r['original_amount'] - r['refund_amount']}."
                    ),
                ),
            )

    # Insert other refunds as MATCHED
    other_refunds = [r for r in refunds if not r.get("is_bug")]
    print(f"Seeding {len(other_refunds)} MATCHED reconciliation items (normal refunds)...")
    with conn.cursor() as cur:
        for r in other_refunds:
            cur.execute(
                """
                INSERT INTO ms_reconciliation_items
                  (recon_id, reference_id, txn_type, internal_txn_id, bank_txn_id,
                   amount, match_status)
                VALUES (%s, %s, 'REFUND', %s, %s, %s, 'MATCHED')
                ON DUPLICATE KEY UPDATE match_status = 'MATCHED'
                """,
                (
                    recon_id,
                    r["refund_id"],
                    r["refund_id"],
                    r["bank_ref_id"],
                    decimal_value(r["refund_amount"]),
                ),
            )

    print("\nSeed complete.")


def print_bug_summary(conn) -> None:
    """Query the DB and print a bug summary report for AXIS AMOUNT_MISMATCH items."""
    print("\n" + "=" * 70)
    print("BUG SUMMARY REPORT: AXIS Partial Refund Mismatch")
    print("=" * 70)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                r.refund_id,
                r.original_payment_id,
                r.bank_code,
                r.refund_type,
                r.refund_amount AS requested_refund_amount,
                ri.amount AS bank_processed_amount,
                ri.remarks
            FROM ms_refunds r
            JOIN ms_reconciliation_items ri
              ON ri.reference_id = r.refund_id
            WHERE ri.match_status = 'AMOUNT_MISMATCH'
            ORDER BY r.refund_id
            """
        )
        rows = cur.fetchall()

    if not rows:
        print("No AMOUNT_MISMATCH items found.")
        return

    print(f"Found {len(rows)} AXIS partial refund discrepancies:\n")
    print(f"{'Refund ID':<30} {'Bank':<6} {'Type':<8} {'Requested':>12} {'Bank Paid':>12} {'Overpaid':>12}")
    print("-" * 82)
    total_overpaid = 0.0
    for row in rows:
        requested = float(row.get("requested_refund_amount") or 0)
        bank_paid = float(row.get("bank_processed_amount") or 0)
        overpaid = bank_paid - requested
        total_overpaid += overpaid
        print(
            f"{row['refund_id']:<30} "
            f"{row['bank_code']:<6} "
            f"{row['refund_type']:<8} "
            f"{requested:>12,.2f} "
            f"{bank_paid:>12,.2f} "
            f"{overpaid:>12,.2f}"
        )
    print("-" * 82)
    print(f"{'TOTAL OVERPAID BY AXIS':>58} {total_overpaid:>12,.2f}")
    print("=" * 70)
    print("\nRoot cause: AXIS _mock_axis_process_refund() uses original_amount")
    print("  when provided, ignoring the partial refund_amount argument.")
    print("  This causes AXIS to always credit the full original payment amount,")
    print("  resulting in customer overpayment on partial refunds.")


if __name__ == "__main__":
    conn = connect_db()
    try:
        seed(conn)
        print_bug_summary(conn)
    finally:
        conn.close()
