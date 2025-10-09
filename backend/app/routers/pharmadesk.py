# backend/app/routers/pharmadesk.py
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND
from sqlalchemy.orm import Session
from datetime import datetime, date
import os, csv

from ..core.db import get_db
from ..models.patient import Patient

router = APIRouter(prefix="/pharmadesk", tags=["PharmaDesk"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({"datetime": datetime})

# -------------------------------
# Constants & Paths
# -------------------------------
PRESCRIPTIONS_CSV = "app/static/data/prescriptions.csv"
DISPENSED_CSV = "app/static/data/dispensed.csv"
os.makedirs(os.path.dirname(PRESCRIPTIONS_CSV), exist_ok=True)
os.makedirs(os.path.dirname(DISPENSED_CSV), exist_ok=True)

PHARMA_USERNAME = "pharmadesk"
PHARMA_PASSWORD = "pharma123"

# -------------------------------
# Auth Helpers
# -------------------------------
def _auth_guard(request: Request) -> bool:
    return request.cookies.get("pharma_auth") == "true"


# -------------------------------
# 🔐 Login / Logout
# -------------------------------
@router.get("/login", response_class=HTMLResponse)
def pharma_login_page(request: Request):
    return templates.TemplateResponse(
        "pharmadesk/login.html",
        {"request": request, "error": None}
    )


@router.post("/login", response_class=HTMLResponse)
def pharma_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == PHARMA_USERNAME and password == PHARMA_PASSWORD:
        resp = RedirectResponse(url="/pharmadesk/dashboard", status_code=HTTP_302_FOUND)
        resp.set_cookie(key="pharma_auth", value="true", httponly=True)
        return resp
    return templates.TemplateResponse(
        "pharmadesk/login.html",
        {"request": request, "error": "Invalid credentials"}
    )


@router.get("/logout")
def pharma_logout():
    resp = RedirectResponse(url="/pharmadesk/login", status_code=HTTP_302_FOUND)
    resp.delete_cookie("pharma_auth")
    return resp


# -------------------------------
# 🏠 Dashboard - Scan / Stats
# -------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def pharma_dashboard(request: Request):
    if not _auth_guard(request):
        return RedirectResponse(url="/pharmadesk/login", status_code=HTTP_302_FOUND)

    # --- Calculate Summary Stats ---
    total_dispensed = 0
    dispensed_today = 0
    today_str = date.today().isoformat()

    if os.path.exists(DISPENSED_CSV):
        with open(DISPENSED_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_dispensed += 1
                if row.get("DispensedOn", "").startswith(today_str):
                    dispensed_today += 1

    return templates.TemplateResponse(
        "pharmadesk/dashboard.html",
        {
            "request": request,
            "total_dispensed": total_dispensed,
            "dispensed_today": dispensed_today,
        },
    )


# -------------------------------
# 🔍 Resolve (QR/UID input)
# -------------------------------
@router.post("/resolve")
def pharma_resolve(request: Request, uid: str = Form(...)):
    if not _auth_guard(request):
        return RedirectResponse(url="/pharmadesk/login", status_code=HTTP_302_FOUND)

    uid = (uid or "").strip()
    if not uid:
        return RedirectResponse(url="/pharmadesk/dashboard", status_code=HTTP_302_FOUND)

    return RedirectResponse(url=f"/pharmadesk/prescription/{uid}", status_code=HTTP_302_FOUND)


# -------------------------------
# 📋 View Prescription
# -------------------------------
@router.get("/prescription/{patient_uid}", response_class=HTMLResponse)
def pharma_view_prescription(request: Request, patient_uid: str, db: Session = Depends(get_db)):
    if not _auth_guard(request):
        return RedirectResponse(url="/pharmadesk/login", status_code=HTTP_302_FOUND)

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    latest = None
    if os.path.exists(PRESCRIPTIONS_CSV):
        with open(PRESCRIPTIONS_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("PatientUID") == patient_uid:
                    if (not latest) or (row["Timestamp"] > latest["Timestamp"]):
                        latest = row

    dispensed_on, dispensed_by = None, None
    if os.path.exists(DISPENSED_CSV):
        with open(DISPENSED_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("PatientUID") == patient_uid:
                    dispensed_on = row["DispensedOn"]
                    dispensed_by = row.get("DispensedBy", "")

    return templates.TemplateResponse(
        "pharmadesk/view.html",
        {
            "request": request,
            "patient": patient,
            "prescription": latest,
            "dispensed_on": dispensed_on,
            "dispensed_by": dispensed_by,
        },
    )


# -------------------------------
# ✅ Mark as Dispensed
# -------------------------------
@router.post("/dispense/{patient_uid}")
def pharma_mark_dispensed(request: Request, patient_uid: str, db: Session = Depends(get_db)):
    if not _auth_guard(request):
        return RedirectResponse(url="/pharmadesk/login", status_code=HTTP_302_FOUND)

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    file_exists = os.path.isfile(DISPENSED_CSV)
    with open(DISPENSED_CSV, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["PatientUID", "Name", "DispensedOn", "DispensedBy"])
        writer.writerow([
            patient.patient_uid,
            patient.name,
            datetime.utcnow().isoformat(),
            PHARMA_USERNAME,
        ])

    return RedirectResponse(url=f"/pharmadesk/prescription/{patient_uid}", status_code=HTTP_302_FOUND)