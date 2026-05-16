from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.shared.db.database import get_db
from backend.shared.models.entities import EMISchedule, LoanApplication, RepaymentTransaction

app = FastAPI(title="Repayment Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmiGenerate(BaseModel):
    loan_id: int


class RepaymentCreate(BaseModel):
    emi_id: int
    paid_amount: float
    channel: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/emis/generate")
def generate_schedule(payload: EmiGenerate, db: Session = Depends(get_db)):
    loan = db.query(LoanApplication).filter(LoanApplication.id == payload.loan_id).first()
    if not loan or not loan.approved_amount:
        raise HTTPException(status_code=400, detail="Loan not approved")

    monthly = float(loan.approved_amount) / loan.tenure_months
    existing = db.query(EMISchedule).filter(EMISchedule.loan_id == loan.id).count()
    if existing:
        return {"message": "Schedule already exists"}

    for i in range(1, loan.tenure_months + 1):
        emi = EMISchedule(
            loan_id=loan.id,
            installment_no=i,
            due_date=date.today() + timedelta(days=30 * i),
            principal_component=round(monthly * 0.85, 2),
            interest_component=round(monthly * 0.15, 2),
            total_due=round(monthly, 2),
        )
        db.add(emi)
    db.commit()
    return {"message": "EMI schedule generated"}


@app.post("/repayments")
def make_repayment(payload: RepaymentCreate, db: Session = Depends(get_db)):
    emi = db.query(EMISchedule).filter(EMISchedule.id == payload.emi_id).first()
    if not emi:
        raise HTTPException(status_code=404, detail="EMI not found")

    txn = RepaymentTransaction(
        emi_id=emi.id,
        payment_ref=f"PAY-{emi.id}-{int(payload.paid_amount)}",
        paid_amount=payload.paid_amount,
        channel=payload.channel,
    )
    emi.paid_amount = float(emi.paid_amount) + payload.paid_amount
    emi.payment_status = "PAID" if float(emi.paid_amount) >= float(emi.total_due) else "DUE"

    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@app.get("/emis")
def list_emis(db: Session = Depends(get_db)):
    rows = db.query(EMISchedule).order_by(EMISchedule.due_date.asc()).all()
    today = date.today()
    for row in rows:
        if row.payment_status == "DUE" and row.due_date < today:
            row.payment_status = "OVERDUE"
    db.commit()
    return rows
