from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from ..core.db import Base

class OTPLog(Base):
    __tablename__ = "otp_logs"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, index=True)
    otp = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    verified = Column(Boolean, default=False)