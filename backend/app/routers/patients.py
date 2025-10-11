# backend/app/routers/patients.py
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import os, csv, re

from ..core.db import get_db
from ..models.patient import Patient

router = APIRouter(tags=["Public / Patients"])
templates = Jinja2Templates(directory="app/templates")

# CSV for prescriptions
PRESCRIPTIONS_CSV = "app/static/data/prescriptions.csv"
os.makedirs(os.path.dirname(PRESCRIPTIONS_CSV), exist_ok=True)

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
                    ts = row.get("Timestamp", "")
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
    result.sort(key=lambda x: x.get("Date", ""), reverse=True)
    return result


# -------------------------------
# Step 1️⃣ — Patient QR Landing Page
# -------------------------------
@router.get("/p/{patient_uid}", response_class=HTMLResponse)
def public_patient_entry(request: Request, patient_uid: str, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Render hospital name + phone/OTP entry page
    return templates.TemplateResponse(
        "verify_number.html",
        {"request": request, "patient": patient, "error": None},
    )


# -------------------------------
# Step 2️⃣ — Verify (Fixed OTP Flow)
# -------------------------------
@router.post("/p/verify", response_class=HTMLResponse)
def verify_fixed_otp(
    request: Request,
    patient_uid: str = Form(...),
    phone: str = Form(...),
    otp: str = Form(...),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # ✅ Check phone and fixed OTP = 1234
    if phone.strip() != str(patient.phone).strip():
        return templates.TemplateResponse(
            "verify_number.html",
            {"request": request, "patient": patient, "error": "Phone number mismatch."},
        )

    if otp.strip() != "1234":
        return templates.TemplateResponse(
            "verify_number.html",
            {"request": request, "patient": patient, "error": "Invalid OTP. Use 1234 for demo."},
        )

    # Success — show dashboard
    prescriptions = load_prescriptions_for(patient_uid)
    height = None
    if patient.height:
        height = re.sub(r"(ft|feet)+", "ft", patient.height.strip(), flags=re.IGNORECASE)

    return templates.TemplateResponse(
        "patient_details.html",
        {
            "request": request,
            "patient": patient,
            "height": height,
            "verified": True,
            "prescriptions": prescriptions,
        },
    )