from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.shared.db.database import get_db
from backend.shared.models.entities import Customer, DisbursementTransaction, LoanApplication

app = FastAPI(title="Loan Disbursement Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoanCreate(BaseModel):
    customer_id: int
    loan_type: str
    requested_amount: float
    tenure_months: int


class ApproveLoan(BaseModel):
    approved_amount: float
    interest_rate: float
    sanction_notes: str


class DisburseLoan(BaseModel):
    disbursed_amount: float
    mode: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/loans")
def create_loan(payload: LoanCreate, db: Session = Depends(get_db)):
    if not db.query(Customer).filter(Customer.id == payload.customer_id).first():
        raise HTTPException(status_code=404, detail="Customer not found")
    loan = LoanApplication(
        loan_ref=f"LOAN-{payload.customer_id}-{payload.tenure_months}",
        **payload.model_dump(),
        status="SUBMITTED",
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return loan


@app.patch("/loans/{loan_id}/approve")
def approve_loan(loan_id: int, payload: ApproveLoan, db: Session = Depends(get_db)):
    loan = db.query(LoanApplication).filter(LoanApplication.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    loan.approved_amount = payload.approved_amount
    loan.interest_rate = payload.interest_rate
    loan.sanction_notes = payload.sanction_notes
    loan.status = "APPROVED"
    db.commit()
    db.refresh(loan)
    return loan


@app.post("/loans/{loan_id}/disburse")
def disburse_loan(loan_id: int, payload: DisburseLoan, db: Session = Depends(get_db)):
    loan = db.query(LoanApplication).filter(LoanApplication.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    txn = DisbursementTransaction(
        loan_id=loan_id,
        txn_ref=f"TXN-LOAN-{loan_id}-{int(payload.disbursed_amount)}",
        disbursed_amount=payload.disbursed_amount,
        mode=payload.mode,
        status="SUCCESS",
    )
    loan.status = "DISBURSED"
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@app.get("/loans")
def list_loans(db: Session = Depends(get_db)):
    return db.query(LoanApplication).order_by(LoanApplication.id.desc()).all()
