from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import os, csv, random, time

from ..core.db import get_db
from ..models.patient import Patient

router = APIRouter(tags=["Public / Patients"])

templates = Jinja2Templates(directory="app/templates")

# CSV where prescriptions are stored (already used by doctor flow)
PRESCRIPTIONS_CSV = "app/static/data/prescriptions.csv"
os.makedirs(os.path.dirname(PRESCRIPTIONS_CSV), exist_ok=True)

# In-memory OTP store: { "<uid>|<phone>": (otp_code:str, expires_at:float) }
otp_store: dict[str, tuple[str, float]] = {}

# -------------------------------
# Helper: read prescriptions
# -------------------------------
def load_prescriptions_for(uid: str):
    """Return list of prescriptions dicts for given patient UID, newest first."""
    result = []
    if os.path.exists(PRESCRIPTIONS_CSV):
        with open(PRESCRIPTIONS_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("PatientUID") == uid:
                    # Keep only the fields we want to show now
                    ts = row.get("Timestamp", "")
                    # Format date only (e.g., 07 Oct 2025)
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", ""))
                        date_str = dt.strftime("%d %b %Y")
                    except Exception:
                        date_str = ts

                    result.append({
                        "Diagnosis": row.get("Diagnosis", ""),
                        "Prescription": row.get("Prescription", ""),
                        "Date": date_str,
                    })
    # Newest first by timestamp if present
    result.sort(key=lambda x: x.get("Date", ""), reverse=True)
    return result


# -------------------------------
# Public Patient Page (QR Landing)
# -------------------------------
@router.get("/p/{patient_uid}", response_class=HTMLResponse)
def public_patient_card(
    request: Request,
    patient_uid: str,
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Is patient verified for this browser?
    verified = request.cookies.get(f"p_auth_{patient_uid}") == "1"

    prescriptions = load_prescriptions_for(patient_uid) if verified else []

    # Normalized height (avoid double 'ft')
    height = None
    if patient.height:
        import re
        height = (
            re.sub(r"(ft|feet)+", "ft", patient.height.strip(), flags=re.IGNORECASE)
            .replace("  ", " ")
            .strip()
        )

    return templates.TemplateResponse(
        "patient.html",
        {
            "request": request,
            "patient": patient,
            "height": height,
            "verified": verified,
            "prescriptions": prescriptions,
            "status": request.query_params.get("status", ""),
            "error": request.query_params.get("error", ""),
        },
    )


# -------------------------------
# Send OTP (Patient)
# -------------------------------
@router.post("/p/send-otp")
def send_patient_otp(
    patient_uid: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Phone must match registered phone
    if phone.strip() != str(patient.phone).strip():
        return JSONResponse({"ok": False, "message": "Phone number does not match our records."}, status_code=400)

    # Generate 6-digit OTP
    otp = f"{random.randint(100000, 999999)}"
    expires_at = time.time() + 5 * 60  # 5 minutes validity
    otp_store[f"{patient_uid}|{phone}"] = (otp, expires_at)

    # Demo: print OTP to server logs (simulate SMS)
    print(f"[OTP] PatientUID={patient_uid} Phone={phone} OTP={otp} (valid 5 min)")

    return JSONResponse({"ok": True, "message": "OTP sent successfully."})


# -------------------------------
# Verify OTP (Patient)
# -------------------------------
@router.post("/p/verify-otp")
def verify_patient_otp(
    request: Request,
    patient_uid: str = Form(...),
    phone: str = Form(...),
    otp: str = Form(...),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    key = f"{patient_uid}|{phone}"
    if key not in otp_store:
        # No OTP requested or expired from store
        return RedirectResponse(
            url=f"/p/{patient_uid}?error=No+active+OTP.+Please+request+again",
            status_code=303,
        )

    saved_code, expires_at = otp_store[key]
    if time.time() > expires_at:
        del otp_store[key]
        return RedirectResponse(
            url=f"/p/{patient_uid}?error=OTP+expired.+Please+resend",
            status_code=303,
        )

    if str(saved_code) != str(otp).strip():
        return RedirectResponse(
            url=f"/p/{patient_uid}?error=Invalid+OTP.+Try+again",
            status_code=303,
        )

    # Success — clear store, set a verification cookie
    del otp_store[key]
    resp = RedirectResponse(url=f"/p/{patient_uid}?status=Verified", status_code=303)
    # Keep the session for 1 day (you can reduce if you prefer)
    max_age = int(timedelta(days=1).total_seconds())
    resp.set_cookie(key=f"p_auth_{patient_uid}", value="1", max_age=max_age, httponly=True, samesite="Lax")
    return resp