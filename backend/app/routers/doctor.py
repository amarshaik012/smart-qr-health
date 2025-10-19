# app/routers/doctor.py
from __future__ import annotations
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Dict, Any, Optional
import csv, json
from pathlib import Path

from ..core.db import get_db
from ..models.patient import Patient
from ..models.medicine import Medicine
from ..models.prescription import Prescription
from ..models.doctor import Doctor

# -----------------------------------------------------------------------------
# Password hashing helpers
# -----------------------------------------------------------------------------
try:
    from passlib.hash import bcrypt as _bcrypt_hash
except Exception:
    _bcrypt_hash = None


def _hash_password(pw: str) -> str:
    if not pw:
        return ""
    if _bcrypt_hash:
        try:
            return _bcrypt_hash.hash(pw)
        except Exception:
            pass
    return "plain:" + pw


def _verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    if hashed.startswith("plain:"):
        return hashed == ("plain:" + plain)
    if _bcrypt_hash:
        try:
            return _bcrypt_hash.verify(plain, hashed)
        except Exception:
            return False
    return False


# -----------------------------------------------------------------------------
# Router setup
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/doctor", tags=["Doctor"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({"datetime": datetime})

DATA_DIR = Path("app/static/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
PRESCRIPTIONS_CSV = DATA_DIR / "prescriptions.csv"
print(f"[Doctor] Using prescription file: {PRESCRIPTIONS_CSV}")

COOKIE_NAME = "doctor_auth"


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
def _get_current_doctor(request: Request, db: Session) -> Optional[Doctor]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        doctor_id = int(raw)
    except Exception:
        return None
    return db.query(Doctor).filter(Doctor.id == doctor_id).first()


def _require_doctor(request: Request, db: Session) -> Doctor:
    doc = _get_current_doctor(request, db)
    if not doc:
        raise HTTPException(status_code=401, detail="Not logged in")
    if getattr(doc, "status", "pending").lower() not in ("approved", "active", "enabled"):
        raise HTTPException(status_code=403, detail="Doctor not approved yet. Please contact admin.")
    return doc


def _doctor_columns() -> set[str]:
    return set(Doctor.__table__.columns.keys())


def _safe_doctor_kwargs(**kwargs) -> Dict[str, Any]:
    cols = _doctor_columns()
    return {k: v for k, v in kwargs.items() if k in cols}


def save_prescription_to_csv(entry: dict):
    headers = ["PatientUID", "PatientName", "Diagnosis", "Medicines", "Notes", "Doctor", "Timestamp"]
    try:
        file_exists = PRESCRIPTIONS_CSV.exists()
        with open(PRESCRIPTIONS_CSV, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            if not file_exists:
                writer.writeheader()
            writer.writerow(entry)
        print(f"[Doctor] ✅ Prescription saved for {entry.get('PatientName')}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving prescription: {e}")


# -----------------------------------------------------------------------------
# Login / Logout / Registration
# -----------------------------------------------------------------------------
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        "doctor/login.html",
        {"request": request, "title": "Doctor Login"}
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    response: Response,
    username: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    login_name = (username or "").strip().lower()
    password = (password or "").strip()

    if not login_name or not password:
        return templates.TemplateResponse(
            "doctor/login.html",
            {"request": request, "title": "Doctor Login", "error": "Username and password required."}
        )

    # 🔹 Match only username, since no email field now
    doc = db.query(Doctor).filter(func.lower(Doctor.username) == login_name).first()

    if not doc or not _verify_password(password, getattr(doc, "password_hash", "") or getattr(doc, "password", "")):
        return templates.TemplateResponse(
            "doctor/login.html",
            {"request": request, "title": "Doctor Login", "error": "Invalid credentials."}
        )

    if getattr(doc, "status", "pending").lower() not in ("approved", "active", "enabled"):
        return templates.TemplateResponse(
            "doctor/login.html",
            {"request": request, "title": "Doctor Login", "error": "Your account is pending approval."}
        )

    res = RedirectResponse(url="/doctor/dashboard", status_code=302)
    res.set_cookie(COOKIE_NAME, str(doc.id), httponly=True, max_age=86400)
    return res


@router.get("/logout")
def logout():
    res = RedirectResponse(url="/doctor/login", status_code=302)
    res.delete_cookie(COOKIE_NAME)
    return res


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        "doctor/register.html",
        {"request": request, "title": "Doctor Registration"}
    )


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    department: str = Form(""),
    specialization: str = Form(""),
    license_no: str = Form(""),
    db: Session = Depends(get_db),
):
    name = name.strip()
    username = username.strip().lower()
    password = password.strip()
    department = (department or specialization or "").strip()
    license_no = license_no.strip()

    if not name or not username or not password:
        return templates.TemplateResponse(
            "doctor/register.html",
            {"request": request, "title": "Doctor Registration",
             "error": "Name, Username, and Password are required."}
        )

    if db.query(Doctor).filter(func.lower(Doctor.username) == username).first():
        return templates.TemplateResponse(
            "doctor/register.html",
            {"request": request, "title": "Doctor Registration",
             "error": "Username already in use."}
        )

    pwd_hashed = _hash_password(password)
    doc = Doctor(
        name=name,
        username=username,
        department=department,
        specialization=department,
        license_no=license_no,
        password_hash=pwd_hashed,
        password=pwd_hashed,
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()

    return templates.TemplateResponse(
        "doctor/register.html",
        {"request": request, "title": "Doctor Registration",
         "info": "✅ Registration sent for approval. Please wait for admin confirmation."}
    )


# -----------------------------------------------------------------------------
# 🚀 Intelligent Medicine Autocomplete
# -----------------------------------------------------------------------------
@router.get("/api/availability")
def get_medicine_suggestions(q: str = "", db: Session = Depends(get_db)):
    q = q.strip().lower()
    if not q:
        return JSONResponse([])

    try:
        meds = (
            db.query(Medicine)
            .filter(func.lower(Medicine.name).like(f"%{q}%"))
            .limit(50)
            .all()
        )

        scored = []
        for m in meds:
            name = getattr(m, "name", "")
            if not name:
                continue

            stock = (
                getattr(m, "stock", None)
                or getattr(m, "stock_qty", None)
                or getattr(m, "stock_quantity", None)
                or 0
            )
            lower_name = name.lower()
            score = 2 if lower_name.startswith(q) else (1 if q in lower_name else 0)

            scored.append({
                "name": name,
                "form": getattr(m, "form", "") or "",
                "strength": getattr(m, "strength", "") or "",
                "stock_qty": stock,
                "in_stock": stock > 0,
                "score": score,
            })

        ranked = sorted(scored, key=lambda x: (not x["in_stock"], -x["score"], x["name"]))
        return JSONResponse(ranked[:15])

    except Exception as e:
        print(f"[Doctor API] Intelligent search error: {e}")
        return JSONResponse([], status_code=500)


# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def doctor_dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        doc = _require_doctor(request, db)
    except HTTPException as e:
        if e.status_code in (401, 403):
            return RedirectResponse(url="/doctor/login", status_code=302)
        raise

    today = datetime.today().date()
    patients = (
        db.query(Patient)
        .filter((Patient.doctor_id == doc.id) | (func.lower(Patient.assigned_doctor) == func.lower(doc.name)))
        .order_by(Patient.created_at.desc())
        .all()
    )

    total_patients = len(patients)
    patients_today = len([p for p in patients if p.created_at and p.created_at.date() == today])
    pending_patients = len([p for p in patients if p.status and p.status.lower() == "waiting"])
    total_prescriptions = (
        db.query(func.count(Prescription.id))
        .filter(func.lower(Prescription.doctor_name) == func.lower(doc.name))
        .scalar()
        or 0
    )

    return templates.TemplateResponse("doctor/dashboard.html",
        {"request": request, "title": "Doctor Dashboard", "doctor": doc,
         "today": today, "patients": patients, "patients_today": patients_today,
         "pending_patients": pending_patients, "total_patients": total_patients,
         "total_prescriptions": total_prescriptions})


# -----------------------------------------------------------------------------
# Prescription & History
# -----------------------------------------------------------------------------
@router.get("/prescribe/{patient_uid}", response_class=HTMLResponse)
def prescribe_page(patient_uid: str, request: Request, db: Session = Depends(get_db)):
    try:
        doc = _require_doctor(request, db)
    except HTTPException:
        return RedirectResponse(url="/doctor/login", status_code=302)

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    medicines = db.query(Medicine).order_by(Medicine.name.asc()).all()
    return templates.TemplateResponse("doctor/prescribe.html",
        {"request": request, "patient": patient, "medicines": medicines,
         "doctor": doc, "title": "Prescribe"})


@router.post("/prescribe/{patient_uid}", response_class=HTMLResponse)
def save_prescription(
    patient_uid: str,
    request: Request,
    diagnosis: str = Form(...),
    notes: str = Form(""),
    medicines_json: str = Form("[]"),
    db: Session = Depends(get_db)
):
    try:
        doc = _require_doctor(request, db)
    except HTTPException:
        return RedirectResponse(url="/doctor/login", status_code=302)

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        meds = json.loads(medicines_json)
    except Exception:
        meds = []

    pres = Prescription(
        patient_id=patient.id,
        diagnosis=diagnosis.strip(),
        notes=notes.strip(),
        medicines_json=json.dumps(meds, ensure_ascii=False),
        created_at=datetime.utcnow(),
        doctor_name=doc.name,
    )
    db.add(pres)

    # ✅ Automatically mark patient as Done
    if hasattr(patient, "status"):
        patient.status = "Done"
        db.add(patient)

    db.commit()

    save_prescription_to_csv({
        "PatientUID": patient.patient_uid,
        "PatientName": patient.name,
        "Diagnosis": diagnosis,
        "Medicines": json.dumps(meds, ensure_ascii=False),
        "Notes": notes,
        "Doctor": doc.name,
        "Timestamp": datetime.utcnow().isoformat(),
    })

    return RedirectResponse(url=f"/doctor/history/{patient_uid}", status_code=302)


# ✅ FIXED: Parse medicines JSON before rendering
@router.get("/history/{patient_uid}", response_class=HTMLResponse)
def doctor_history(patient_uid: str, request: Request, db: Session = Depends(get_db)):
    try:
        doc = _require_doctor(request, db)
    except HTTPException:
        return RedirectResponse(url="/doctor/login", status_code=302)

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    db_prescriptions = (
        db.query(Prescription)
        .filter(Prescription.patient_id == patient.id)
        .order_by(Prescription.created_at.desc())
        .all()
    )

    # 🔹 Convert JSON strings to Python objects
    for p in db_prescriptions:
        if isinstance(getattr(p, "Medicines", None), str):
            try:
                p.Medicines = json.loads(p.Medicines)
            except Exception:
                p.Medicines = []
        elif isinstance(getattr(p, "medicines_json", None), str):
            try:
                p.Medicines = json.loads(p.medicines_json)
            except Exception:
                p.Medicines = []

    csv_prescriptions = []
    if PRESCRIPTIONS_CSV.exists():
        with open(PRESCRIPTIONS_CSV, newline="", encoding="utf-8") as csvfile:
            for row in csv.DictReader(csvfile):
                if row.get("PatientUID") == patient_uid:
                    csv_prescriptions.append(row)

    prescriptions = db_prescriptions + csv_prescriptions

    return templates.TemplateResponse(
        "doctor/history.html",
        {
            "request": request,
            "patient": patient,
            "prescriptions": prescriptions,
            "doctor": doc,
            "today": datetime.today(),
            "title": f"History - {patient.name}",
        },
    )