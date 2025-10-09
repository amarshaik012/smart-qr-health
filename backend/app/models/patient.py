from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from ..core.db import Base


class Patient(Base):
    __tablename__ = "patients"

    # --- Primary identifiers ---
    id = Column(Integer, primary_key=True, index=True)
    patient_uid = Column(String(50), unique=True, nullable=False, index=True)

    # --- Basic details ---
    name = Column(String(100), nullable=False)
    phone = Column(String(15), unique=True, nullable=False)
    email = Column(String(100), nullable=False)
    gender = Column(String(10), nullable=True)
    dob = Column(String(20), nullable=True)

    # --- Additional health details ---
    weight = Column(String(20), nullable=True)
    height = Column(String(20), nullable=True)

    # --- QR info ---
    qr_filename = Column(String(255), nullable=True)

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Patient(name='{self.name}', phone='{self.phone}', uid='{self.patient_uid}')>"