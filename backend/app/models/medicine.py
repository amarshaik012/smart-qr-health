from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from ..core.db import Base


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)

    # Identity
    name = Column(String(120), nullable=False, index=True)
    strength = Column(String(60), nullable=True)
    form = Column(String(40), nullable=True)

    # Commercials
    mrp = Column(Float, nullable=True, default=0.0)
    tax_pct = Column(Float, nullable=True, default=0.0)

    # Inventory
    stock_qty = Column(Integer, nullable=False, default=0)
    reorder_level = Column(Integer, nullable=False, default=0)

    # Extra for CSV / compatibility
    batch_no = Column(String(100), nullable=True)
    expiry_date = Column(String(20), nullable=True)
    manufacturer = Column(String(120), nullable=True)

    # ---- Convenience aliases ----
    @property
    def qty_available(self) -> int:
        return self.stock_qty or 0

    @qty_available.setter
    def qty_available(self, value: int):
        self.stock_qty = value

    @property
    def is_low_stock(self) -> bool:
        """Return True if below or equal to reorder level."""
        try:
            return int(self.stock_qty or 0) <= int(self.reorder_level or 0)
        except Exception:
            return False

    @property
    def inventory_value(self) -> float:
        """Approximate total stock value (MRP * qty)."""
        try:
            return float(self.mrp or 0.0) * int(self.stock_qty or 0)
        except Exception:
            return 0.0

    # ---- Labels & representation ----
    def label(self) -> str:
        """Readable label for dropdowns or printouts."""
        parts = [self.name or ""]
        if self.strength:
            parts.append(self.strength)
        if self.form:
            parts.append(self.form)
        return " ".join([p for p in parts if p]).strip()

    def __repr__(self):
        return (
            f"<Medicine(name={self.name}, stock={self.stock_qty}, "
            f"batch_no={self.batch_no}, expiry={self.expiry_date})>"
        )

    # ---- Timestamps ----
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())