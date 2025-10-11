from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import os, csv, re

from ..core.db import get_db
from ..models.patient import Patient

router = APIRouter(tags=["Public / Patients"])

# ------------------------------------------------------
# ✅ Render & Local Path Setup
# ------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DATA_DIR = os.path.join(BASE_DIR, "static", "data")

os.makedirs(STATIC_DATA_DIR, exist_ok=True)
PRESCRIPTIONS_CSV = os.path.join(STATIC_DATA_DIR, "prescriptions.csv")
open(PRESCRIPTIONS_CSV, "a").close()

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ------------------------------------------------------
# 📄 Load Patient Prescriptions
# ------------------------------------------------------
def load_prescriptions_for(uid: str):
    """Fetch prescriptions for a given patient UID."""
    results = []
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
                    results.append({
                        "Diagnosis": row.get("Diagnosis", ""),
                        "Prescription": row.get("Prescription", ""),
                        "Date": date_str,
                    })
    results.sort(key=lambda x: x.get("Date", ""), reverse=True)
    return results


# ------------------------------------------------------
# 🧾 Step 1 — Patient QR Landing Page
# ------------------------------------------------------
@router.get("/p/{patient_uid}", response_class=HTMLResponse)
def patient_verification_page(request: Request, patient_uid: str, db: Session = Depends(get_db)):
    """When patient scans their QR, show verification form."""
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    return templates.TemplateResponse(
        "verify_number.html",
        {
            "request": request,
            "patient": patient,
            "error": ""
        }
    )


# ------------------------------------------------------
# 🔐 Step 2 — Verify Phone + OTP (Fixed OTP for Demo)
# ------------------------------------------------------
@router.post("/p/verify", response_class=HTMLResponse)
def verify_patient(
    request: Request,
    patient_uid: str = Form(...),
    phone: str = Form(...),
    otp: str = Form(...),
    db: Session = Depends(get_db),
):
    """Validate phone number and demo OTP, then show dashboard."""
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Validate phone number
    if phone.strip() != str(patient.phone).strip():
        return templates.TemplateResponse(
            "verify_number.html",
            {"request": request, "patient": patient, "error": "❌ Phone number not registered."},
        )

    # Fixed OTP for demo mode
    if otp.strip() != "1234":
        return templates.TemplateResponse(
            "verify_number.html",
            {"request": request, "patient": patient, "error": "❌ Invalid OTP. Use 1234 for demo."},
        )

    # ✅ Success — load prescriptions
    prescriptions = load_prescriptions_for(patient_uid)
    height = re.sub(r"(ft|feet)+", "ft", patient.height.strip(), flags=re.IGNORECASE) if patient.height else None

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