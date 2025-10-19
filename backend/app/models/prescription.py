# app/models/prescription.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.db import Base
import json


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    # Clinical details
    diagnosis = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    doctor_name = Column(String(100), nullable=True)

    # Medicines are stored as JSON string
    medicines_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship for joins
    patient = relationship("Patient", back_populates="prescriptions", lazy="joined")

    # ------------------------------------------------------------------
    # Helpers for parsing / exporting medicines
    # ------------------------------------------------------------------
    def medicines(self):
        """Return list of medicine dicts from stored JSON."""
        try:
            meds = json.loads(self.medicines_json or "[]")
            return meds if isinstance(meds, list) else []
        except Exception:
            return []

    def set_medicines(self, medicines_list):
        """Accepts a Python list and stores it as JSON string."""
        try:
            self.medicines_json = json.dumps(medicines_list, ensure_ascii=False)
        except Exception:
            self.medicines_json = "[]"

    def summary(self):
        """Readable summary for debugging or dashboards."""
        meds = self.medicines()
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "doctor_name": self.doctor_name or "",
            "diagnosis": self.diagnosis or "",
            "notes": (self.notes or "")[:120],
            "medicine_count": len(meds),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Prescription(id={self.id}, doctor={self.doctor_name}, patient_id={self.patient_id})>"