# backend/app/models/payment.py
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from datetime import datetime

from ..core.db import Base

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    doctor_id  = Column(Integer, ForeignKey("doctors.id"), nullable=True)

    amount  = Column(Float, default=0.0, nullable=False)
    status  = Column(String(20), default="paid")     # "paid" | "pending" | "failed"
    method  = Column(String(30), default="cash")     # "cash" | "card" | "upi" | etc.
    ref     = Column(String(120), default="")        # optional reference/txn id
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)