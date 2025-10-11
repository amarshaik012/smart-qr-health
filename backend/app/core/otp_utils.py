import random
from ..core.db import SessionLocal
from ..models.otp_log import OTPLog

def generate_otp(phone: str):
    """Generate a random OTP and store it in the database."""
    otp = str(random.randint(100000, 999999))
    print(f"[DEBUG] OTP for {phone}: {otp}")  # Free console display
    db = SessionLocal()
    db.add(OTPLog(phone=phone, otp=otp))
    db.commit()
    db.close()
    return otp

def verify_otp(phone: str, entered_otp: str) -> bool:
    """Verify the entered OTP against the most recent one."""
    db = SessionLocal()
    record = (
        db.query(OTPLog)
        .filter(OTPLog.phone == phone)
        .order_by(OTPLog.created_at.desc())
        .first()
    )
    valid = record and record.otp == entered_otp
    if valid:
        record.verified = True
        db.commit()
    db.close()
    return valid