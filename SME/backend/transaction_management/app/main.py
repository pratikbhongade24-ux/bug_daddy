import json
import logging
import os
from pathlib import Path
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import event, func
from sqlalchemy.orm import Session

from backend.shared.db.database import engine, get_db
from backend.shared.models.entities import (
    LedgerEntry,
    ReconciliationMismatch,
    ReconciliationReport,
    SettlementRecord,
    TransactionAccount,
    TransactionAuditLog,
    TransactionParty,
    TransferTransaction,
)

app = FastAPI(title='Transaction Management Service')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

logger = logging.getLogger('transaction_mgmt')
logging.basicConfig(level=logging.INFO)

METRICS = {
    'requests_total': 0,
    'requests_failed': 0,
    'request_latency_ms_sum': 0.0,
    'db_query_count': 0,
    'db_slow_queries': 0,
    'transfers_created': 0,
    'reconciliation_runs': 0,
    'mismatches_detected': 0,
}

BUG_STATE = {
    'beneficiary_routing_bug_active': os.getenv('TX_BUG_BENEFICIARY_ROUTING_ACTIVE', 'true').lower() in {'1', 'true', 'yes', 'on'},
    'delayed_posting_bug_active': os.getenv('TX_BUG_DELAYED_POSTING_ACTIVE', 'true').lower() in {'1', 'true', 'yes', 'on'},
}
# This flag is intentionally stored in source and can be flipped by the demo "Invoke AI"
# code-fix endpoint to simulate an actual code-level remediation.
CODE_PATCH_APPLIED = False

QUERY_TIMES: dict[int, float] = {}


def _row_dict(row):
    if row is None:
        return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@event.listens_for(engine, 'before_cursor_execute')
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    QUERY_TIMES[id(cursor)] = time.perf_counter()


@event.listens_for(engine, 'after_cursor_execute')
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start = QUERY_TIMES.pop(id(cursor), None)
    if start is None:
        return
    elapsed_ms = (time.perf_counter() - start) * 1000
    METRICS['db_query_count'] += 1
    if elapsed_ms > 200:
        METRICS['db_slow_queries'] += 1
        logger.warning('Slow query %.2f ms | %s', elapsed_ms, statement[:200])


class PartyCreate(BaseModel):
    party_code: str
    party_name: str
    party_type: Literal['INDIVIDUAL', 'BUSINESS', 'INTERNAL'] = 'INDIVIDUAL'


class AccountCreate(BaseModel):
    party_id: int
    account_number: str
    account_type: Literal['SAVINGS', 'CURRENT', 'SETTLEMENT', 'NODAL'] = 'SAVINGS'
    opening_balance: float = Field(default=0, ge=0)


class TransferCreate(BaseModel):
    source_account_id: int
    beneficiary_account_id: int
    amount: float = Field(gt=0)
    anomaly_profile: list[
        Literal[
            'incorrect_debit_credit_mapping',
            'duplicate_transaction',
            'missing_settlement',
            'reconciliation_mismatch',
            'delayed_posting',
            'wrong_beneficiary_transfer',
        ]
    ] = Field(default_factory=list)
    narrative: str | None = None


class ReconciliationRun(BaseModel):
    hours_back: int = Field(default=24, ge=1, le=720)


class DemoScenarioRequest(BaseModel):
    party_a_account_id: int | None = None
    party_b_account_id: int | None = None
    amount: float = Field(gt=0)


class BugFixRequest(BaseModel):
    bug_key: Literal['beneficiary_routing_bug', 'delayed_posting_bug']
    resolved_by: str = Field(default='bugdaddy_agent')
    notes: str | None = None


class BugResetRequest(BaseModel):
    bug_key: Literal['beneficiary_routing_bug', 'delayed_posting_bug'] = 'beneficiary_routing_bug'


def _trace_id_from_request(request: Request, x_trace_id: str | None = None) -> str:
    return x_trace_id or request.headers.get('x-trace-id') or str(uuid.uuid4())


def _find_account_by_number(db: Session, account_number: str) -> TransactionAccount | None:
    return db.query(TransactionAccount).filter(TransactionAccount.account_number == account_number).first()


def _find_party_by_code(db: Session, party_code: str) -> TransactionParty | None:
    return db.query(TransactionParty).filter(TransactionParty.party_code == party_code).first()


def _ensure_demo_entities(db: Session, trace_id: str) -> dict[str, int]:
    # Idempotent demo setup so users can run scenarios without manual party/account creation.
    defaults = [
        ('DEMO-PARTY-A', 'Demo Party A', 'DEMO-ACC-A', Decimal('1000000')),
        ('DEMO-PARTY-B', 'Demo Party B', 'DEMO-ACC-B', Decimal('250000')),
        ('DEMO-PARTY-C', 'Demo Party C', 'DEMO-ACC-C', Decimal('120000')),
    ]
    account_ids: dict[str, int] = {}
    created = False

    for party_code, party_name, account_number, opening in defaults:
        party = _find_party_by_code(db, party_code)
        if not party:
            created = True
            party = TransactionParty(
                party_code=party_code,
                party_name=party_name,
                party_type='BUSINESS',
            )
            db.add(party)
            db.flush()

        account = _find_account_by_number(db, account_number)
        if not account:
            created = True
            account = TransactionAccount(
                party_id=party.id,
                account_number=account_number,
                account_type='CURRENT',
                available_balance=opening,
                ledger_balance=opening,
            )
            db.add(account)
            db.flush()
        account_ids[party_code] = account.id

    if created:
        db.add(TransactionAuditLog(
            trace_id=trace_id,
            action='demo.bootstrap',
            entity_type='transaction_demo',
            entity_id='default-demo-entities',
            details='Created default parties/accounts for demo transactions.',
        ))
    return account_ids


@app.middleware('http')
async def observability_middleware(request: Request, call_next):
    started = time.perf_counter()
    METRICS['requests_total'] += 1
    trace_id = request.headers.get('x-trace-id', str(uuid.uuid4()))
    request.state.trace_id = trace_id
    try:
        response = await call_next(request)
    except Exception:
        METRICS['requests_failed'] += 1
        raise
    elapsed = (time.perf_counter() - started) * 1000
    METRICS['request_latency_ms_sum'] += elapsed
    response.headers['x-trace-id'] = trace_id
    response.headers['x-latency-ms'] = f'{elapsed:.2f}'
    return response


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/metrics')
def metrics():
    avg = 0.0
    if METRICS['requests_total']:
        avg = METRICS['request_latency_ms_sum'] / METRICS['requests_total']
    return {**METRICS, 'request_latency_avg_ms': round(avg, 2)}


@app.post('/parties')
def create_party(payload: PartyCreate, request: Request, db: Session = Depends(get_db)):
    row = TransactionParty(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(TransactionAuditLog(trace_id=request.state.trace_id, action='party.create', entity_type='party', entity_id=str(row.id)))
    db.commit()
    return _row_dict(row)


@app.post('/accounts')
def create_account(payload: AccountCreate, request: Request, db: Session = Depends(get_db)):
    party = db.query(TransactionParty).filter(TransactionParty.id == payload.party_id).first()
    if not party:
        raise HTTPException(status_code=404, detail='Party not found')
    row = TransactionAccount(
        party_id=payload.party_id,
        account_number=payload.account_number,
        account_type=payload.account_type,
        available_balance=Decimal(str(payload.opening_balance)),
        ledger_balance=Decimal(str(payload.opening_balance)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    db.add(TransactionAuditLog(trace_id=request.state.trace_id, action='account.create', entity_type='account', entity_id=str(row.id)))
    db.commit()
    return _row_dict(row)


def _apply_transfer(db: Session, tx: TransferTransaction, src: TransactionAccount, dst: TransactionAccount, anomalies: list[str], trace_id: str):
    amount = Decimal(str(tx.amount))
    debit_account = src
    credit_account = dst

    if 'wrong_beneficiary_transfer' in anomalies:
        wrong = db.query(TransactionAccount).filter(TransactionAccount.id != dst.id, TransactionAccount.id != src.id).first()
        if wrong:
            tx.intended_beneficiary_account_id = dst.id
            tx.beneficiary_account_id = wrong.id
            credit_account = wrong

    # Intentional logical bug for demo: a routing condition sends medium/large transfers
    # to the fallback account instead of intended beneficiary.
    if (
        BUG_STATE['beneficiary_routing_bug_active']
        and (not CODE_PATCH_APPLIED)
        and tx.intended_beneficiary_account_id is None
        and amount >= Decimal('20000')
        and tx.beneficiary_account_id != src.id
    ):
        fallback = db.query(TransactionAccount).filter(TransactionAccount.id != dst.id, TransactionAccount.id != src.id).first()
        if fallback:
            tx.intended_beneficiary_account_id = dst.id
            tx.beneficiary_account_id = fallback.id
            credit_account = fallback
            anomalies.append('wrong_beneficiary_transfer')

    if 'incorrect_debit_credit_mapping' in anomalies:
        debit_account, credit_account = credit_account, debit_account

    debit_account.available_balance = Decimal(str(debit_account.available_balance)) - amount
    debit_account.ledger_balance = Decimal(str(debit_account.ledger_balance)) - amount
    credit_account.available_balance = Decimal(str(credit_account.available_balance)) + amount
    credit_account.ledger_balance = Decimal(str(credit_account.ledger_balance)) + amount

    db.add(LedgerEntry(
        transfer_id=tx.id,
        account_id=debit_account.id,
        entry_type='DEBIT',
        amount=amount,
        running_balance=debit_account.ledger_balance,
        trace_id=trace_id,
    ))
    db.add(LedgerEntry(
        transfer_id=tx.id,
        account_id=credit_account.id,
        entry_type='CREDIT',
        amount=amount,
        running_balance=credit_account.ledger_balance,
        trace_id=trace_id,
    ))


@app.post('/transactions/transfer')
def create_transfer(payload: TransferCreate, request: Request, db: Session = Depends(get_db)):
    src = db.query(TransactionAccount).filter(TransactionAccount.id == payload.source_account_id).first()
    dst = db.query(TransactionAccount).filter(TransactionAccount.id == payload.beneficiary_account_id).first()
    if not src or not dst:
        raise HTTPException(status_code=404, detail='Source or beneficiary account not found')

    trace_id = request.state.trace_id
    transfer_ref = f'TX-{int(time.time())}-{uuid.uuid4().hex[:8]}'
    anomalies = list(payload.anomaly_profile)

    tx = TransferTransaction(
        transfer_ref=transfer_ref,
        source_account_id=src.id,
        beneficiary_account_id=dst.id,
        amount=Decimal(str(payload.amount)),
        status='POSTED',
        posted_at=datetime.now(timezone.utc),
        settled_at=datetime.now(timezone.utc),
        anomaly_flags=json.dumps(anomalies),
        external_ref=f'EXT-{uuid.uuid4().hex[:12]}',
    )

    if 'delayed_posting' in anomalies and BUG_STATE['delayed_posting_bug_active']:
        tx.status = 'POSTING_DELAYED'
        tx.posted_at = datetime.now(timezone.utc) + timedelta(hours=6)

    db.add(tx)
    db.flush()

    _apply_transfer(db, tx, src, dst, anomalies, trace_id)

    if 'missing_settlement' in anomalies:
        db.add(SettlementRecord(
            transfer_id=tx.id,
            expected_amount=Decimal(str(payload.amount)),
            settled_amount=Decimal('0'),
            settlement_status='MISSING',
        ))
    else:
        settled_amt = Decimal(str(payload.amount))
        status = 'SETTLED'
        if 'reconciliation_mismatch' in anomalies:
            settled_amt = settled_amt - Decimal('7.50')
            status = 'MISMATCH'
        db.add(SettlementRecord(
            transfer_id=tx.id,
            expected_amount=Decimal(str(payload.amount)),
            settled_amount=settled_amt,
            settlement_status=status,
            settled_at=datetime.now(timezone.utc),
        ))

    duplicate_id = None
    if 'duplicate_transaction' in anomalies:
        dup = TransferTransaction(
            transfer_ref=f'{transfer_ref}-DUP',
            source_account_id=src.id,
            beneficiary_account_id=tx.beneficiary_account_id,
            intended_beneficiary_account_id=tx.intended_beneficiary_account_id,
            amount=Decimal(str(payload.amount)),
            status='POSTED',
            posted_at=datetime.now(timezone.utc),
            settled_at=datetime.now(timezone.utc),
            anomaly_flags=json.dumps(['duplicate_transaction']),
            external_ref=tx.external_ref,
            parent_transfer_id=tx.id,
        )
        db.add(dup)
        db.flush()
        duplicate_id = dup.id

    db.add(TransactionAuditLog(
        trace_id=trace_id,
        action='transfer.create',
        entity_type='transfer',
        entity_id=str(tx.id),
        details=json.dumps({'anomalies': anomalies, 'duplicate_transfer_id': duplicate_id}),
    ))

    db.commit()
    db.refresh(tx)
    METRICS['transfers_created'] += 1
    return {
        'transfer': _row_dict(tx),
        'duplicate_transfer_id': duplicate_id,
        'trace_id': trace_id,
    }


@app.post('/transactions/demo/party-a-to-party-b-discrepancy')
def create_party_transfer_discrepancy(payload: DemoScenarioRequest, request: Request, db: Session = Depends(get_db)):
    demo_ids = _ensure_demo_entities(db, request.state.trace_id)
    party_a_account_id = payload.party_a_account_id or demo_ids['DEMO-PARTY-A']
    party_b_account_id = payload.party_b_account_id or demo_ids['DEMO-PARTY-B']
    demo = TransferCreate(
        source_account_id=party_a_account_id,
        beneficiary_account_id=party_b_account_id,
        amount=payload.amount,
        anomaly_profile=['wrong_beneficiary_transfer', 'missing_settlement', 'reconciliation_mismatch', 'delayed_posting'],
        narrative='Party A transfer to Party B with intentional reconciliation discrepancy',
    )
    return create_transfer(demo, request=request, db=db)


@app.post('/transactions/demo/bootstrap')
def bootstrap_demo_entities(request: Request, db: Session = Depends(get_db)):
    ids = _ensure_demo_entities(db, request.state.trace_id)
    db.commit()
    return {
        'status': 'ok',
        'message': 'Demo parties/accounts ready',
        'accounts': {
            'party_a_account_id': ids['DEMO-PARTY-A'],
            'party_b_account_id': ids['DEMO-PARTY-B'],
            'party_c_account_id': ids['DEMO-PARTY-C'],
        },
    }


def _seed_demo_transactions_if_needed(db: Session, trace_id: str) -> dict[str, int]:
    existing = db.query(func.count(TransferTransaction.id)).scalar() or 0
    if existing >= 50:
        return {'created': 0, 'total_transfers': existing, 'anomalies_seeded': 0}

    demo_ids = _ensure_demo_entities(db, trace_id)
    a = demo_ids['DEMO-PARTY-A']
    b = demo_ids['DEMO-PARTY-B']
    c = demo_ids['DEMO-PARTY-C']
    account_pairs = [(a, b), (b, a), (a, c), (c, b), (b, c)]

    target_total = 50
    to_create = target_total - existing
    created = 0
    anomalies_seeded = 0
    anomaly_slots = {10, 22, 34, 46}
    for i in range(to_create):
        src, dst = account_pairs[i % len(account_pairs)]
        amount = float(random.randint(2000, 18000))
        profile: list[str] = []
        if i in anomaly_slots:
            if i == 10:
                # This one is impacted by the intentional API bug when active.
                amount = 25000.0
                profile = []
            elif i == 22:
                profile = ['missing_settlement']
            elif i == 34:
                profile = ['reconciliation_mismatch']
            elif i == 46:
                profile = ['delayed_posting']
            anomalies_seeded += 1
        payload = TransferCreate(
            source_account_id=src,
            beneficiary_account_id=dst,
            amount=amount,
            anomaly_profile=profile,
            narrative='AUTO_SEEDED_DEMO',
        )
        fake_req = type('Req', (), {'state': type('State', (), {'trace_id': trace_id})()})()
        create_transfer(payload=payload, request=fake_req, db=db)
        created += 1

    db.add(TransactionAuditLog(
        trace_id=trace_id,
        action='demo.seed.transactions',
        entity_type='transaction_demo',
        entity_id='seed-50',
        details=json.dumps({'created': created, 'anomalies_seeded': anomalies_seeded}),
    ))
    db.commit()
    total = db.query(func.count(TransferTransaction.id)).scalar() or 0
    return {'created': created, 'total_transfers': total, 'anomalies_seeded': anomalies_seeded}


@app.post('/transactions/demo/seed')
def seed_demo_transactions(request: Request, db: Session = Depends(get_db)):
    trace_id = request.state.trace_id
    out = _seed_demo_transactions_if_needed(db, trace_id)
    return {'status': 'ok', **out}


def _reset_demo_transactions(db: Session, trace_id: str):
    db.query(ReconciliationMismatch).delete()
    db.query(ReconciliationReport).delete()
    db.query(LedgerEntry).delete()
    db.query(SettlementRecord).delete()
    db.query(TransferTransaction).delete()

    defaults = {
        'DEMO-ACC-A': Decimal('1000000'),
        'DEMO-ACC-B': Decimal('250000'),
        'DEMO-ACC-C': Decimal('120000'),
    }
    accounts = db.query(TransactionAccount).filter(TransactionAccount.account_number.in_(list(defaults.keys()))).all()
    for acc in accounts:
        bal = defaults.get(acc.account_number, Decimal('0'))
        acc.available_balance = bal
        acc.ledger_balance = bal

    db.add(TransactionAuditLog(
        trace_id=trace_id,
        action='demo.reset.transactions',
        entity_type='transaction_demo',
        entity_id='reset-50',
        details='Cleared reconciliation/transfer data and reset demo balances.',
    ))
    db.commit()


@app.post('/transactions/demo/reset-seed')
def reset_seed_demo_transactions(request: Request, db: Session = Depends(get_db)):
    trace_id = request.state.trace_id
    _ensure_demo_entities(db, trace_id)
    _reset_demo_transactions(db, trace_id)
    out = _seed_demo_transactions_if_needed(db, trace_id)
    return {'status': 'ok', 'message': 'Demo dataset reset and reseeded', **out}


@app.get('/transactions/{transfer_id}')
def get_transfer(transfer_id: int, db: Session = Depends(get_db)):
    tx = db.query(TransferTransaction).filter(TransferTransaction.id == transfer_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail='Transfer not found')
    ledger = db.query(LedgerEntry).filter(LedgerEntry.transfer_id == transfer_id).all()
    settlement = db.query(SettlementRecord).filter(SettlementRecord.transfer_id == transfer_id).first()
    return {
        'transfer': _row_dict(tx),
        'ledger_entries': [_row_dict(x) for x in ledger],
        'settlement': _row_dict(settlement),
    }


@app.get('/transactions')
def list_transfers(limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.query(TransferTransaction).order_by(TransferTransaction.id.desc()).limit(limit).all()
    return [_row_dict(x) for x in rows]


def _add_mismatch(db: Session, report_id: int, transfer_id: int | None, mismatch_type: str, severity: str, details: str, root_cause: str):
    db.add(ReconciliationMismatch(
        report_id=report_id,
        transfer_id=transfer_id,
        mismatch_type=mismatch_type,
        severity=severity,
        details=details,
        impacted_services='transaction_management,settlement_processor,reconciliation_engine',
        root_cause_hint=root_cause,
    ))


@app.post('/reconciliation/run')
def run_reconciliation(payload: ReconciliationRun, request: Request, db: Session = Depends(get_db)):
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=payload.hours_back)

    transfers = db.query(TransferTransaction).filter(TransferTransaction.created_at >= start_time, TransferTransaction.created_at <= end_time).all()

    report = ReconciliationReport(
        report_ref=f'RECON-{int(time.time())}-{uuid.uuid4().hex[:6]}',
        window_start=start_time,
        window_end=end_time,
        status='COMPLETED',
        total_transfers=len(transfers),
        mismatch_count=0,
        missing_settlement_count=0,
        duplicate_count=0,
    )
    db.add(report)
    db.flush()

    seen_external_refs: dict[str, int] = {}
    mismatch_count = 0
    missing_count = 0
    dup_count = 0

    for tx in transfers:
        settlement = db.query(SettlementRecord).filter(SettlementRecord.transfer_id == tx.id).first()
        anomalies = set(json.loads(tx.anomaly_flags) if tx.anomaly_flags else [])

        if tx.external_ref:
            if tx.external_ref in seen_external_refs:
                dup_count += 1
                mismatch_count += 1
                _add_mismatch(
                    db,
                    report.id,
                    tx.id,
                    'DUPLICATE',
                    'HIGH',
                    f'Duplicate external_ref {tx.external_ref} found with transfer {seen_external_refs[tx.external_ref]}',
                    'Duplicate transaction created by replay without idempotency lock.',
                )
            else:
                seen_external_refs[tx.external_ref] = tx.id

        if tx.intended_beneficiary_account_id and tx.intended_beneficiary_account_id != tx.beneficiary_account_id:
            mismatch_count += 1
            _add_mismatch(
                db,
                report.id,
                tx.id,
                'WRONG_BENEFICIARY',
                'CRITICAL',
                f'Transfer posted to account {tx.beneficiary_account_id}, intended {tx.intended_beneficiary_account_id}',
                'Beneficiary mapping bug in transfer posting pipeline.',
            )

        if not settlement or settlement.settlement_status == 'MISSING':
            missing_count += 1
            mismatch_count += 1
            _add_mismatch(
                db,
                report.id,
                tx.id,
                'MISSING_SETTLEMENT',
                'CRITICAL',
                'Settlement record missing or marked missing.',
                'Settlement dispatcher dropped transaction event.',
            )
        elif Decimal(str(settlement.settled_amount)) != Decimal(str(settlement.expected_amount)):
            mismatch_count += 1
            _add_mismatch(
                db,
                report.id,
                tx.id,
                'AMOUNT_MISMATCH',
                'HIGH',
                f'Expected {settlement.expected_amount}, settled {settlement.settled_amount}',
                'Rounding/cutoff defect between core ledger and settlement system.',
            )

        if tx.status == 'POSTING_DELAYED' or 'delayed_posting' in anomalies:
            mismatch_count += 1
            _add_mismatch(
                db,
                report.id,
                tx.id,
                'DELAYED_POSTING',
                'MEDIUM',
                'Posting delayed beyond SLA threshold.',
                'Queue lag or stuck posting worker caused delayed update.',
            )

        if 'incorrect_debit_credit_mapping' in anomalies:
            mismatch_count += 1
            _add_mismatch(
                db,
                report.id,
                tx.id,
                'DEBIT_CREDIT_SWAP',
                'HIGH',
                'Debit/credit accounts swapped during posting.',
                'Ledger entry mapping defect in posting function.',
            )

    report.mismatch_count = mismatch_count
    report.missing_settlement_count = missing_count
    report.duplicate_count = dup_count

    db.add(TransactionAuditLog(
        trace_id=request.state.trace_id,
        action='reconciliation.run',
        entity_type='reconciliation_report',
        entity_id=str(report.id),
        details=json.dumps({'mismatch_count': mismatch_count, 'window_hours': payload.hours_back}),
    ))
    db.commit()
    db.refresh(report)

    METRICS['reconciliation_runs'] += 1
    METRICS['mismatches_detected'] += mismatch_count

    return _row_dict(report)


@app.get('/reconciliation/reports/{report_id}')
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(ReconciliationReport).filter(ReconciliationReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail='Report not found')
    mismatches = db.query(ReconciliationMismatch).filter(ReconciliationMismatch.report_id == report_id).order_by(ReconciliationMismatch.id.asc()).all()
    return {'report': _row_dict(report), 'mismatches': [_row_dict(x) for x in mismatches]}


@app.get('/reconciliation/reports')
def list_reports(limit: int = Query(default=20, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.query(ReconciliationReport).order_by(ReconciliationReport.generated_at.desc()).limit(limit).all()
    return [_row_dict(x) for x in rows]


@app.get('/reconciliation/reports/{report_id}/analysis')
def analyze_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    report = db.query(ReconciliationReport).filter(ReconciliationReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail='Report not found')
    mismatches = db.query(ReconciliationMismatch).filter(ReconciliationMismatch.report_id == report_id).all()
    if not mismatches:
        summary = 'No reconciliation mismatches detected for this report window.'
        return {'report_id': report_id, 'summary': summary, 'root_causes': [], 'impacted_services': []}

    counts: dict[str, int] = {}
    impacted = set()
    root_hints = []
    for row in mismatches:
        counts[row.mismatch_type] = counts.get(row.mismatch_type, 0) + 1
        if row.impacted_services:
            impacted.update(s.strip() for s in row.impacted_services.split(',') if s.strip())
        if row.root_cause_hint:
            root_hints.append(row.root_cause_hint)

    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    root_causes = [f'{k}: {v} occurrence(s)' for k, v in ranked]
    summary = (
        f'Reconciliation report {report.report_ref} found {report.mismatch_count} mismatches. '
        f'Top issue: {root_causes[0] if root_causes else "none"}. '
        'Likely defect path includes transaction posting, settlement dispatch, and reconciliation logic.'
    )

    report.analysis_summary = summary
    db.add(TransactionAuditLog(
        trace_id=request.state.trace_id,
        action='reconciliation.analyze',
        entity_type='reconciliation_report',
        entity_id=str(report.id),
        details=json.dumps({'root_causes': root_causes}),
    ))
    db.commit()

    return {
        'report_id': report_id,
        'summary': summary,
        'root_causes': root_causes,
        'root_cause_hints': root_hints[:10],
        'impacted_services': sorted(impacted),
        'suggested_trace_queries': [
            'SELECT * FROM transaction.transfers WHERE external_ref = <external_ref>;',
            'SELECT * FROM transaction.settlement_records WHERE transfer_id = <transfer_id>;',
            'SELECT * FROM transaction.ledger_entries WHERE transfer_id = <transfer_id> ORDER BY id;',
        ],
    }


@app.get('/observability/query-monitoring')
def query_monitoring():
    return {
        'db_query_count': METRICS['db_query_count'],
        'db_slow_queries': METRICS['db_slow_queries'],
        'slow_query_threshold_ms': 200,
    }


@app.get('/demo/bug-status')
def demo_bug_status():
    return {
        'beneficiary_routing_bug_active': BUG_STATE['beneficiary_routing_bug_active'],
        'delayed_posting_bug_active': BUG_STATE['delayed_posting_bug_active'],
        'code_patch_applied': CODE_PATCH_APPLIED,
        'description': 'Large transfer beneficiary routing bug in posting path',
    }


@app.post('/demo/bug/fix')
def demo_fix_bug(payload: BugFixRequest, request: Request, db: Session = Depends(get_db)):
    if payload.bug_key == 'beneficiary_routing_bug':
        BUG_STATE['beneficiary_routing_bug_active'] = False
    elif payload.bug_key == 'delayed_posting_bug':
        BUG_STATE['delayed_posting_bug_active'] = False
    else:
        raise HTTPException(status_code=400, detail='Unsupported bug key')
    db.add(TransactionAuditLog(
        trace_id=request.state.trace_id,
        action='demo.bug.fix',
        entity_type='transaction_demo',
        entity_id=payload.bug_key,
        details=json.dumps({'resolved_by': payload.resolved_by, 'notes': payload.notes}),
    ))
    db.commit()
    return {
        'status': 'fixed',
        'bug_key': payload.bug_key,
        'beneficiary_routing_bug_active': BUG_STATE['beneficiary_routing_bug_active'],
        'delayed_posting_bug_active': BUG_STATE['delayed_posting_bug_active'],
    }


@app.post('/demo/bug/fix-code')
def demo_fix_bug_code(payload: BugFixRequest, request: Request, db: Session = Depends(get_db)):
    if payload.bug_key == 'delayed_posting_bug':
        now = datetime.now(timezone.utc)
        patched = (
            db.query(TransferTransaction)
            .filter(TransferTransaction.status == 'POSTING_DELAYED')
            .update(
                {
                    TransferTransaction.status: 'POSTED',
                    TransferTransaction.posted_at: now,
                    TransferTransaction.settled_at: now,
                },
                synchronize_session=False,
            )
        )
        BUG_STATE['delayed_posting_bug_active'] = False
        db.add(TransactionAuditLog(
            trace_id=request.state.trace_id,
            action='demo.bug.fix_code',
            entity_type='transaction_demo',
            entity_id=payload.bug_key,
            details=json.dumps({'resolved_by': payload.resolved_by, 'notes': payload.notes, 'patched_transactions': int(patched)}),
        ))
        db.commit()
        return {
            'status': 'fixed',
            'mode': 'data_repair',
            'bug_key': payload.bug_key,
            'patched_transactions': int(patched),
            'beneficiary_routing_bug_active': BUG_STATE['beneficiary_routing_bug_active'],
            'delayed_posting_bug_active': BUG_STATE['delayed_posting_bug_active'],
        }

    if payload.bug_key != 'beneficiary_routing_bug':
        raise HTTPException(status_code=400, detail='Unsupported bug key')

    source_path = Path(__file__)
    content = source_path.read_text(encoding='utf-8')
    before_line = "CODE_PATCH_APPLIED = False"
    after_line = "CODE_PATCH_APPLIED = True"
    if after_line in content:
        already = True
    elif before_line in content:
        content = content.replace(before_line, after_line, 1)
        source_path.write_text(content, encoding='utf-8')
        already = False
    else:
        raise HTTPException(status_code=500, detail='Could not locate patch marker in source file')

    BUG_STATE['beneficiary_routing_bug_active'] = False
    db.add(TransactionAuditLog(
        trace_id=request.state.trace_id,
        action='demo.bug.fix_code',
        entity_type='transaction_demo',
        entity_id=payload.bug_key,
        details=json.dumps({'resolved_by': payload.resolved_by, 'notes': payload.notes, 'already_patched': already}),
    ))
    db.commit()
    return {
        'status': 'fixed',
        'mode': 'code_patch',
        'bug_key': payload.bug_key,
        'already_patched': already,
        'patched_file': str(source_path),
        'changed_from': before_line,
        'changed_to': after_line,
        'beneficiary_routing_bug_active': False,
    }


@app.post('/demo/bug/reset')
def demo_reset_bug(payload: BugResetRequest, request: Request, db: Session = Depends(get_db)):
    if payload.bug_key == 'beneficiary_routing_bug':
        BUG_STATE['beneficiary_routing_bug_active'] = True
    elif payload.bug_key == 'delayed_posting_bug':
        BUG_STATE['delayed_posting_bug_active'] = True
    else:
        raise HTTPException(status_code=400, detail='Unsupported bug key')
    db.add(TransactionAuditLog(
        trace_id=request.state.trace_id,
        action='demo.bug.reset',
        entity_type='transaction_demo',
        entity_id=payload.bug_key,
        details='Intentional beneficiary routing bug re-enabled for demo baseline.',
    ))
    db.commit()
    return {
        'status': 'reset',
        'bug_key': payload.bug_key,
        'beneficiary_routing_bug_active': BUG_STATE['beneficiary_routing_bug_active'],
        'delayed_posting_bug_active': BUG_STATE['delayed_posting_bug_active'],
    }


@app.post('/demo/bug/reset-code')
def demo_reset_bug_code(payload: BugResetRequest, request: Request, db: Session = Depends(get_db)):
    source_path = Path(__file__)
    content = source_path.read_text(encoding='utf-8')
    before_line = "CODE_PATCH_APPLIED = True"
    after_line = "CODE_PATCH_APPLIED = False"
    if after_line in content:
        already = True
    elif before_line in content:
        content = content.replace(before_line, after_line, 1)
        source_path.write_text(content, encoding='utf-8')
        already = False
    else:
        raise HTTPException(status_code=500, detail='Could not locate patch marker in source file')

    BUG_STATE['beneficiary_routing_bug_active'] = True
    db.add(TransactionAuditLog(
        trace_id=request.state.trace_id,
        action='demo.bug.reset_code',
        entity_type='transaction_demo',
        entity_id=payload.bug_key,
        details=json.dumps({'already_reset': already}),
    ))
    db.commit()
    return {
        'status': 'reset',
        'mode': 'code_patch',
        'already_reset': already,
        'patched_file': str(source_path),
        'changed_from': before_line,
        'changed_to': after_line,
        'beneficiary_routing_bug_active': True,
    }


@app.on_event('startup')
def startup_seed():
    auto_seed = os.getenv('TX_DEMO_AUTO_SEED_ON_START', 'true').lower() in {'1', 'true', 'yes', 'on'}
    if not auto_seed:
        return
    db = next(get_db())
    try:
        trace_id = str(uuid.uuid4())
        _ensure_demo_entities(db, trace_id)
        _seed_demo_transactions_if_needed(db, trace_id)
    finally:
        db.close()
