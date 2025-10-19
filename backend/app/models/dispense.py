from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.db import Base


class Dispense(Base):
    __tablename__ = "dispenses"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=True)

    # Line values
    qty = Column(Integer, nullable=False, default=0)
    unit_price = Column(Float, nullable=False, default=0.0)
    discount_pct = Column(Float, nullable=False, default=0.0)
    tax_pct = Column(Float, nullable=False, default=0.0)
    total_amount = Column(Float, nullable=False, default=0.0)

    # Additional fields
    pharmacist = Column(String(80), nullable=True)
    payment_mode = Column(String(50), nullable=True)  # Cash / Card / UPI
    notes = Column(Text, nullable=True)

    # ✅ New column to store all dispensed items (medicine list)
    items_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ORM relations
    patient = relationship("Patient", lazy="joined")
    medicine = relationship("Medicine", lazy="joined")