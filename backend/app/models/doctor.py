from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from ..core.db import Base


class Doctor(Base):
    __tablename__ = "doctors"

    # --- Primary identifiers ---
    id = Column(Integer, primary_key=True, index=True)

    # --- Basic info ---
    username = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=True)
    specialization = Column(String(100), nullable=True)
    license_no = Column(String(50), nullable=True)

    # --- Auth info ---
    password = Column(String(128), nullable=False)
    password_hash = Column(String(255), nullable=True)
    status = Column(String(20), default="pending")  # pending | approved | rejected

    # --- Timestamp ---
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Relationship with patients ---
    patients = relationship(
        "Patient",
        back_populates="doctor",
        cascade="all, delete-orphan",
        lazy="joined"
    )

    # --- String representation ---
    def __repr__(self):
        return (
            f"<Doctor(id={self.id}, name='{self.name}', username='{self.username}', "
            f"department='{self.department}', status='{self.status}')>"
        )