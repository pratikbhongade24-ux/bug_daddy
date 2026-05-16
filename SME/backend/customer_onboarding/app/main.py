from datetime import date
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.shared.db.database import get_db
from backend.shared.models.entities import Customer

app = FastAPI(title="Customer Onboarding Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CustomerCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    dob: date
    employment_type: str
    annual_income: float
    credit_score: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/customers")
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    customer = Customer(
        customer_ref=f"CUST-{payload.phone[-4:]}-{payload.credit_score}",
        **payload.model_dump(),
        eligibility_status="ELIGIBLE" if payload.credit_score >= 700 else "REVIEW",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@app.get("/customers")
def list_customers(db: Session = Depends(get_db)):
    return db.query(Customer).order_by(Customer.id.desc()).all()


@app.get("/customers/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer
