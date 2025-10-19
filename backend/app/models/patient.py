from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.db import Base


class Patient(Base):
    __tablename__ = "patients"

    # --- Primary identifiers ---
    id = Column(Integer, primary_key=True, index=True)
    patient_uid = Column(String(50), unique=True, nullable=False, index=True)

    # --- Basic details ---
    name = Column(String(100), nullable=False)
    phone = Column(String(15), unique=True, nullable=False)
    email = Column(String(100), nullable=True)
    gender = Column(String(10), nullable=True)
    dob = Column(String(20), nullable=True)

    # --- Additional health details ---
    weight = Column(String(20), nullable=True)
    height = Column(String(20), nullable=True)

    # --- Doctor assignment ---
    assigned_doctor = Column(String(100), nullable=True)  # Doctor name for quick filter
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)

    # --- Consultation status ---
    status = Column(String(20), default="waiting")  # waiting | done | reviewing

    # --- ORM Relationship (link to Doctor model) ---
    doctor = relationship("Doctor", back_populates="patients", lazy="joined")

    # --- Prescriptions relationship ---
    prescriptions = relationship("Prescription", back_populates="patient", cascade="all, delete-orphan")

    # --- QR info ---
    qr_filename = Column(String(255), nullable=True)

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return (
            f"<Patient(id={self.id}, name='{self.name}', phone='{self.phone}', "
            f"doctor='{self.assigned_doctor}', uid='{self.patient_uid}', status='{self.status}')>"
        )