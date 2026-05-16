from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.shared.db.database import get_db
from backend.shared.models.entities import Customer, KYCRecord

app = FastAPI(title="KYC Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class KycCreate(BaseModel):
    customer_id: int
    document_type: str
    document_number: str
    document_url: str


class KycStatusUpdate(BaseModel):
    status: str
    reviewer_notes: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/kyc")
def upload_kyc(payload: KycCreate, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == payload.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    rec = KYCRecord(**payload.model_dump(), status="UNDER_REVIEW")
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@app.patch("/kyc/{kyc_id}")
def update_kyc_status(kyc_id: int, payload: KycStatusUpdate, db: Session = Depends(get_db)):
    rec = db.query(KYCRecord).filter(KYCRecord.id == kyc_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="KYC record not found")
    rec.status = payload.status
    rec.reviewer_notes = payload.reviewer_notes
    db.commit()
    db.refresh(rec)
    return rec


@app.get("/kyc")
def list_kyc(db: Session = Depends(get_db)):
    return db.query(KYCRecord).order_by(KYCRecord.id.desc()).all()
